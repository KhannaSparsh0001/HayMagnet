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
# PHASE 3: LIVE CHAT UI
# ==========================================

async def run_investigation_ui(case_row):
    case_trigger = case_row['trigger_text']
    case_id = case_row['case_id']
    
    with st.status("🔌 Connecting to TigerGraph MCP Server...", expanded=True) as status:
        mcp_client = TigerGraphMCPClient()
        await mcp_client.connect()
        
        rules = get_fraud_rules()
        tools = await mcp_client.get_allowed_tools()
        status.update(label=f"✅ Connected! Loaded {len(tools)} graph tools.", state="complete", expanded=False)
    
    st.markdown(f"### 🔍 Investigating Case: `{case_id}`")
    st.divider()
    
    db_evidence = ""
    critic_feedback = ""
    max_turns = 8
    
    for turn in range(max_turns):
        with st.chat_message("assistant", avatar="🤖"):
            st.markdown(f"**Agent 2 (Lead Investigator) - Turn {turn+1}**")
            with st.spinner("Analyzing rules and evidence..."):
                action = agent2_planner(case_trigger, rules, db_evidence, feedback=critic_feedback)
            critic_feedback = "" 
            
            if "Final Verdict:" in action or turn == max_turns - 1:
                st.markdown(action)
                
                with st.chat_message("assistant", avatar="🕵️‍♂️"):
                    st.markdown("**Agent 3 (Senior Overseer)**")
                    with st.spinner("Reviewing verdict logic against fraud rules..."):
                        review = agent3_critic(action, db_evidence, rules)
                    
                    if "APPROVED" in review or turn == max_turns - 1:
                        st.success("✅ **Verdict Approved by Overseer!**")
                        
                        st.markdown("### 🛑 FINAL STRUCTURED VERDICT")
                        json_result = format_final_verdict(action, case_id)
                        if json_result:
                            try:
                                parsed = json.loads(json_result)
                                decision = parsed.get("decision", "Unknown")
                                reasoning = parsed.get("reasoning", "")
                                
                                if "Fraud" in decision:
                                    st.error(f"### 🚨 {decision}\n\n**Reasoning:** {reasoning}")
                                else:
                                    st.success(f"### ✅ {decision}\n\n**Reasoning:** {reasoning}")
                                    
                                with st.expander("Raw JSON"):
                                    st.json(parsed)
                            except:
                                st.write(json_result)
                        else:
                            st.warning("⚠️ JSON formatting failed.")
                        
                        await mcp_client.close()
                        return
                    else:
                        st.error(f"🚨 **Verdict Rejected:** {review}")
                        critic_feedback = review
                        continue 
                
            requested_data = action.replace('Data Request:', '').strip()
            st.markdown(f"**Data Request:** _{requested_data}_")
            
        with st.chat_message("assistant", avatar="⚡"):
            st.markdown("**Agent 1 (DB Expert)**")
            with st.spinner("Executing TigerGraph queries via MCP..."):
                new_evidence = await agent1_db_expert(mcp_client, action, tools)
            
            db_evidence += f"\nRequest: {action}\nResult: {new_evidence}\n"
            
            with st.expander(f"📊 Retrieved {len(new_evidence)} characters of graph data"):
                st.code(new_evidence, language="json")
                
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
    
    try:
        asyncio.run(run_investigation_ui(selected_row))
    except Exception as e:
        st.error(f"Investigation failed: {e}")
    finally:
        st.session_state.is_running = False
        st.rerun()
