# System Architecture & Multi-Agent Design

HayMagnet is designed around an AI-first, graph-native multi-agent architecture. Instead of relying on a monolithic LLM prompt or basic RAG, it separates concerns into specialized agents communicating across defined protocol boundaries.

---

## 1. High-Level Architecture Diagram

```text
               +--------------------------------------------+
               |             Case Trigger Event             |
               | (case_pack.csv or Streamlit UI Submission) |
               +--------------------------------------------+
                                     |
                                     v
                        +--------------------------+
                        |   Triage Filter Engine   |
                        |   (triage_case() check)  |
                        +--------------------------+
                                     |
                                     v
     +---------------------------------------------------------------+
     |                   Multi-Agent Investigation Loop              |
     |                                                               |
     |   +-------------------------------------------------------+   |
     |   |              Agent 2: Lead Investigator               |   |
     |   |     (Groq / Llama 3.1 70B / openai/gpt-oss-120b)      |   |
     |   +-------------------------------------------------------+   |
     |            |                                   ^              |
     |      "Data Request: ..."                       |              |
     |            |                           "Result: {JSON/Text}"  |
     |            v                                   |              |
     |   +-------------------------------------------------------+   |
     |   |                 Agent 1: DB Expert                    |   |
     |   |   Primary: Google Gemini 3.6 Flash                    |   |
     |   |   Fallback: Hugging Face Serverless Llama 3 70B       |   |
     |   +-------------------------------------------------------+   |
     |            |                                                  |
     |      MCP stdio RPC (`call_tool`)                              |
     |            v                                                  |
     |   +-----------------------------------+                       |
     |   |     TigerGraph MCP Server         |                       |
     |   |     (`tigergraph-mcp` CLI)        |                       |
     |   +-----------------------------------+                       |
     |            |                                                  |
     |      REST / GSQL                                              |
     |            v                                                  |
     |   +-----------------------------------+                       |
     |   |     TigerGraph Cloud Instance     |                       |
     |   |     Graph: `FraudGraph`           |                       |
     |   +-----------------------------------+                       |
     |                                                               |
     |   When Agent 2 concludes: "Final Verdict: ..."                |
     |                               |                               |
     |                               v                               |
     |   +-------------------------------------------------------+   |
     |   |              Agent 3: Senior Overseer                 |   |
     |   |             (Groq / Llama 3.1 70B)                    |   |
     |   +-------------------------------------------------------+   |
     |            |                                                  |
     |            +--- REJECTED ---> [Loops back to Agent 2 with     |
     |            |                   targeted critic feedback]      |
     |            v                                                  |
     |         APPROVED                                              |
     +---------------------------------------------------------------+
                                     |
                                     v
                        +--------------------------+
                        |  Structured JSON Engine  |
                        |  (Groq format_verdict)   |
                        +--------------------------+
                                     |
                                     v
                        +--------------------------+
                        |  `cases/{case_id}.json`  |
                        |    & UI Real-Time Feed   |
                        +--------------------------+
```

---

## 2. Agent Roles and Specifications

### Agent 1: Database Expert (`agent1_db_expert`)
- **Primary Engine**: Google Gemini 3.6 Flash (`google-genai` SDK)
- **Fallback Engine**: Hugging Face Serverless Inference (`meta-llama/Meta-Llama-3-70B-Instruct`)
- **Responsibility**:
  - Translates natural language inquiries from the Lead Investigator into TigerGraph MCP tool calls.
  - Automatically identifies target nodes, edge traversals, and schema types.
  - Summarizes raw graph responses statelessly into clear evidence for the investigation.
- **Fail-Safe Mechanism**:
  - Automatically catches HTTP `429` / `RESOURCE_EXHAUSTED` quotas on Gemini and switches seamlessly to Hugging Face Llama 3.
  - Offloaded to worker threads via `asyncio.to_thread` with strict 60-second timeouts to avoid blocking the async event loop.

### Agent 2: Lead Investigator (`agent2_planner` / `agent2_planner_stream`)
- **Primary Engine**: Groq High-Speed Inference (`openai/gpt-oss-120b` or `llama-3.1-70b-versatile`)
- **Responsibility**:
  - Analyzes the trigger text and established fraud rules (`fraud_rules.txt`).
  - Iteratively decides whether more evidence is needed from TigerGraph.
  - Emits either a `Data Request: <request>` or `Final Verdict: <verdict>`.
  - Supports live chunk streaming (`agent2_planner_stream`) for the real-time Streamlit dashboard.

### Agent 3: Senior Overseer / Critic (`agent3_critic`)
- **Primary Engine**: Groq High-Speed Inference
- **Responsibility**:
  - Intercepts the final verdict formulated by Agent 2 before it can be finalized.
  - Cross-references cited evidence against the actual database responses collected during the session.
  - Checks for hallucinations, logic inversions, and rule misapplications.
  - Emits `APPROVED` or `REJECTED: <detailed_critique>` to trigger corrective action.

---

## 3. The Model Context Protocol (MCP) Bridge

The communication between the LLM and TigerGraph Cloud is mediated by `tools.py` using the standard Model Context Protocol:
1. `tools.py` launches `tigergraph-mcp` as a subprocess via standard I/O (`stdio_client`).
2. Environment variables (`TG_HOST`, `TG_SECRET`) are securely passed down to the subprocess.
3. Tool definitions are retrieved via `session.list_tools()`.
4. Schemas are sanitized with `clean_schema()` to ensure compatibility with strict OpenAPI validation in Gemini and OpenAI formats.
5. Permitted tools exposed to the agent include:
   - `tigergraph__gsql`
   - `tigergraph__get_node`
   - `tigergraph__get_node_edges`
   - `tigergraph__get_graph_schema`
   - `tigergraph__run_query`

---

## 4. UI Layer (`app.py`)

- **Framework**: Streamlit
- **Features**:
  - Sidebar case selector pulling from `HHGOA_IEEE/case_pack.csv`.
  - Real-time case metadata: timestamp, trigger type, risk score metric.
  - Live chat-style agent visualization:
    - Lead Investigator thoughts streamed live with `st.write_stream`.
    - DB Expert tool executions rendered with expandable JSON payloads.
    - Senior Overseer critique decisions color-coded in green/red.
    - Formatted JSON output display with parsed decision and reasoning.
