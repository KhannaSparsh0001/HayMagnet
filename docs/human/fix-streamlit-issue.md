\# HayMagnet — Fix Streamlit UI Freeze During Async Multi-Agent Groq Streaming



\## Context



HayMagnet is a Python multi-agent fraud-investigation system using:



\* Streamlit frontend

\* `asyncio` orchestration

\* Agent 1: Gemini → natural language → TigerGraph queries through MCP

\* Agent 2: Groq GPT-OSS 120B / Llama → Lead Investigator

\* TigerGraph for graph evidence



Current execution flow:



```text

User

&#x20; ↓

Streamlit

&#x20; ↓

asyncio orchestration

&#x20; ↓

Agent 1 — Gemini

&#x20; ↓

MCP tools

&#x20; ↓

TigerGraph

&#x20; ↓

Graph evidence

&#x20; ↓

Agent 2 — Groq

&#x20; ↓

stream response to Streamlit

```



Agent 1 completes successfully. The terminal confirms that Gemini executes MCP tools, retrieves the TigerGraph schema/data, and produces evidence.



The application then freezes when Agent 2 begins.



Observed behavior:



\* Streamlit spinner remains indefinitely.

\* Groq response never appears in the UI.

\* No useful exception reaches the terminal.

\* The process does not obviously crash.

\* Previous Gemini blocking-network issue was already mitigated using `asyncio.to\_thread()` + `asyncio.wait\_for()`.



\## Important correction to the diagnosis



Do NOT assume that `st.write\_stream()` itself is inherently incompatible with asyncio.



Current Streamlit versions support async generators with `st.write\_stream()`. The likely problem is the architecture around the event loop, synchronous Streamlit rendering, stream consumption, exception propagation, or a blocking API call.



Therefore, diagnose the actual blocking boundary instead of blindly removing `st.write\_stream()`.



\---



\# Required Architecture



Separate the backend agent execution from Streamlit rendering.



The architecture should become:



```text

&#x20;                        STREAMLIT UI

&#x20;                             │

&#x20;                        synchronous

&#x20;                             │

&#x20;                             ▼

&#x20;                      UI stream adapter

&#x20;                             │

&#x20;                        queue / bridge

&#x20;                             │

&#x20;                             ▼

&#x20;                      ASYNC BACKEND

&#x20;                             │

&#x20;                   asyncio event loop

&#x20;                             │

&#x20;             ┌───────────────┴───────────────┐

&#x20;             │                               │

&#x20;         Agent 1                         Agent 2

&#x20;          Gemini                           Groq

&#x20;             │                               │

&#x20;         MCP tools                    AsyncGroq stream

&#x20;             │                               │

&#x20;         TigerGraph                           │

&#x20;             │                               │

&#x20;             └───────────────┬───────────────┘

&#x20;                             │

&#x20;                        Agent events

&#x20;                             │

&#x20;                             ▼

&#x20;                        UI adapter

&#x20;                             │

&#x20;                             ▼

&#x20;                   st.write\_stream()

```



\## Critical architectural rule



Agents must NEVER directly call Streamlit UI functions.



Do NOT do this:



```python

async def investigator(...):

&#x20;   ...

&#x20;   st.write\_stream(...)

```



Do this instead:



```python

async def investigator(...):

&#x20;   ...

&#x20;   yield text

```



The backend should produce data/events.



The Streamlit layer should consume those events and render them.



\---



\# Step 1 — Inspect the existing implementation



Before changing code, locate:



1\. Where `asyncio.run()` is called.

2\. Where the main investigation pipeline starts.

3\. Where Agent 1 completes.

4\. Where Agent 2 starts.

5\. Where the Groq client is instantiated.

6\. Whether Groq uses `Groq` or `AsyncGroq`.

7\. Where the Groq stream is created.

8\. Where the stream is consumed.

9\. Where `st.write\_stream()` is called.

10\. Any `asyncio.to\_thread()` usage.

11\. Any `asyncio.wait\_for()` usage.

12\. Any `run\_until\_complete()` usage.

13\. Any nested `asyncio.run()` usage.

14\. Any synchronous Groq iterator being consumed inside async code.



Do not make broad architectural changes before understanding the current call chain.



\---



\# Step 2 — Agent 2 must use AsyncGroq



If Agent 2 is currently using the synchronous Groq client for streaming, migrate the streaming path to `AsyncGroq`.



Conceptually:



```python

from groq import AsyncGroq



client = AsyncGroq(...)

```



Then:



```python

stream = await client.chat.completions.create(

&#x20;   model="openai/gpt-oss-120b",

&#x20;   messages=messages,

&#x20;   stream=True,

)

```



Consume it asynchronously:



```python

async for chunk in stream:

&#x20;   text = chunk.choices\[0].delta.content



&#x20;   if text:

&#x20;       yield text

```



Do NOT create a synchronous stream and then iterate over it inside the asyncio event loop.



