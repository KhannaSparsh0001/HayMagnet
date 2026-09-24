import streamlit as st
import pandas as pd
import requests
import json
import os
import time

BACKEND_URL = "http://127.0.0.1:8000"

# Page configuration
st.set_page_config(
    page_title="HayMagnet - AI Fraud Investigation Platform",
    page_icon="🧲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Glassmorphism CSS & Strict Dark Theme Enforcement across all themes
st.markdown("""
<style>
    /* Force Dark Theme across Main & Sidebar regardless of browser light/dark mode */
    html, body, .stApp, .main, [data-testid="stSidebar"], section[data-testid="stSidebar"] {
        background-color: #0b0f19 !important;
        background: radial-gradient(circle at 50% 0%, #111827, #0b0f19) !important;
        color: #e2e8f0 !important;
    }
    
    /* Ensure sidebar text and containers are crisp dark slate */
    [data-testid="stSidebar"] {
        background-color: #0f172a !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    [data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    
    /* Input fields and selectbox dropdowns dark theme styling */
    div[data-baseweb="input"], div[data-baseweb="select"], .stTextInput input, .stSelectbox div {
        background-color: #1e293b !important;
        color: #f8fafc !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
    }
    
    .metric-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px;
        backdrop-filter: blur(10px);
        margin-bottom: 12px;
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-success { background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; }
    .badge-warning { background-color: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; }
    .badge-error { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid #ef4444; }
    .badge-info { background-color: rgba(0, 242, 254, 0.2); color: #00f2fe; border: 1px solid #00f2fe; }
    .rule-pill-pass { background-color: #064e3b; color: #34d399; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
    .rule-pill-fail { background-color: #7f1d1d; color: #f87171; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; margin-right: 4px; }
</style>
""", unsafe_allow_html=True)

# Wait for server health on boot
def wait_for_backend(max_retries=3):
    for i in range(max_retries):
        try:
            res = requests.get(f"{BACKEND_URL}/", timeout=1)
            if res.status_code == 200:
                return True, res.json()
        except Exception:
            time.sleep(0.5)
    return False, {}

server_online, server_info = wait_for_backend()

# Fetch cases from Backend API
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

# ==============================================================================
# SIDEBAR: SYSTEM STATUS & DYNAMIC MODEL CONFIGURATION
# ==============================================================================
with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    else:
        st.title("HayMagnet 🧲")
        
    st.markdown("### System Status")
    if server_online:
        st.markdown(f'<span class="status-badge badge-success">🟢 Backend Online ({server_info.get("tools_count", 0)} MCP Tools Active)</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-badge badge-error">🔴 Backend Offline</span>', unsafe_allow_html=True)
        st.info("Run server in terminal: `python server.py`")

    st.divider()
    
    # ⚙️ API KEYS & PER-AGENT MODEL SELECTION
    st.markdown("### ⚙️ API Keys & Model Providers")
    
    gemini_key = st.text_input("Google Gemini API Key", value=os.getenv("GEMINI_API_KEY", ""), type="password")
    groq_key = st.text_input("Groq API Key", value=os.getenv("GROQ_API_KEY", ""), type="password")
    hf_key = st.text_input("Hugging Face Token (HF_TOKEN)", value=os.getenv("HF_TOKEN", ""), type="password")

    has_gemini = bool(gemini_key and gemini_key != "your_gemini_api_key_here")
    has_groq = bool(groq_key and groq_key != "your_groq_api_key_here")
    has_hf = bool(hf_key and hf_key != "your_huggingface_token_here")

    # Build dynamic model option list based on active keys
    gemini_models = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"] if has_gemini else []
    groq_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "llama-3.3-70b-versatile"] if has_groq else []
    hf_models = ["meta-llama/Meta-Llama-3-70B-Instruct", "mistralai/Mixtral-8x7B-Instruct-v0.1"] if has_hf else []

    available_models = []
    if has_gemini: available_models.extend(gemini_models)
    if has_groq: available_models.extend(groq_models)
    if has_hf: available_models.extend(hf_models)
    available_models.append("✨ Custom Model (Specify)...")

    if not has_gemini and not has_groq and not has_hf:
        st.warning("⚠️ Enter a Gemini, Groq, or Hugging Face API Key above to enable model selection.")
        agent1_model, agent2_model, agent3_model = "gemini-2.5-flash", "openai/gpt-oss-120b", "openai/gpt-oss-120b"
    else:
        st.markdown("#### Per-Agent Preferred Models")
        
        # Smart pre-selection index helpers
        def get_default_idx(target_model, model_list):
            if target_model in model_list:
                return model_list.index(target_model)
            return 0

        idx1 = get_default_idx("gemini-2.5-flash", available_models)
        idx2 = get_default_idx("openai/gpt-oss-120b", available_models)
        idx3 = get_default_idx("openai/gpt-oss-120b", available_models)

        agent1_choice = st.selectbox("🤖 Agent 1 (DB Expert):", options=available_models, index=idx1)
        agent2_choice = st.selectbox("🕵️ Agent 2 (Lead Analyst):", options=available_models, index=idx2)
        agent3_choice = st.selectbox("⚖️ Agent 3 (Senior Overseer):", options=available_models, index=idx3)

        # Handle Custom Model Specification & Live Testing
        def resolve_custom_model(choice, label, default_name):
            if choice == "✨ Custom Model (Specify)...":
                col1, col2 = st.columns([3, 1])
                with col1:
                    custom_name = st.text_input(f"Custom ID for {label}:", value=default_name)
                with col2:
                    st.write("")
                    st.write("")
                    if st.button("⚡ Test", key=f"test_{label}"):
                        with st.spinner("Pinging..."):
                            try:
                                prov = "gemini" if "gemini" in custom_name else ("hf" if ("llama" in custom_name or "mistral" in custom_name) else "groq")
                                key_used = gemini_key if prov == "gemini" else (hf_key if prov == "hf" else groq_key)
                                res = requests.get(
                                    f"{BACKEND_URL}/api/test-model",
                                    params={"provider": prov, "model_name": custom_name, "api_key": key_used},
                                    timeout=10
                                )
                                data = res.json()
                                if data.get("ok"):
                                    st.success("✅ Valid!")
                                else:
                                    st.error(f"❌ {data.get('error', 'Failed')}")
                            except Exception as e:
                                st.error(f"Error: {e}")
                return custom_name
            return choice

        agent1_model = resolve_custom_model(agent1_choice, "Agent 1", "gemini-2.5-flash")
        agent2_model = resolve_custom_model(agent2_choice, "Agent 2", "openai/gpt-oss-120b")
        agent3_model = resolve_custom_model(agent3_choice, "Agent 3", "openai/gpt-oss-120b")

    st.divider()
    
    # CASE SELECTOR
    st.markdown("### Case Selection")
    if df is not None and not df.empty:
        case_ids = df['case_id'].tolist()
        selected_case_id = st.selectbox("Select Benchmark Case:", case_ids)
        selected_row = df[df['case_id'] == selected_case_id].iloc[0]
    else:
        st.error("Could not load case dataset.")
        st.stop()

