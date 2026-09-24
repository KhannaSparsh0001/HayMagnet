# HayMagnet Operational Runbook

This guide covers setup, dependencies, database provisioning, batch processing, dashboard execution, and troubleshooting.

---

## 1. Prerequisites & Environment Setup

### Required API Keys & Services
1. **TigerGraph Cloud Account**:
   - A Savanna or Cloud workspace running TigerGraph.
   - Database hostname (`TG_HOST`).
   - Secret key or superuser token (`TG_SECRET`).
2. **Google Gemini API Key**:
   - Free or paid tier key from Google AI Studio (`GEMINI_API_KEY`).
   - Powers Agent 1 (DB Expert).
3. **Groq API Key**:
   - Free API key from Groq Console (`GROQ_API_KEY`).
   - Powers Agent 2 (Lead Investigator) and Agent 3 (Senior Overseer).
4. **Hugging Face Token** *(Optional Fallback)*:
   - Inference API token from Hugging Face (`HF_TOKEN`).

### Setting `.env`
Create or edit `.env` in the repository root:
```env
TG_HOST=https://your-workspace.i.tgcloud.io
TG_SECRET=your_tigergraph_secret_here
TG_USERNAME=your_username
TG_PASSWORD=your_password
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
python -c "import tigergraph_mcp, mcp, google.genai, PyPDF2, groq, huggingface_hub, streamlit, pyTigerGraph; print('All dependencies OK!')"
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
If you have the IEEE-CIS data files placed in `HHGOA_IEEE/` (`transactions.csv`, `identity.csv`, `closed_cases_history.csv`):
```bash
python load_data.py
```

---

## 4. Running the Investigation

### Running the Live Web Dashboard
Launch the interactive Streamlit dashboard:
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.
- Select a Case ID from the sidebar.
- Review the case metadata (timestamp, trigger type, risk score).
- Click **"Unleash Agents 🚀"** to watch the multi-agent investigation stream in real time.

### Running Batch Processing Mode
To run autonomous investigations across all cases in `HHGOA_IEEE/case_pack.csv`:
```bash
python agent.py
```
- Cases are triaged automatically.
- Structured verdicts are saved under `cases/<case_id>.json`.

---

## 5. Troubleshooting & Known Gotchas

### Issue 1: Asynchronous Event-Loop Lock
- **Cause**: Blocking HTTP network calls inside `async def` functions starve the event loop in Streamlit.
- **Fix**: All Gemini SDK calls are wrapped in `asyncio.to_thread()` and bounded by `asyncio.wait_for(timeout=60.0)`.

### Issue 2: Windows Subprocess Path for `tigergraph-mcp`
- **Cause**: On Windows with user-level pip installations, `tigergraph-mcp.exe` resides in `%APPDATA%\Python\Python3xx\Scripts`, which may not match `sys.prefix/Scripts`.
- **Fix**: `tools.py` uses `shutil.which("tigergraph-mcp")` to resolve the executable dynamically.

### Issue 3: Gemini 429 Quota Exceeded
- **Cause**: Rate limiting on free-tier Gemini API keys.
- **Fix**: `agent.py` automatically catches APIError 429 and triggers `agent1_hf_fallback` using Hugging Face Serverless Llama 3 70B.