Also do NOT blindly wrap the entire streaming operation in `asyncio.to\_thread()` if an async Groq client is available.



\---



\# Step 3 — Add an idle timeout to Groq streaming



A timeout around only the initial request is insufficient.



The stream can successfully open and then stop producing chunks.



Protect individual chunk retrieval.



Conceptually:



```python

async def groq\_stream(...):



&#x20;   stream = await client.chat.completions.create(

&#x20;       model="openai/gpt-oss-120b",

&#x20;       messages=messages,

&#x20;       stream=True,

&#x20;   )



&#x20;   while True:



&#x20;       try:

&#x20;           chunk = await asyncio.wait\_for(

&#x20;               stream.\_\_anext\_\_(),

&#x20;               timeout=30,

&#x20;           )



&#x20;       except StopAsyncIteration:

&#x20;           break



&#x20;       except asyncio.TimeoutError:

&#x20;           raise TimeoutError(

&#x20;               "Groq stream produced no chunk for 30 seconds"

&#x20;           )



&#x20;       text = chunk.choices\[0].delta.content



&#x20;       if text:

&#x20;           yield text

```



Adapt this to the actual Groq SDK implementation if its stream object exposes iteration differently.



The important requirement is:



> Detect a stream that opens successfully but produces no chunk for an extended period.



Never allow an infinite silent wait.



\---



\# Step 4 — Separate backend events from Streamlit



Create an event abstraction.



For example:



```python

from dataclasses import dataclass

from typing import Any





@dataclass

class AgentEvent:

&#x20;   type: str

&#x20;   data: Any = None

```



Useful event types:



```text

agent\_started

agent\_completed

tool\_started

tool\_completed

evidence\_received

token

agent\_completed

agent\_error

pipeline\_completed

```



For the Groq response, produce:



```python

yield AgentEvent(

&#x20;   type="token",

&#x20;   data=text,

)

```



Do not call `st.write()`, `st.write\_stream()`, `st.status()`, etc. from inside the agent.



\---



\# Step 5 — If necessary, create an async → sync bridge



If the current Streamlit execution model requires the backend to run independently, use a queue between the async backend and synchronous UI.



Use:



```python

queue.Queue()

```



for the cross-thread boundary.



Conceptual implementation:



```python

import asyncio

import queue

import threading





def run\_async\_stream(async\_generator\_factory):



&#x20;   q = queue.Queue()

&#x20;   DONE = object()



&#x20;   def runner():



&#x20;       async def consume():



&#x20;           try:

&#x20;               async for item in async\_generator\_factory():

&#x20;                   q.put(("data", item))



&#x20;           except Exception as exc:

&#x20;               q.put(("error", exc))



&#x20;           finally:

&#x20;               q.put(("done", DONE))



&#x20;       asyncio.run(consume())



&#x20;   thread = threading.Thread(

&#x20;       target=runner,

&#x20;       daemon=True,

&#x20;   )



&#x20;   thread.start()



&#x20;   while True:



&#x20;       kind, value = q.get()



&#x20;       if kind == "data":

&#x20;           yield value



&#x20;       elif kind == "error":

&#x20;           raise value



&#x20;       elif kind == "done":

&#x20;           break



&#x20;   thread.join(timeout=1)

```



Then the Streamlit layer can consume it:



```python

with st.chat\_message("assistant"):



&#x20;   response = st.write\_stream(

&#x20;       run\_async\_stream(

&#x20;           lambda: investigator\_stream(evidence)

&#x20;       )

&#x20;   )

```



Adapt this implementation to the existing project rather than blindly duplicating infrastructure.



\---



\# Step 6 — Do NOT create nested event-loop problems



Search the project for:



```python

asyncio.run(

```



```python

loop.run\_until\_complete(

```



```python

asyncio.get\_event\_loop(

```



and nested async execution.



Avoid architectures like:



```text

asyncio.run()

&#x20;   ↓

async function

&#x20;   ↓

asyncio.run()

```



or:



```text

asyncio event loop

&#x20;   ↓

blocking stream iterator

&#x20;   ↓

Streamlit

```



There should be a clearly defined owner for the backend event loop.



\---



\# Step 7 — Instrument the exact freeze location



Add temporary logging around the entire Agent 2 lifecycle.



At minimum:



```text

A1: Agent 1 completed

A2: Evidence assembled

A3: Starting Agent 2

A4: Starting Groq request

A5: Groq stream object received

A6: Waiting for first Groq chunk

A7: Groq chunk received

A8: Putting chunk into UI queue

A9: Streamlit consumed chunk

A10: Groq stream completed

A11: Agent 2 completed

```



Use timestamps.



For example:



```python

logger.info("A4: Starting Groq request")

```



etc.



This is important because the current symptom does NOT prove that Streamlit is the root cause.



Determine exactly which transition stops.



\---



