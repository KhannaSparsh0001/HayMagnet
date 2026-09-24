# Streamlit Asyncio Event-Lock Issue & Resolution

## 1. The Problem
During Phase 3 testing, Agent 1 (The DB Expert powered by Gemini 3.6 Flash) would successfully formulate a TigerGraph MCP tool call (e.g., `tigergraph__get_graph_schema`) and execute it in under 1 second. However, when attempting to send the tool's JSON output back to the Gemini API for synthesis, the application would freeze infinitely.

**Symptoms:**
- The terminal hung on `[18:21:59] Sending tool results back to Gemini...`
- No Python exception or timeout error was ever thrown.
- The Streamlit dashboard spinner spun indefinitely without rendering new text.

## 2. Testing & Investigation
To isolate the root cause, several diagnostic tests were run in the background:
1. **Payload Size Check:** We verified if `tigergraph__get_graph_schema` was returning a massive JSON payload that crashed the API. Reviewing `setup_graph.py` confirmed the graph schema is extremely small (7 vertices, 9 edges), ruling out payload size limits.
2. **Model Deprecation Checks:** Tests confirmed that `gemini-2.5-flash` was returning a `404 NOT_FOUND` for new users, leading us to upgrade to `gemini-3.6-flash`.
3. **The `thought_signature` Red Herring:** A mock API script manually passed a simulated `function_response` to Gemini 3.6 Flash. This triggered a `400 INVALID_ARGUMENT` error complaining about a missing `thought_signature`. This initially led to the false conclusion that the `google-genai` SDK was bugged. However, further analysis proved this error was only caused by the mock script's improperly formatted chat history, not the actual application code.

## 3. The Root Cause: Asynchronous Thread Deadlock
The true culprit was an event-loop thread deadlock. Streamlit executes apps in a unique threading model, and our `run_investigation_ui` relies on `asyncio`. 
- The `google-genai` SDK's `chat.send_message()` is a **synchronous, blocking** network call.
- Executing a blocking network call directly inside an `async def` function (without yielding) hijacks the event loop.
- This starved the underlying network sockets, causing the `send_message` HTTP request to deadlock infinitely without ever triggering a native timeout.

## 4. The Solution (Attempt 1: Threading)
The resolution required unblocking the event loop and implementing aggressive fail-safes.
1. **Thread Offloading:** We wrapped the synchronous Gemini network calls inside `asyncio.to_thread()`. This pushes the blocking I/O to a background worker thread, allowing the main event loop (and Streamlit's UI) to continue breathing.
2. **Hard Timeouts:** We wrapped the threaded calls in `asyncio.wait_for(..., timeout=60.0)`. If Google's API hangs or network conditions degrade, the code will aggressively kill the request after 60 seconds and gracefully fall back to an error string, guaranteeing the UI never freezes again.

## 5. The Stateless Refactor (Attempt 2)
Even after fixing the threading, the Gemini SDK was throwing a `ValueError` because the model returned a chained `function_call` instead of a text summary, causing the UI to silently crash. 
We refactored `agent1_db_expert` to bypass `chat.send_message` entirely. Instead of feeding tool outputs back into the broken chat history, we now intercept the JSON and spawn a fresh, stateless `generate_content` prompt instructing the model to summarize it. This successfully forced Gemini to return plain text in 2.70 seconds.

## 6. Current Unresolved State
Despite all backend fixes succeeding (the terminal verifies Gemini completes its synthesis successfully without warnings), the Streamlit UI still permanently freezes before rendering Turn 2. 
**Suspected Root Cause:** A fatal conflict between Streamlit's `st.write_stream()` generator (used by the Groq Agent) and the enclosing `asyncio.run()` event loop, or an invalid model ID (`openai/gpt-oss-120b`) causing Groq to throw an exception that Streamlit silently swallows.
