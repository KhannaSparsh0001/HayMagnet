<table align="center">
  <tr>
    <td align="center" width="220">
      <img src="logo.png" alt="HayMagnet logo" width="180" />
    </td>
    <td align="center" width="220">
      <h1>HayMagnet</h1>
      <p><strong>Autonomous AI Fraud Investigator</strong></p>
    </td>
  </tr>
</table>

<p align="center">
  <strong>Autonomous AI-powered fraud investigation platform for Hacker House Goa 2026</strong>
</p>

HayMagnet is an intelligent, multi-agent fraud investigation platform built to analyze suspicious financial transactions by combining TigerGraph graph analytics, deterministic policy rules (R1–R10), simulated operational mock APIs, and multi-provider LLM reasoning. Instead of a single chatbot, the system uses multiple specialized AI agents, deterministic calculation engines, and mock execution bridges to investigate benchmark cases, retrieve graph evidence, enforce institutional rules, and execute policy-approved actions.

---

## ⚡ Core Architecture

- **Agent 1: DB Expert** uses **Google Gemini 2.5 Flash / Groq** to interpret requests and call TigerGraph MCP tools (`get_node_edges`, `run_query`).
- **Agent 2: Lead Investigator** uses **Groq `openai/gpt-oss-120b` / Gemini / HuggingFace** to reason about fraud rules, evidence, and historical case memory.
- **Agent 3: Senior Overseer** reviews final verdicts to reject hallucinated or incomplete conclusions.
- **Deterministic Policy Engine (`policy_engine.py`)**: Computes exact exposure USD, evaluates institutional rules (R1–R10), determines approval routes (`AUTO_APPROVE`, `L1_MANUAL_REVIEW`, `L2_SAR_ESCALATION`), and generates 100% compliant Pydantic benchmark JSON.
- **Mock Action Execution Engine (`action_executor.py`)**: Simulates external operational APIs (customer SMS/email messages, account freezes, card blocks, chargeback refunds, CRM tickets, case closure).
- **Universal Multi-Provider Engine**: Dynamic model provider selection (Gemini, Groq, HuggingFace, or Custom write-in models) with live `/api/test-model` verification and automatic fallback.
- **Decoupled Execution & UI (`server.py` + `app.py`)**: FastAPI backend streaming Server-Sent Events (SSE) to a high-contrast Enterprise Light Mode Streamlit dashboard with a 20-case batch benchmark auditor.

---

## 🔑 Key Components

- `policy_engine.py` — deterministic rule evaluation (R1–R10), exposure calculation, 3-tier approval matrix, Pydantic benchmark schema
- `action_executor.py` — simulated mock APIs (customer messaging, account freeze, card block, refund, CRM ticket, case closure)
- `agent.py` — multi-agent orchestration loop with dynamic model execution & fallback
- `server.py` — FastAPI backend with SSE streaming `/api/investigate/{case_id}` and `/api/test-model`
- `tools.py` — TigerGraph MCP client & `write_case_to_graph` deterministic case memory write-back
- `app.py` — Streamlit web dashboard client with Enterprise Light Mode theme & 20-case batch runner
- `run.py` — unified dual-server launcher script
- `setup_graph.py` — graph schema provisioning
- `load_data.py` — IEEE-CIS dataset ingestion pipeline
- `extract_rules.py` — extracts fraud heuristics into `fraud_rules.txt`

---

## 🔄 Investigation Workflow

```text
Case trigger
   ↓
Lead Investigator (Agent 2) requests evidence & queries TigerGraph Case Memory
   ↓
DB Expert (Agent 1) executes TigerGraph MCP graph tools
   ↓
Overseer (Agent 3) validates reasoning and logic soundness
   ↓
Deterministic Policy Engine evaluates R1-R10 rules & approval routing (auto/L1/L2)
   ↓
Action Executor runs simulated mock APIs (freeze account, block card, customer SMS, CRM ticket)
   ↓
Graph Case Memory persists closed case findings back to TigerGraph
   ↓
Final Pydantic Benchmark JSON verdict saved & reported
```

---

## 🛠️ Tech Stack

- **Languages & Frameworks**: Python, Streamlit, FastAPI, Pydantic, Pandas
- **Graph Database**: TigerGraph Cloud (Savanna workspace) via Model Context Protocol (MCP) & GSQL
- **AI Models**: Google Gemini 2.5 Flash, Groq (`openai/gpt-oss-120b`, `gpt-oss-20b`, `qwen3.8-27b`), HuggingFace Llama 3 70B
- **Streaming**: Server-Sent Events (SSE)

---

## 🚀 Running the Project

### Prerequisites

Create `.env` in the root directory:

```env
TG_HOST=https://your-tigergraph-workspace-url
TG_SECRET=your_database_secret
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
HF_TOKEN=your_hf_token
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Launch Unified Platform

Simply run `run.py` to automatically boot both the FastAPI backend and Streamlit frontend in separate terminal tabs:

```bash
python run.py
```

---

_Built with ❤️ and ☕ for Hacker House Goa 2026._