\# Step 8 — Explicitly propagate exceptions



Do not allow exceptions inside the async producer to disappear.



The async producer must do:



```python

try:

&#x20;   ...

except Exception as exc:

&#x20;   q.put(("error", exc))

&#x20;   logger.exception("Agent 2 failed")

finally:

&#x20;   q.put(("done", None))

```



The synchronous Streamlit consumer must do:



```python

if kind == "error":

&#x20;   raise RuntimeError(

&#x20;       f"Agent pipeline failed: {value}"

&#x20;   ) from value

```



This ensures:



```text

async exception

&#x20;     ↓

queue

&#x20;     ↓

Streamlit

```



rather than:



```text

async exception

&#x20;     ↓

hidden inside generator

&#x20;     ↓

infinite UI spinner

```



\---



\# Step 9 — First isolate Groq from the entire agent pipeline



Before testing the complete:



```text

Gemini → MCP → TigerGraph → Groq → Streamlit

```



pipeline, create a minimal test using the exact same Groq model/client:



```text

Streamlit

&#x20;  ↓

async Groq generator

&#x20;  ↓

GPT-OSS 120B

&#x20;  ↓

stream chunks

&#x20;  ↓

Streamlit

```



Test with a simple prompt:



```text

Respond with 20 short words.

```



If this works:



```text

Groq + Streamlit = working

```



Then the problem is in the HayMagnet orchestration boundary.



If this hangs:



```text

Groq stream itself = suspect

```



Then inspect:



\* model name

\* SDK version

\* API response

\* authentication

\* network

\* stream initialization

\* first-token latency

\* timeout behavior



Do NOT modify the entire architecture until this isolation test is understood.



\---



\# Step 10 — Preserve the existing Gemini fix



The Gemini integration previously had synchronous blocking network calls.



Keep the existing pattern where appropriate:



```python

await asyncio.to\_thread(...)

```



plus:



```python

asyncio.wait\_for(...)

```



Do not remove a working Gemini fix just because Agent 2 is being redesigned.



The desired architecture is:



```text

Gemini synchronous SDK

&#x20;       ↓

asyncio.to\_thread()

&#x20;       ↓

async orchestration



Groq asynchronous SDK

&#x20;       ↓

native async streaming

&#x20;       ↓

async orchestration

```



\---



\# Desired final architecture



The final system should conceptually look like:



```text

&#x20;                        STREAMLIT

&#x20;                           │

&#x20;                   synchronous rendering

&#x20;                           │

&#x20;                           ▼

&#x20;                    UI event adapter

&#x20;                           │

&#x20;                           ▼

&#x20;                      Event Queue

&#x20;                           │

&#x20;                ┌──────────┴──────────┐

&#x20;                │                     │

&#x20;             ASYNCIO              ASYNCIO

&#x20;            BACKEND               STREAM

&#x20;                │                     │

&#x20;                ▼                     ▼

&#x20;         Investigation           AsyncGroq

&#x20;            Pipeline                 │

&#x20;                │                    │

&#x20;      ┌─────────┴─────────┐          │

&#x20;      │                   │          │

&#x20;   Gemini                MCP       tokens

&#x20;      │                   │          │

&#x20;      └─────────┬─────────┘          │

&#x20;                ▼                    │

&#x20;            TigerGraph              │

&#x20;                │                    │

&#x20;                └─────────┬──────────┘

&#x20;                          ▼

&#x20;                    Agent 2 evidence

&#x20;                          │

&#x20;                          ▼

&#x20;                      Groq stream

&#x20;                          │

&#x20;                          ▼

&#x20;                      AgentEvent

&#x20;                          │

&#x20;                          ▼

&#x20;                        Queue

&#x20;                          │

&#x20;                          ▼

&#x20;                    Streamlit UI

```



\## Success criteria



The implementation is complete only when:



1\. Agent 1 still executes successfully.

2\. MCP/TigerGraph operations still work.

3\. Agent 2 uses asynchronous Groq streaming.

4\. Streamlit UI remains responsive while Agent 2 runs.

5\. Tokens appear incrementally instead of only after completion.

6\. A stalled Groq stream produces a timeout instead of an infinite spinner.

7\. Groq/API exceptions reach the UI and terminal.

8\. No agent directly calls Streamlit rendering APIs.

9\. No nested event loops are introduced.

10\. No synchronous blocking iterator is consumed on the main asyncio event loop.

11\. The exact freeze location can be identified from logs.

12\. The minimal isolated Groq → Streamlit streaming test passes.



\## Important



Do not blindly assume:



> "`st.write\_stream()` + asyncio = deadlock."



That is not established.



Treat the actual problem as:



> \*\*An async multi-agent backend and synchronous Streamlit rendering currently have an unsafe execution/streaming boundary.\*\*



Find the exact blocking boundary, then implement a clean async-backend → event/queue → synchronous-UI architecture.



