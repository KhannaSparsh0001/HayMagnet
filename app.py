import streamlit as st
import pandas as pd
import os
import asyncio
import json

# Import our modularized backend
from tools import TigerGraphMCPClient
from agent import get_fraud_rules, agent2_planner, agent3_critic, agent1_db_expert, format_final_verdict

# Page configuration
st.set_page_config(
    page_title="HayMagnet - AI Fraud Investigator",
    page_icon="🤖",
    layout="wide"
)

# Phase 1: Environment & UI Scaffolding

@st.cache_data
def load_data():
    csv_path = "HHGOA_IEEE/case_pack.csv"
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path)
    return None

df = load_data()

# Initialize session state for investigation running
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# ==========================================
# PHASE 2: ASYNC INTEGRATION
# ==========================================

async def run_investigation_ui(case_row):
    case_trigger = case_row['trigger_text']
    case_id = case_row['case_id']
    
    st.write("🔌 **Connecting to TigerGraph MCP Server...**")
    mcp_client = TigerGraphMCPClient()
    await mcp_client.connect()
    
    rules = get_fraud_rules()
    tools = await mcp_client.get_allowed_tools()
    st.write(f"✅ **Connected! Loaded {len(tools)} graph tools.**")
    
    st.write(f"🔍 **Starting Investigation on {case_id}**")
    
    db_evidence = ""
    critic_feedback = ""
    max_turns = 8
    
    for turn in range(max_turns):
        st.write(f"--- **Turn {turn+1}** ---")
        st.write("> 🤖 **Agent 2 (Groq) is analyzing...**")
        
        action = agent2_planner(case_trigger, rules, db_evidence, feedback=critic_feedback)
        critic_feedback = "" 
        
        if "Final Verdict:" in action or turn == max_turns - 1:
            st.write("> 🤖 **Agent 2 submitted a verdict.**")
            st.write(action)
            
            st.write("> 🕵️ **Agent 3 (Critic) is reviewing...**")
            review = agent3_critic(action, db_evidence, rules)
            
            if "APPROVED" in review or turn == max_turns - 1:
                st.write("> ✅ **Agent 3 APPROVED the verdict.**")
                
                st.write("📝 **Formatting Final Output...**")
                json_result = format_final_verdict(action, case_id)
                if json_result:
                    try:
                        st.json(json.loads(json_result))
                    except:
                        st.write(json_result)
                else:
                    st.write("⚠️ JSON formatting failed.")
                
                await mcp_client.close()
                return
            else:
                st.write(f"> 🚨 **Agent 3 REJECTED the verdict:** {review}")
                critic_feedback = review
                continue 
            
        requested_data = action.replace('Data Request:', '').strip()
        st.write(f"> 🤖 **Agent 2 requested data:** {requested_data}")
        
        st.write("> ⚡ **Agent 1 (Gemini/HF) is executing graph queries...**")
        new_evidence = await agent1_db_expert(mcp_client, action, tools)
        
        db_evidence += f"\nRequest: {action}\nResult: {new_evidence}\n"
        st.write(f"> 📊 **Agent 1 retrieved {len(new_evidence)} characters of evidence.**")
        
    await mcp_client.close()

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.title("HayMagnet 🧲")
    st.header("Case Selection")
    
    if df is not None:
        case_ids = df['case_id'].tolist()
        selected_case_id = st.selectbox("Select a Case ID:", case_ids, disabled=st.session_state.is_running)
        
        selected_row = df[df['case_id'] == selected_case_id].iloc[0]
        
        st.divider()
        st.subheader("Case Metadata")
        st.write(f"**Timestamp:** {selected_row.get('ts', 'N/A')}")
        st.write(f"**Trigger Type:** {selected_row.get('trigger_type', 'N/A')}")
        
        risk_score = selected_row.get('risk_score', 'N/A')
        st.metric("Risk Score", risk_score)
        
    else:
        st.error("Could not find HHGOA_IEEE/case_pack.csv")
        st.stop()

# ==========================================
# MAIN PANEL
# ==========================================
st.title("🤖 Autonomous Fraud Investigator")
st.markdown("Watch the multi-agent system investigate TigerGraph in real-time.")

st.info(f"**Trigger Alert:** {selected_row['trigger_text']}")

if st.button("Unleash Agents 🚀", use_container_width=True, type="primary", disabled=st.session_state.is_running):
    st.session_state.is_running = True
    
    # We must use asyncio.run to kick off the async loop in sync Streamlit
    try:
        asyncio.run(run_investigation_ui(selected_row))
    except Exception as e:
        st.error(f"Investigation failed: {e}")
    finally:
        st.session_state.is_running = False
        st.rerun() # Refresh the page to re-enable the button