# ==============================================================================
# MAIN PANEL: TABBED NAVIGATION
# ==============================================================================
st.title("🧲 HayMagnet — Autonomous Fraud Investigator")
st.markdown("Multi-Agent Graph Reasoning powered by TigerGraph MCP & Deterministic Policy Validation.")

tab_single, tab_batch = st.tabs(["🔍 Live Single-Case Investigation", "📊 20-Case Batch Auditor"])

# ------------------------------------------------------------------------------
# TAB 1: LIVE SINGLE-CASE INVESTIGATION
# ------------------------------------------------------------------------------
with tab_single:
    col_meta1, col_meta2, col_meta3 = st.columns(3)
    with col_meta1:
        st.markdown(f"**Case ID:** `{selected_case_id}`")
        st.markdown(f"**Trigger Type:** `{selected_row.get('trigger_type', 'N/A')}`")
    with col_meta2:
        st.markdown(f"**Timestamp:** `{selected_row.get('ts', 'N/A')}`")
        score = float(selected_row.get('risk_score', 0))
        badge_cls = "badge-error" if score > 70 else ("badge-warning" if score > 30 else "badge-success")
        st.markdown(f'**Risk Score:** <span class="status-badge {badge_cls}">{score:.1f} / 100</span>', unsafe_allow_html=True)
    with col_meta3:
        st.markdown(f"**Agent 1 Model:** `{agent1_model}`")
        st.markdown(f"**Agent 2 Model:** `{agent2_model}`")
        st.markdown(f"**Agent 3 Model:** `{agent3_model}`")

    st.info(f"🚨 **Trigger Alert:** {selected_row['trigger_text']}")

    def run_investigation_stream(case_id):
        st.markdown("---")
        st.markdown(f"### ⚡ Executing Agent Workflow for `{case_id}`")
        
        query_params = {
            "gemini_key": gemini_key,
            "groq_key": groq_key,
            "hf_key": hf_key,
            "agent1_model": agent1_model,
            "agent2_model": agent2_model,
            "agent3_model": agent3_model
        }

        try:
            response = requests.get(
                f"{BACKEND_URL}/api/investigate/{case_id}",
                params=query_params,
                stream=True,
                timeout=300
            )
        except Exception as e:
            st.error(f"Failed to connect to backend server: {e}")
            return

        current_event = None
        planner_container = None
        planner_text = ""

        try:
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

                    # Handle Events
                    if current_event == "turn_start":
                        turn = data.get("turn", 1)
                        st.markdown(f"#### 🔄 Turn {turn}")
                        planner_container = st.empty()
                        planner_text = ""

                    elif current_event == "planner_chunk":
                        chunk = data.get("chunk", "")
                        planner_text += chunk
                        if planner_container:
                            planner_container.markdown(f"🤖 **Lead Analyst (Agent 2 - `{agent2_model}`):**\n\n{planner_text}")

                    elif current_event == "data_request":
                        req = data.get("request", "")
                        st.info(f"⚡ **Data Request to DB Expert:** _{req}_")

                    elif current_event == "tool_exec":
                        t_name = data.get("tool_name", "")
                        t_args = data.get("args", {})
                        st.caption(f"🔧 **TigerGraph Tool Call:** `{t_name}` params: `{json.dumps(t_args)}`")

                    elif current_event == "evidence_retrieved":
                        ev = data.get("evidence", "")
                        length = data.get("evidence_length", 0)
                        with st.expander(f"📊 Agent 1 Retrieved {length} chars of Graph Evidence"):
                            st.code(ev, language="json")

                    elif current_event == "critic_start":
                        st.caption(f"🕵️‍♂️ **Overseer (Agent 3 - `{agent3_model}`):** Reviewing verdict logic...")

                    elif current_event == "critic_review":
                        review = data.get("review", "")
                        approved = data.get("approved", False)
                        if approved:
                            st.success(f"✅ **Overseer Approved Verdict:**\n\n{review}")
                        else:
                            st.error(f"🚨 **Overseer Rejected Verdict:**\n\n{review}")

                    elif current_event == "final_verdict":
                        st.markdown("---")
                        st.markdown("### 🛑 FINAL DETERMINISTIC VERDICT & AUDIT REPORT")
                        json_raw = data.get("json_verdict")
                        if json_raw:
                            try:
                                parsed = json.loads(json_raw)
                                case_data = parsed.get("case", {})
                                verdict = case_data.get("verdict", "uncertain")
                                prob = case_data.get("fraud_probability", 0.0)
                                exposure = case_data.get("exposure_usd", 0.0)
                                pattern = case_data.get("pattern", "none")
                                summary = case_data.get("summary", "")
                                
                                actions = parsed.get("next_best_actions", {})
                                route = actions.get("final", {}).get("action", "L1_MANUAL_REVIEW")

                                col_v1, col_v2, col_v3 = st.columns(3)
                                with col_v1:
                                    v_badge = "badge-error" if verdict == "fraud" else ("badge-success" if verdict == "legitimate" else "badge-warning")
                                    st.markdown(f'**Final Verdict:** <span class="status-badge {v_badge}">{verdict.upper()}</span>', unsafe_allow_html=True)
                                with col_v2:
                                    st.markdown(f"**Fraud Probability:** `{prob*100:.1f}%`")
                                    st.markdown(f"**Total Exposure:** `${exposure:,.2f}`")
                                with col_v3:
                                    r_badge = "badge-error" if "SAR" in route or "L2" in route else ("badge-success" if "AUTO" in route else "badge-warning")
                                    st.markdown(f'**Approval Route:** <span class="status-badge {r_badge}">{route}</span>', unsafe_allow_html=True)

                                st.markdown("#### 🛡️ Deterministic Fraud Policy Rules (R1 - R10)")
                                r_cols = st.columns(5)
                                rules_fired = []
                                if prob >= 0.8: rules_fired.append("R1: High Fraud Prob")
                                if exposure >= 2500: rules_fired.append("R3: Exposure > $2,500")
                                if pattern != "none": rules_fired.append(f"R5: Pattern ({pattern})")
                                
                                for idx in range(1, 11):
                                    r_key = f"R{idx}"
                                    is_triggered = any(r_key in rf for rf in rules_fired)
                                    with r_cols[(idx-1)%5]:
                                        pill_cls = "rule-pill-fail" if is_triggered else "rule-pill-pass"
                                        st.markdown(f'<span class="{pill_cls}">{r_key}: {"TRIGGERED" if is_triggered else "PASS"}</span>', unsafe_allow_html=True)

                                st.markdown("#### 📝 Executive Evidence Summary")
                                st.write(summary)

                                with st.expander("📄 View Full Pydantic Benchmark JSON"):
                                    st.json(parsed)

                            except Exception as ex:
                                st.warning(f"Raw Verdict JSON parsing error: {ex}")
                                st.write(json_raw)

                    elif current_event == "complete":
                        st.balloons()
        except Exception as e:
            st.error(f"Error during stream execution: {e}")

    if st.button("Unleash Agents 🚀", use_container_width=True, type="primary", disabled=not server_online):
        run_investigation_stream(selected_case_id)

