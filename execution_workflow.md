# Hacker House Goa: HayMagnet Action Plan 🎯

This document outlines the strategic objectives and execution roadmap to transition HayMagnet from its current foundational state into a fully autonomous, production-ready fraud investigation engine.

## Current State (What We Have Built)
- **Data Layer:** Graph schema designed and published to TigerGraph Savanna (`setup_graph.py`).
- **Ingestion Engine:** Massive 1GB IEEE-CIS dataset securely chunked and streamed into the cloud (`load_data.py`).
- **Agent Core:** A custom Python bridge connecting the Gemini SDK to the TigerGraph MCP server, capable of dynamically reading PDF fraud rules (`agent.py`).

---

## Strategic Objectives & Execution Plan

### Objective 1: Agent Efficacy & Tool Verification
**Goal:** Prove that the Gemini LLM can successfully navigate the graph database using MCP tools and correctly apply banking rules (R1-R10) to a single case.
**How we do it:**
1. Execute `python agent.py` (which is currently hardcoded to test Case #1: `HHG-001`).
2. Monitor the terminal to verify that Gemini successfully triggers `mcp.call_tool` and receives valid database responses.
3. Validate that the LLM's final JSON output correctly identifies the fraud pattern based on the PDF rules.

### Objective 2: Batch Case Processing Pipeline
**Goal:** Scale the agent to autonomously investigate the entire backlog of suspected cases without human intervention.
**How we do it:**
1. Modify `agent.py` to remove the hardcoded single-case test.
2. Implement an asynchronous loop that iterates through every row in `HHGOA_IEEE/case_pack.csv`.
3. Feed each `trigger_text` sequentially into the Gemini chat session.
4. Add robust error handling (try/except blocks) to ensure that if the LLM hallucinates a bad tool call on one case, it gracefully skips or retries without crashing the entire pipeline.

### Objective 3: Automated Reporting & Auditing
**Goal:** Generate a tangible, human-readable report of the AI's investigations for the bank's compliance team (and the hackathon judges).
**How we do it:**
1. Intercept the final JSON verdict (`decision` and `reasoning`) outputted by Gemini for each case.
2. Append these results to a pandas DataFrame in memory.
3. Once the batch loop completes, export the DataFrame to `investigation_results.csv`.
4. Ensure the output strictly maps the `case_id` to the `decision` and the `evidence_cited`.

### Objective 4 (Stretch Goal): Interactive UI Demo
**Goal:** Create a visual "wow factor" for the Hacker House presentation.
**How we do it:**
1. Wrap the `agent.py` logic in a lightweight `Streamlit` or `Gradio` web application.
2. Allow a judge to type in a Case ID, hit "Investigate", and watch the agent's thoughts, tool calls, and final verdict stream onto the screen in real-time.
