import streamlit as st
import pandas as pd
import os

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

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.title("HayMagnet 🧲")
    st.header("Case Selection")
    
    if df is not None:
        case_ids = df['case_id'].tolist()
        selected_case_id = st.selectbox("Select a Case ID:", case_ids)
        
        # Get selected row
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

# Display the trigger text prominently
st.info(f"**Trigger Alert:** {selected_row['trigger_text']}")

# The Unleash Button
if st.button("Unleash Agents 🚀", use_container_width=True, type="primary"):
    st.warning("Phase 1 Scaffolding Complete! The agents are not wired up yet. That comes in Phase 2!")