# ------------------------------------------------------------------------------
# TAB 2: 20-CASE BATCH AUDITOR
# ------------------------------------------------------------------------------
with tab_batch:
    st.markdown("### 📊 Autonomous 20-Case Benchmark Suite")
    st.markdown("Execute all benchmark cases sequentially through the multi-agent pipeline.")

    if st.button("▶️ Run Full 20-Case Benchmark Suite", type="primary", disabled=not server_online):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_list = []

        for idx, row in df.iterrows():
            c_id = row['case_id']
            status_text.markdown(f"⏳ **Investigating Case {idx+1}/20:** `{c_id}`...")
            progress_bar.progress((idx + 1) / len(df))

            try:
                res = requests.get(
                    f"{BACKEND_URL}/api/investigate/{c_id}",
                    params={
                        "gemini_key": gemini_key,
                        "groq_key": groq_key,
                        "hf_key": hf_key,
                        "agent1_model": agent1_model,
                        "agent2_model": agent2_model,
                        "agent3_model": agent3_model
                    },
                    stream=True,
                    timeout=300
                )
                
                final_json_str = ""
                for l in res.iter_lines():
                    if not l: continue
                    s = l.decode('utf-8')
                    if s.startswith('event: final_verdict'):
                        next_line = next(res.iter_lines(), b'').decode('utf-8')
                        if next_line.startswith('data: '):
                            final_json_str = json.loads(next_line[6:]).get('json_verdict', '')
                
                if final_json_str:
                    p = json.loads(final_json_str)
                    c_det = p.get('case', {})
                    results_list.append({
                        "Case ID": c_id,
                        "Verdict": c_det.get('verdict', 'N/A'),
                        "Fraud Prob": f"{c_det.get('fraud_probability', 0)*100:.1f}%",
                        "Exposure USD": f"${c_det.get('exposure_usd', 0):,.2f}",
                        "Pattern": c_det.get('pattern', 'N/A'),
                        "Status": c_det.get('status', 'N/A')
                    })
                else:
                    results_list.append({
                        "Case ID": c_id, "Verdict": "Inconclusive", "Fraud Prob": "N/A", "Exposure USD": "$0.00", "Pattern": "N/A", "Status": "Error"
                    })
            except Exception as err:
                results_list.append({
                    "Case ID": c_id, "Verdict": "Error", "Fraud Prob": "N/A", "Exposure USD": "$0.00", "Pattern": "N/A", "Status": str(err)
                })

        status_text.success("✅ **Benchmark Run Completed across all 20 cases!**")
        res_df = pd.DataFrame(results_list)
        st.dataframe(res_df, use_container_width=True)

        csv_data = res_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Benchmark Audit Results CSV",
            data=csv_data,
            file_name="investigation_results.csv",
            mime="text/csv"
        )
