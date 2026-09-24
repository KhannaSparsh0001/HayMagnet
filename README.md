# HayMagnet 🤖 🧲

**Built for Hacker House Goa 2026**

HayMagnet is an intelligent, scalable fraud-detection agent built during the exclusive Hacker House Goa residency. Sitting at the intersection of Artificial Intelligence and high-performance data processing, it bridges the deep graph traversal capabilities of **TigerGraph Savanna** with the advanced reasoning of **Groq**, **Google Gemini**, and **Hugging Face**. 

Rather than a simple prototype, HayMagnet is designed as a scalable product architecture that enables an autonomous multi-agent workforce to investigate suspected fraudulent transactions across massive datasets, based on a strict set of banking rules (R1-R10).

## 🏗️ Architecture & Phases

This project was built from scratch in raw Python, avoiding heavy abstractions (like LangChain) to maintain maximum speed and direct control over the LLMs and Graph database.

### 1. Schema Provisioning (`setup_graph.py`)
We programmatically define and publish the `FraudGraph` schema directly to the TigerGraph Cloud instance using `pyTigerGraph` and secure REST API Secrets.
- **Vertices:** `Customer`, `Card`, `Transaction`, `DeviceProfile`, `EmailDomain`, `BillingRegion`, `ClosedCase`
- **Edges:** `OWNS`, `MADE`, `FROM_DEVICE`, `PURCHASER_EMAIL`, `BILLED_IN`, `NEXT_TXN`, `INVOLVES`, `ON_CARD`, `CONNECTED_TO`

### 2. Data Ingestion Pipeline (`load_data.py`)
Handling the massive 1GB IEEE-CIS dataset requires careful memory management. This script uses a chunked `pandas` pipeline to stream hundreds of thousands of transactions into TigerGraph securely.

### 3. The Tri-Model Agentic Engine (`agent.py` & `tools.py`)
The crown jewel of the project. We built a custom bridge that connects the `tigergraph-mcp` (Model Context Protocol) server to multiple leading AI platforms.
- **Agent 1 (DB Expert):** Powered by **Google Gemini 2.5 Flash**. It translates plain-english requests into direct TigerGraph tool calls to extract live graph data.
- **Agent 2 (Lead Investigator):** Powered by **Groq Llama-3.1-70B**. It acts as the brain, analyzing evidence, forming plans, and issuing directives to the DB Expert until a conclusion is reached.
- **Agent 3 (Senior Overseer):** Also powered by Groq, this critic agent evaluates Agent 2's final verdict to catch hallucinations or skipped rules, forcing a retry if the logic is flawed.
- **Serverless Fallback:** If Gemini hits a 429 Rate Limit error, the engine instantly and transparently routes the MCP tool schemas to **Hugging Face's Serverless API** (Meta-Llama-3) to ensure zero downtime.
- **JSON Formatter:** A dedicated Groq agent forces the final unstructured verdict into a strictly formatted JSON file.

### 4. Interactive Live Dashboard (`app.py`)
A slick, real-time web application built with **Streamlit**. It allows judges to select a case trigger and watch the agents collaborate in real-time through chat bubbles, expandable graph data modules, and massive Final Verdict metric cards.

## 🚀 How to Run

### Prerequisites
1. A TigerGraph Savanna Workspace.
2. A Google Gemini API Key (`GEMINI_API_KEY`).
3. A Groq API Key (`GROQ_API_KEY`).
4. A Hugging Face Token (`HF_TOKEN`).
5. The IEEE-CIS dataset placed in the `HHGOA_IEEE/` directory.

### Setup
1. Clone this repository.
2. Create a `.env` file in the root directory:
```env
TG_HOST=https://your-tigergraph-workspace-url
TG_SECRET=your_database_secret
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key
HF_TOKEN=your_hf_token
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Execution
**Option A: The Batch Processor**
To unleash the agents on the entire `case_pack.csv` backlog, producing JSON reports for each case automatically:
```bash
python agent.py
```

**Option B: The Live Dashboard (Recommended for Demos)**
To spin up the web UI and watch the multi-agent system investigate a single case in real-time:
```bash
streamlit run app.py
```

---
*Built with ❤️ and ☕ for the TigerGraph Hackathon.*
