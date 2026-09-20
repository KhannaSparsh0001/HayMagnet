# HayMagnet 🤖 🧲

**Built for Hacker House Goa 2026**

HayMagnet is an intelligent, scalable fraud-detection agent built during the exclusive Hacker House Goa residency. Sitting at the intersection of Artificial Intelligence and high-performance data processing, it bridges the deep graph traversal capabilities of **TigerGraph Savanna** with the advanced reasoning of **Google Gemini 2.5**. 

Rather than a simple prototype, HayMagnet is designed as a scalable product architecture that enables an autonomous LLM agent to investigate suspected fraudulent transactions across massive datasets, based on a strict set of banking rules (R1-R10).

## 🏗️ Architecture & Phases

This project was built from scratch in raw Python, avoiding heavy abstractions (like LangChain) to maintain maximum speed and direct control over the LLM and Graph database.

### 1. Schema Provisioning (`setup_graph.py`)
We programmatically define and publish the `FraudGraph` schema directly to the TigerGraph Cloud instance using `pyTigerGraph` and secure REST API Secrets.
- **Vertices:** `Customer`, `Card`, `Transaction`, `DeviceProfile`, `EmailDomain`, `BillingRegion`, `ClosedCase`
- **Edges:** `OWNS`, `MADE`, `FROM_DEVICE`, `PURCHASER_EMAIL`, `BILLED_IN`, `NEXT_TXN`, `INVOLVES`, `ON_CARD`, `CONNECTED_TO`

### 2. Data Ingestion Pipeline (`load_data.py`)
Handling the massive 1GB IEEE-CIS dataset requires careful memory management. This script uses a chunked `pandas` pipeline to stream hundreds of thousands of transactions into TigerGraph securely via `upsertVertexDataFrame` and `upsertEdgeDataFrame`, ensuring all IDs are strictly formatted for the REST API.

### 3. MCP Agent Bridge (`agent.py`)
The crown jewel of the project. We built a custom bridge that connects the `tigergraph-mcp` (Model Context Protocol) server directly to the native `google-genai` SDK.
- Dynamically extracts the R1-R10 banking rules from a PDF using `PyPDF2`.
- Translates TigerGraph MCP JSON schemas into Gemini Function Declarations.
- Allows Gemini to autonomously traverse the graph, write queries, and output a final JSON verdict (`Confirmed Fraud` or `False Positive`) for triggered cases.

## 🚀 How to Run

### Prerequisites
1. A TigerGraph Savanna Workspace.
2. A Google Gemini API Key.
3. The IEEE-CIS dataset placed in the `HHGOA_IEEE/` directory.

### Setup
1. Clone this repository.
2. Create a `.env` file in the root directory:
```env
TG_HOST=https://your-tigergraph-workspace-url
TG_SECRET=your_database_secret
GEMINI_API_KEY=your_gemini_api_key
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Execution
**Step 1:** Build the graph schema.
```bash
python setup_graph.py
```

**Step 2:** Ingest the dataset.
```bash
python load_data.py
```

**Step 3:** Unleash the AI Investigator.
```bash
python agent.py
```

---
*Built with ❤️ and ☕ for the TigerGraph Hackathon.*
