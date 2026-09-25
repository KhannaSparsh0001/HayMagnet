# HayMagnet Operational Runbook

This guide covers setup, dependencies, database provisioning, policy engine evaluation, action execution, batch processing, dashboard execution, and troubleshooting.

---

## 1. Prerequisites & Environment Setup

### Required API Keys & Services
1. **TigerGraph Cloud Account**:
   - A Savanna workspace running TigerGraph.
   - Database hostname (`TG_HOST`).
   - Secret key or superuser token (`TG_SECRET`).
2. **Google Gemini API Key**:
   - Free or paid tier key from Google AI Studio (`GEMINI_API_KEY`).
3. **Groq API Key**:
   - Free API key from Groq Console (`GROQ_API_KEY`).
4. **Hugging Face Token**:
   - Inference API token from Hugging Face (`HF_TOKEN`).

### Setting `.env`
Create or edit `.env` in the repository root:
```env
TG_HOST=https://your-workspace.i.tgcloud.io
TG_SECRET=your_tigergraph_secret_here
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
HF_TOKEN=your_hf_token_here
```

---

## 2. Dependency Installation

Install all required packages via pip:
```bash
pip install -r requirements.txt
```

Verify package installation:
```bash
python -c "import tigergraph_mcp, mcp, google.genai, groq, huggingface_hub, streamlit, pydantic, pyTigerGraph; print('All dependencies OK!')"
```

---

## 3. Database Setup & Data Ingestion

### Step 1: Provision Graph Schema
Run `setup_graph.py` to create the `FraudGraph` schema in your TigerGraph instance:
```bash
python setup_graph.py
```

### Step 2: Extract Fraud Rules
Extract institutional rules from the challenge PDF into plain text (`fraud_rules.txt`):
```bash
python extract_rules.py
```

### Step 3: Ingest Data
Ingest IEEE-CIS data files placed in `HHGOA_IEEE/` (`transactions.csv`, `identity.csv`, `closed_cases_history.csv`):
```bash
python load_data.py
```

---

## 4. Architecture Modules

- **`policy_engine.py`**: Deterministic rule engine evaluating institutional rules R1–R10, exposure USD sum, approval routing (`auto/L1/L2`), and Pydantic benchmark schemas.
- **`action_executor.py`**: Mock execution engine for simulated downstream operational actions (customer messaging, account freeze, card block, refund customer, CRM ticket, case closure).
- **`tools.py`**: TigerGraph MCP client bridge and `write_case_to_graph` deterministic case memory write-back.
- **`agent.py`**: Multi-agent orchestration engine with dynamic model selection and fallback logic.

---

## 5. Running the Investigation

### Running the Platform (Unified Launcher)
Launch both the FastAPI backend and Streamlit frontend in separate terminal tabs with a single command:
```bash
python run.py
```
Open your browser at `http://localhost:8501`.

### Manual Independent Launch
If you prefer running components separately:
```bash
# Terminal 1: FastAPI Backend
python server.py

# Terminal 2: Streamlit Dashboard
streamlit run app.py
```

---

## 6. Troubleshooting & Known Gotchas

### Issue 1: Asynchronous Event-Loop Lock
- **Cause**: Blocking HTTP network calls inside `async def` functions starve the event loop in Streamlit.
- **Fix**: All Gemini SDK calls are wrapped in `asyncio.to_thread()` and bounded by `asyncio.wait_for(timeout=60.0)`.

### Issue 2: Windows Subprocess Path for `tigergraph-mcp`
- **Cause**: On Windows with user-level pip installations, `tigergraph-mcp.exe` resides in `%APPDATA%\Python\Python3xx\Scripts`.
- **Fix**: `tools.py` uses `shutil.which("tigergraph-mcp")` to resolve the executable dynamically.

### Issue 3: Gemini 429 Quota Exceeded / Model Fallback
- **Cause**: Rate limiting on free-tier Gemini API keys.
- **Fix**: `agent.py` automatically catches API errors and falls back to Groq candidate models (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`) or Hugging Face.
