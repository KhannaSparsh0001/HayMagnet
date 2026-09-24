# HayMagnet API & Code Reference

This document provides a reference for the core Python modules, functions, classes, and parameters across the HayMagnet repository.

---

## 1. `tools.py`

### Functions

#### `clean_schema(schema: dict) -> dict`
- **Purpose**: Cleans JSON schema definitions returned by the MCP server by removing keywords (`examples`, `default`, `title`, `$ref`, `$defs`) that violate strict OpenAPI validators in Gemini and OpenAI formats.
- **Parameters**: `schema` (JSON schema dictionary).
- **Returns**: Cleaned schema dictionary.

#### `convert_mcp_tool_to_gemini(mcp_tool) -> types.FunctionDeclaration`
- **Purpose**: Converts an MCP tool instance into a Google GenAI `types.FunctionDeclaration` object.
- **Parameters**: `mcp_tool` (MCP tool object with `name`, `description`, `input_schema`).
- **Returns**: `FunctionDeclaration` configured with sanitized schema.

#### `convert_mcp_to_openai_schema(mcp_tool) -> dict`
- **Purpose**: Converts an MCP tool instance into an OpenAI-compatible function calling dictionary format. Used by Groq and Hugging Face inference clients.
- **Parameters**: `mcp_tool`.
- **Returns**: OpenAI function dictionary `{"type": "function", "function": {...}}`.

### Classes

#### `TigerGraphMCPClient`
Manages the lifecycle, subprocess execution, and session management for the TigerGraph Model Context Protocol server.

- **`async def connect()`**: Starts `tigergraph-mcp` subprocess using stdio client and initializes an active MCP `ClientSession`. Uses `shutil.which` to find executable on Windows/Linux.
- **`async def get_allowed_tools() -> list`**: Queries MCP server for available tools and filters down to the approved set: `tigergraph__gsql`, `tigergraph__get_node`, `tigergraph__get_node_edges`, `tigergraph__get_graph_schema`, `tigergraph__run_query`.
- **`async def execute_tool(tool_name: str, args_dict: dict) -> str`**: Executes an MCP tool on TigerGraph with a 45-second timeout and returns the string response.
- **`async def close()`**: Cleanly exits the async stack and terminates the MCP server subprocess.

---

## 2. `agent.py`

### Functions

#### `get_fraud_rules() -> str`
- **Purpose**: Reads `fraud_rules.txt` and returns the institutional rules text.

#### `triage_case(row: pd.Series) -> bool`
- **Purpose**: Heuristic pre-filter. Evaluates trigger type and risk score (`risk_score < 0.5` skipped as low risk unless customer report).
- **Returns**: `True` if case should be investigated, `False` otherwise.

#### `format_final_verdict(verdict_text: str, case_id: str) -> Optional[str]`
- **Purpose**: Calls Groq (`llama-3.1-8b-instant`) with `json_object` response format to structure final decision (`Confirmed Fraud` or `False Positive`) and reasoning paragraph. Writes output to `cases/{case_id}.json`.

#### `agent2_planner(case_trigger: str, rules: str, db_evidence: str, feedback: str = "") -> str`
- **Purpose**: Lead Investigator agent. Analyzes trigger, rules, prior evidence, and critic feedback. Returns either `Data Request: ...` or `Final Verdict: ...`.

#### `agent2_planner_stream(case_trigger: str, rules: str, db_evidence: str, feedback: str = "") -> Generator`
- **Purpose**: Streaming variant of `agent2_planner` for real-time rendering in Streamlit (`st.write_stream`).

#### `agent3_critic(verdict: str, db_evidence: str, rules: str) -> str`
- **Purpose**: Senior Overseer. Checks verdict for hallucinations or rule misapplications against gathered evidence. Emits `APPROVED` or `REJECTED: ...`.

#### `agent1_db_expert(mcp_client: TigerGraphMCPClient, data_request: str, tools: list, ui_callback: Optional[callable] = None) -> str`
- **Purpose**: Database Expert powered by Gemini 3.6 Flash. Maps data request to MCP function calls, executes them via TigerGraph, and statelessly synthesizes graph evidence.
- **Failover**: Falls back to `agent1_hf_fallback` on Gemini 429 quota errors.

#### `agent1_hf_fallback(mcp_client: TigerGraphMCPClient, data_request: str, tools: list, system_instruction: str, ui_callback: Optional[callable] = None) -> str`
- **Purpose**: Serverless fallback using Hugging Face Llama 3 70B Instruct with tool calling.

#### `investigate_case(mcp_client, case_trigger, tools, rules) -> str`
- **Purpose**: Multi-turn orchestration loop coordinating Agent 2, Agent 1, and Agent 3.

---

## 3. `app.py`

Streamlit dashboard entry point providing:
- Case loading and caching (`load_data()`).
- Reactive session state management (`st.session_state.is_running`).
- Real-time multi-agent execution pipeline (`run_investigation_ui()`).
- UI callbacks for tool execution indicators and Overseer review banners.
