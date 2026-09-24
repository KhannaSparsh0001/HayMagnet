import streamlit as st
import pandas as pd
import requests
import json
import os

BACKEND_URL = "http://127.0.0.1:8000"

# Page configuration
st.set_page_config(
    page_title="HayMagnet - AI Fraud Investigator",
    page_icon="🤖",
    layout="wide"
)

# Fetch cases from Backend API (with fallback to local CSV)
@st.cache_data(ttl=5)
def get_cases():
    try:
        res = requests.get(f"{BACKEND_URL}/api/cases", timeout=3)
        if res.status_code == 200:
            return pd.DataFrame(res.json()["cases"])
    except Exception:
        pass
    
    csv_path = "HHGOA_IEEE/case_pack.csv"
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    return None

df = get_cases()

# Check server health
def check_server():
    try:
        res = requests.get(f"{BACKEND_URL}/", timeout=2)
        return res.status_code == 200, res.json() if res.status_code == 200 else {}
    except Exception:
        return False, {}

server_online, server_info = check_server()

# Sidebar
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.title("HayMagnet 🧲")
        
    st.header("System Status")
    if server_online:
        st.success(f"🟢 **Backend Online** ({server_info.get('tools_count', 0)} MCP Tools Active)")
    else:
        st.error("🔴 **Backend Offline**\n\nPlease run `python server.py` in a separate terminal.")
        st.info("```bash\npython server.py\n```")

    st.divider()
    st.header("Case Selection")

    if df is not None and not df.empty:
        case_ids = df['case_id'].tolist()
        selected_case_id = st.selectbox("Select a Case ID:", case_ids)

        selected_row = df[df['case_id'] == selected_case_id].iloc[0]

        st.divider()
        st.subheader("Case Metadata")
        st.write(f"**Timestamp:** {selected_row.get('ts', 'N/A')}")
        st.write(f"**Trigger Type:** {selected_row.get('trigger_type', 'N/A')}")

        risk_score = selected_row.get('risk_score', 'N/A')
        st.metric("Risk Score", risk_score)
    else:
        st.error("Could not load case dataset.")
        st.stop()

# Main Panel
st.title("🤖 Autonomous Fraud Investigator")
st.markdown("Watch the multi-agent system investigate TigerGraph in real-time.")

st.info(f"**Trigger Alert:** {selected_row['trigger_text']}")

def run_investigation_stream(case_id):
    st.markdown(f"### 🔍 Investigating Case: `{case_id}`")
    st.divider()

    try:
        response = requests.get(f"{BACKEND_URL}/api/investigate/{case_id}", stream=True, timeout=300)
    except Exception as e:
        st.error(f"Failed to connect to backend server: {e}")
        return

    current_event = None
    planner_container = None
    planner_text = ""

    for line in response.iter_lines():
        if not line:
            continue
        line_str = line.decode('utf-8')

        if line_str.startswith('event: '):
            current_event = line_str[7:].strip()
        elif line_str.startswith('data: '):
            data_str = line_str[6:].strip()
            try:
                data = json.loads(data_str)
            except Exception:
                continue

            # Process Event Types
            if current_event == "turn_start":
                turn = data.get("turn", 1)
                st.markdown(f"#### 🔄 Turn {turn}")
                planner_container = st.empty()
                planner_text = ""

            elif current_event == "planner_chunk":
                chunk = data.get("chunk", "")
                planner_text += chunk
                if planner_container:
                    planner_container.markdown(f"🤖 **Lead Investigator (Agent 2):**\n\n{planner_text}")

            elif current_event == "data_request":
                req = data.get("request", "")
                st.info(f"⚡ **Data Request to DB Expert:** _{req}_")

            elif current_event == "tool_exec":
                t_name = data.get("tool_name", "")
                t_args = data.get("args", {})
                st.caption(f"🔧 Executing TigerGraph Tool: `{t_name}` with parameters: `{json.dumps(t_args)}`")

            elif current_event == "evidence_retrieved":
                ev = data.get("evidence", "")
                length = data.get("evidence_length", 0)
                with st.expander(f"📊 Retrieved {length} characters of graph evidence"):
                    st.code(ev, language="json")

            elif current_event == "critic_start":
                st.caption("🕵️‍♂️ **Agent 3 (Senior Overseer):** Reviewing verdict logic...")

            elif current_event == "critic_review":
                review = data.get("review", "")
                approved = data.get("approved", False)
                if approved:
                    st.success(f"✅ **Overseer Approved Verdict:**\n\n{review}")
                else:
                    st.error(f"🚨 **Overseer Rejected Verdict:**\n\n{review}")

            elif current_event == "final_verdict":
                st.markdown("---")
                st.markdown("### 🛑 FINAL STRUCTURED VERDICT")
                json_raw = data.get("json_verdict")
                if json_raw:
                    try:
                        parsed = json.loads(json_raw)
                        decision = parsed.get("decision", "Unknown")
                        reasoning = parsed.get("reasoning", "")
                        if "Fraud" in decision:
                            st.error(f"### 🚨 Decision: {decision}\n\n**Reasoning:** {reasoning}")
                        else:
                            st.success(f"### ✅ Decision: {decision}\n\n**Reasoning:** {reasoning}")
                        with st.expander("Raw Verdict JSON"):
                            st.json(parsed)
                    except Exception:
                        st.write(json_raw)
                else:
                    st.warning("Final verdict text received but structured JSON formatting failed.")

            elif current_event == "complete":
                st.balloons()

if st.button("Unleash Agents 🚀", use_container_width=True, type="primary", disabled=not server_online):
    run_investigation_stream(selected_case_id)
