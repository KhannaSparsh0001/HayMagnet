import os
import time
import sys
import asyncio
import pandas as pd
import json
import re
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors
from groq import Groq, AsyncGroq
from huggingface_hub import InferenceClient

# Import our modularized tools
from tools import TigerGraphMCPClient, convert_mcp_tool_to_gemini, convert_mcp_to_openai_schema
import time

load_dotenv()

# Setup Gemini (Primary DB Agent)
gemini_api_key = os.getenv("GEMINI_API_KEY")
ai = genai.Client(api_key=gemini_api_key) if gemini_api_key and gemini_api_key != "your_gemini_api_key_here" else None
if not ai:
    print("Warning: GEMINI_API_KEY not set in .env. LLM calls requiring Gemini will require API key setup.")

# Setup Groq (Primary Planner, Critic & Formatter)
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key and groq_api_key != "your_groq_api_key_here" else None
async_groq_client = AsyncGroq(api_key=groq_api_key) if groq_api_key and groq_api_key != "your_groq_api_key_here" else None

GROQ_CANDIDATE_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]

async def async_groq_completion_with_fallback(messages, tools=None, temperature=0.0, response_format=None, candidate_models=None):
    """Executes a Groq chat completion with automatic model fallback across candidate models."""
    if not async_groq_client:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    if candidate_models is None:
        candidate_models = GROQ_CANDIDATE_MODELS
    last_err = None
    for model in candidate_models:
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if tools:
                kwargs["tools"] = tools
            if response_format:
                kwargs["response_format"] = response_format
            return await async_groq_client.chat.completions.create(**kwargs)
        except Exception as e:
            last_err = e
            print(f"  [Groq Fallback Chain] Model {model} failed: {e}. Trying next candidate...")
            continue
    raise last_err

async def async_groq_stream_with_fallback(messages, temperature=0.0, candidate_models=None):
    """Streams a Groq chat completion with automatic model fallback across candidate models."""
    if not async_groq_client:
        yield "Final Verdict: Error - GROQ_API_KEY is not configured."
        return
    if candidate_models is None:
        candidate_models = GROQ_CANDIDATE_MODELS
    for model in candidate_models:
        try:
            stream = await async_groq_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
            return
        except Exception as e:
            print(f"  [Groq Stream Chain] Model {model} failed: {e}. Trying next candidate...")
            continue
    yield "Final Verdict: Inconclusive / System Error - LLM rate limit or connection failure occurred."

# Setup Hugging Face (Fallback DB Agent)
hf_token = os.getenv("HF_TOKEN")
hf_client = InferenceClient(api_key=hf_token) if hf_token and hf_token != "your_huggingface_token_here" else None

def get_fraud_rules():
    rules_file = "fraud_rules.txt"
    if not os.path.exists(rules_file):
        raise FileNotFoundError(f"Missing {rules_file}. Please run extract_rules.py first!")
    with open(rules_file, "r", encoding="utf-8") as f:
        return f.read()

# ==============================================================================
# PHASE 2: TRIAGE & JSON FORMATTING
# ==============================================================================

def triage_case(row):
    """Evaluates the CSV row to determine if the case is worth investigating."""
    trigger_type = row.get('trigger_type', '')
    if trigger_type == 'customer_report':
        return True
    if trigger_type == 'risk_score':
        try:
            score = float(row.get('risk_score', 0))
            if score < 0.5:
                return False
        except (ValueError, TypeError):
            pass
    return True

def format_final_verdict(verdict_text, case_id):
    """Uses Groq to extract structured JSON from the unstructured verdict."""
    if not groq_client:
        print(f"⚠️ Skipping JSON formatting for {case_id} because GROQ_API_KEY is not set.")
        return None
        
    prompt = f"""
    Extract the final decision and reasoning from the following fraud investigator's verdict.
    You must return a valid JSON object strictly adhering to this schema:
    {{
        "decision": "Confirmed Fraud" or "False Positive",
        "reasoning": "A concise paragraph explaining the evidence."
    }}
    
    Verdict Text:
    {verdict_text}
    """
    
    for model_name in ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]:
        try:
            completion = groq_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            json_output = completion.choices[0].message.content
            os.makedirs("cases", exist_ok=True)
            file_path = f"cases/{case_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json_output)
            print(f"✅ Verdict for {case_id} successfully structured and saved to {file_path}")
            return json_output
        except Exception as e:
            continue
    print(f"❌ Failed to format JSON for {case_id} via Groq")
    return None

# ==============================================================================
# PHASE 3 & 4: CORE ENGINE (AGENTS 1, 2, AND 3)
# ==============================================================================

def agent2_planner(case_trigger, rules, db_evidence, feedback=""):
    """Groq GPT-OSS 120B acts as the Lead Investigator."""
    if not groq_client:
        return "Final Verdict: Error - GROQ_API_KEY is not configured."
        
    prompt = f"""
    You are the Lead Fraud Investigator. 
    Your job is to determine if this case is fraudulent based on the rules.
    
    RULES:
    {rules}
    
    CASE TRIGGER:
    {case_trigger}
    
    DATABASE EVIDENCE GATHERED SO FAR:
    {db_evidence if db_evidence else "None"}
    
    {f'OVERSEER FEEDBACK (CRITICAL): {feedback}' if feedback else ''}
    
    INSTRUCTIONS:
    If you need more information from the TigerGraph database, output exactly:
    Data Request: [Your plain english request for the DB expert, e.g., 'Find all transactions for card X']
    
    If you have enough information to make a decision based on the rules, output exactly:
    Final Verdict: [Your detailed reasoning and decision (Confirmed Fraud or False Positive)]
    """
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0
    )
    return completion.choices[0].message.content

def agent3_critic(verdict, db_evidence, rules):
    """Groq GPT-OSS 120B acts as the Senior Critic/Overseer."""
    if not groq_client:
        return "APPROVED" # Skip if no API key
        
    prompt = f"""
    You are the Senior Fraud Overseer.
    A Lead Investigator has submitted a Final Verdict for a case.
    
    RULES:
    {rules}
    
    EVIDENCE GATHERED:
    {db_evidence}
    
    SUBMITTED VERDICT:
    {verdict}
    
    INSTRUCTIONS:
    Critically analyze the verdict. Did the investigator hallucinate evidence? Did they misapply a rule?
    If the verdict is sound and logically supported by the actual evidence gathered, output exactly:
    APPROVED
    
    If the verdict is flawed, hallucinated, or incomplete, output exactly:
    REJECTED: [Detailed feedback on what the investigator needs to do instead]
    """
    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0
    )
    return completion.choices[0].message.content

def agent2_planner_stream(case_trigger, rules, db_evidence, feedback=""):
    """Groq GPT-OSS 120B acts as the Lead Investigator, yielding chunks for UI."""
    if not groq_client:
        yield "Final Verdict: Error - GROQ_API_KEY is not configured."
        return
        
    prompt = f"""
    You are the Lead Fraud Investigator. 
    Your job is to determine if this case is fraudulent based on the rules.
    
    RULES:
    {rules}
    
    CASE TRIGGER:
    {case_trigger}
    
    DATABASE EVIDENCE GATHERED SO FAR:
    {db_evidence if db_evidence else "None"}
    
    {f'OVERSEER FEEDBACK (CRITICAL): {feedback}' if feedback else ''}
    
    INSTRUCTIONS:
    If you need more information from the TigerGraph database, output exactly:
    Data Request: [Your plain english request for the DB expert, e.g., 'Find all transactions for card X']
    
    If you have enough information to make a decision based on the rules, output exactly:
    Final Verdict: [Your detailed reasoning and decision (Confirmed Fraud or False Positive)]
    """
    stream = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0,
        stream=True
    )
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content

async def async_agent2_planner_stream(case_trigger, rules, db_evidence, feedback=""):
    """Groq acts as the Lead Investigator, yielding chunks asynchronously with multi-model fallback."""
    if not async_groq_client:
        yield "Final Verdict: Error - GROQ_API_KEY is not configured."
        return
        
    capped_evidence = db_evidence[-4000:] if len(db_evidence) > 4000 else db_evidence
    
    prompt = f"""
    You are the Lead Fraud Investigator. 
    Your job is to determine if this case is fraudulent based on the rules.
    
    RULES:
    {rules}
    
    CASE TRIGGER:
    {case_trigger}
    
    DATABASE EVIDENCE GATHERED SO FAR:
    {capped_evidence if capped_evidence else "None"}
    
    {f'OVERSEER FEEDBACK (CRITICAL): {feedback}' if feedback else ''}
    
    INSTRUCTIONS:
    If you need more information from the TigerGraph database, output exactly:
    Data Request: [Your plain english request for the DB expert, e.g., 'Find all transactions for card X']
    
    If you have enough information to make a decision based on the rules, output exactly:
    Final Verdict: [Your detailed reasoning and decision (Confirmed Fraud or False Positive)]
    """
    messages = [{"role": "system", "content": prompt}]
    async for chunk in async_groq_stream_with_fallback(messages):
        yield chunk

async def async_agent3_critic(verdict, db_evidence, rules):
    """Async Groq Overseer with multi-model fallback."""
    if not async_groq_client:
        return "APPROVED"
        
    capped_evidence = db_evidence[-3000:] if len(db_evidence) > 3000 else db_evidence
    prompt = f"""
    You are the Senior Fraud Overseer.
    A Lead Investigator has submitted a Final Verdict for a case.
    
    RULES:
    {rules}
    
    EVIDENCE GATHERED:
    {capped_evidence}
    
    SUBMITTED VERDICT:
    {verdict}
    
    INSTRUCTIONS:
    Critically analyze the verdict. Did the investigator hallucinate evidence? Did they misapply a rule?
    If the verdict is sound and logically supported by the actual evidence gathered, output exactly:
    APPROVED
    
    If the verdict is flawed, hallucinated, or incomplete, output exactly:
    REJECTED: [Detailed feedback on what the investigator needs to do instead]
    """
    try:
        completion = await async_groq_completion_with_fallback([{"role": "system", "content": prompt}])
        return completion.choices[0].message.content
    except Exception as e:
        print(f"  [Critic] All Groq models failed: {e}. Defaulting to APPROVED.")
        return "APPROVED"

async def async_format_final_verdict(verdict_text, case_id, is_inconclusive=False):
    """Uses AsyncGroq with multi-model fallback to extract structured JSON from the unstructured verdict."""
    if is_inconclusive:
        json_obj = {
            "decision": "Inconclusive / System Error",
            "reasoning": verdict_text
        }
        os.makedirs("cases", exist_ok=True)
        file_path = f"cases/{case_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(json_obj, f, indent=2)
        return json.dumps(json_obj)

    if not async_groq_client:
        return None
        
    prompt = f"""
    Extract the final decision and reasoning from the following fraud investigator's verdict.
    You must return a valid JSON object strictly adhering to this schema:
    {{
        "decision": "Confirmed Fraud", "False Positive", or "Inconclusive / System Error",
        "reasoning": "A concise paragraph explaining the evidence or failure."
    }}
    
    Verdict Text:
    {verdict_text}
    """
    try:
        completion = await async_groq_completion_with_fallback(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            candidate_models=["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
        )
        json_output = completion.choices[0].message.content
        os.makedirs("cases", exist_ok=True)
        file_path = f"cases/{case_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        return json_output
    except Exception as e:
        print(f"❌ Failed to format JSON for {case_id}: {e}")
        return None

async def agent1_groq_fallback(mcp_client, data_request, tools, system_instruction, ui_callback=None):
    """Fallback tool execution using Groq API (openai/gpt-oss-120b)."""
    if not async_groq_client:
        return "Error: Groq Fallback triggered but GROQ_API_KEY is not configured."
        
    groq_tools = [convert_mcp_to_openai_schema(t) for t in tools]
    
    # Register common hallucinated aliases (both prefixed and unprefixed) so Groq API never rejects with tool_use_failed
    existing_tool_names = {t["function"]["name"] for t in groq_tools}
    
    compatibility_definitions = [
        ("tigergraph__run_gremlin_query", "Compatibility tool for graph traversal queries."),
        ("run_gremlin_query", "Compatibility tool for graph traversal queries."),
        ("tigergraph__show_graph_details", "Show details of the graph schema."),
        ("show_graph_details", "Show details of the graph schema."),
        ("get_node_edges", "Get edges connected to a vertex."),
        ("get_node", "Get vertex details."),
        ("get_neighbors", "Get neighbors of a vertex."),
        ("get_graph_schema", "Get graph schema."),
        ("run_query", "Run a TigerGraph query."),
        ("gsql", "Execute GSQL statement.")
    ]
    
    for tool_name, desc in compatibility_definitions:
        if tool_name not in existing_tool_names:
            groq_tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "graph_name": {"type": "string"},
                            "vertex_type": {"type": "string"},
                            "vertex_id": {"type": "string"},
                            "edge_type": {"type": "string"},
                            "query": {"type": "string"},
                            "command": {"type": "string"}
                        }
                    }
                }
            })

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": data_request}
    ]
    
    try:
        response = await async_groq_completion_with_fallback(
            messages=messages,
            tools=groq_tools,
            temperature=0.0
        )
        
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or "No relevant evidence returned by Groq fallback model."
            
        tool_results = []
        for tool_call in msg.tool_calls:
            t_name = tool_call.function.name
            args_dict = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
            if not isinstance(args_dict, dict):
                args_dict = {}
            
            # Map aliases and normalize tool names
            if "gremlin" in t_name.lower():
                query_str = args_dict.get("query", "")
                card_match = re.search(r"\b(C-[\w\-]+)\b", query_str) or re.search(r"\b(C-[\w\-]+)\b", data_request)
                if card_match:
                    card_id = card_match.group(1)
                    t_name = "tigergraph__get_node_edges"
                    args_dict = {
                        "graph_name": "FraudGraph",
                        "vertex_type": "Card",
                        "vertex_id": card_id,
                        "edge_type": "MADE"
                    }
                else:
                    t_name = "tigergraph__get_graph_schema"
                    args_dict = {"graph_name": "FraudGraph"}
            elif "details" in t_name.lower() or t_name in ["show_graph_details", "tigergraph__show_graph_details"]:
                t_name = "tigergraph__get_graph_schema"
                args_dict = {"graph_name": "FraudGraph"}
            elif not t_name.startswith("tigergraph__"):
                t_name = f"tigergraph__{t_name}"
                
            if ui_callback:
                ui_callback(t_name, args_dict)
            else:
                print(f"  [Groq Fallback] Running {t_name} with {args_dict}...")
                
            tool_output = await mcp_client.execute_tool(t_name, args_dict)
            tool_results.append(f"Tool `{t_name}`: {tool_output}")
            
        summary_messages = [
            {
                "role": "system",
                "content": "You are a graph database expert. Summarize the following retrieved graph database evidence to answer the investigator's question clearly. Do NOT call any tools or output JSON."
            },
            {
                "role": "user",
                "content": f"Investigator Question: {data_request}\n\nRetrieved Graph Evidence:\n{' | '.join(tool_results)}"
            }
        ]
        
        try:
            final_resp = await async_groq_completion_with_fallback(
                messages=summary_messages,
                temperature=0.0
            )
            return final_resp.choices[0].message.content or "\n".join(tool_results)
        except Exception as sum_err:
            print(f"  [Groq Fallback summary error: {sum_err}], returning raw evidence.")
            return "\n".join(tool_results)
    except Exception as e:
        error_str = str(e)
        print(f"  [Groq Fallback Exception Caught]: {error_str[:200]}")
        
        # 1. Attempt recovery from failed_generation if Groq refused an unlisted function
        failed_gen_match = re.search(r"['\"]failed_generation['\"]\s*:\s*['\"](\{.*?\})['\"]\s*\}", error_str, re.DOTALL)
        if failed_gen_match:
            try:
                gen_raw = failed_gen_match.group(1).replace("\\'", "'").replace('\\"', '"')
                parsed_gen = json.loads(gen_raw)
                p_name = parsed_gen.get("name", "")
                p_args = parsed_gen.get("arguments", {})
                if "gremlin" in p_name:
                    query_str = str(p_args)
                    c_match = re.search(r"\b(C-[\w\-]+)\b", query_str) or re.search(r"\b(C-[\w\-]+)\b", data_request)
                    if c_match:
                        edges = await mcp_client.execute_tool("tigergraph__get_node_edges", {
                            "graph_name": "FraudGraph",
                            "vertex_type": "Card",
                            "vertex_id": c_match.group(1),
                            "edge_type": "MADE"
                        })
                        return f"Retrieved transactions for card {c_match.group(1)}: {edges}"
                elif "schema" in p_name or "details" in p_name:
                    schema_res = await mcp_client.execute_tool("tigergraph__get_graph_schema", {"graph_name": "FraudGraph"})
                    return f"Retrieved FraudGraph schema: {schema_res}"
            except Exception as gen_err:
                print(f"  [Groq Fallback Failed Gen Recovery Error]: {gen_err}")
                
        # 2. Direct recovery by searching for card ID in error or original request
        card_match = re.search(r"\b(C-[\w\-]+)\b", error_str) or re.search(r"\b(C-[\w\-]+)\b", data_request)
        if card_match:
            card_id = card_match.group(1)
            print(f"  [Groq Fallback Direct Recovery] Extracting edges for card {card_id}...")
            try:
                edges = await mcp_client.execute_tool("tigergraph__get_node_edges", {
                    "graph_name": "FraudGraph",
                    "vertex_type": "Card",
                    "vertex_id": card_id,
                    "edge_type": "MADE"
                })
                return f"Retrieved transactions for card {card_id}: {edges}"
            except Exception as rec_err:
                print(f"  [Groq Fallback Recovery Edge Error]: {rec_err}")
                
        # 3. Last-resort fallback: fetch schema directly so the pipeline never halts with 400
        try:
            schema_res = await mcp_client.execute_tool("tigergraph__get_graph_schema", {"graph_name": "FraudGraph"})
            return f"FraudGraph Schema Evidence (retrieved via direct fallback): {schema_res}"
        except Exception:
            return f"Database query could not be completed for request: {data_request}"

async def async_agent_failure_analyst(case_trigger, db_evidence, last_critic_review=""):
    """Analyzes an inconclusive investigation execution trace and provides a clear human diagnostic summary."""
    if not async_groq_client:
        return "Investigation inconclusive. System encountered an error and could not complete evidence gathering."
        
    prompt = f"""
    You are an AI Forensic Analyst. An automated fraud investigation was unable to reach a conclusive decision.
    Your task is to analyze the failure trace below and explain clearly to a human fraud manager why no decision could be drawn.
    
    CASE TRIGGER:
    {case_trigger}
    
    DATABASE EVIDENCE / ERRORS ENCOUNTERED:
    {db_evidence if db_evidence else "No evidence retrieved (Database queries failed or timed out)."}
    
    LAST OVERSEER CRITIC REVIEW:
    {last_critic_review if last_critic_review else "None"}
    
    INSTRUCTIONS:
    Provide a concise, professional, human-readable summary (2-4 sentences) explaining:
    1. What step failed or why evidence was insufficient.
    2. The impact on the fraud risk assessment.
    3. What manual or system action is required next.
    Do NOT declare "Confirmed Fraud" or "False Positive". Focus strictly on diagnosing the investigation failure.
    """
    try:
        completion = await async_groq_completion_with_fallback(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.0
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Investigation incomplete: Encountered system errors during database retrieval and analysis trace ({e})."

async def agent1_db_expert(mcp_client, data_request, tools, ui_callback=None):
    """Gemini 3.6 Flash acts as the DB Expert with TigerGraph MCP Tools."""
    system_instruction = f"""
    You are an expert Graph Database Query Agent for TigerGraph.
    You have direct access to TigerGraph MCP tools for the graph `FraudGraph`.
    
    AVAILABLE TOOLS:
    1. `tigergraph__get_node_edges`: To find transactions made by a card, call with:
       vertex_type='Card', vertex_id='<card_id>', edge_type='MADE', graph_name='FraudGraph'.
       To find devices used by a transaction, call with vertex_type='Transaction', vertex_id='<tx_id>', edge_type='FROM_DEVICE'.
       To find who owns a card, call with vertex_type='Customer', vertex_id='<customer_id>', edge_type='OWNS'.
    2. `tigergraph__get_node`: To inspect vertex details for any Card, Transaction, Customer, or DeviceProfile.
    3. `tigergraph__run_query`: To run an interpreted GSQL query: `INTERPRET QUERY () FOR GRAPH FraudGraph {{ ... }}`.
    4. `tigergraph__get_graph_schema`: To view the graph structure (graph_name='FraudGraph').
    
    IMPORTANT:
    - Never invent tools. TigerGraph uses GSQL, not Gremlin.
    - Always use graph_name='FraudGraph'.
    """
    
    gemini_tools = [convert_mcp_tool_to_gemini(t) for t in tools]
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[{"function_declarations": gemini_tools}],
        temperature=0.0
    )
    
    if not ai:
        if async_groq_client:
            print("Gemini client not initialized, falling back to Groq...")
            return await agent1_groq_fallback(mcp_client, data_request, tools, system_instruction, ui_callback=ui_callback)
        if hf_client:
            print("Gemini client not initialized, falling back to Hugging Face...")
            return await agent1_hf_fallback(mcp_client, data_request, tools, system_instruction, ui_callback=ui_callback)
        return "Error: GEMINI_API_KEY is not configured in .env."

    # Try gemini-flash-latest primary
    chat = ai.chats.create(model="gemini-flash-latest", config=config)
    
    try:
        if ui_callback:
            ui_callback("STATUS_UPDATE", {"status": "Waiting for Gemini to plan tools..."})
        print(f"[{time.strftime('%H:%M:%S')}] Sending request to Gemini Flash...")
        start_time = time.time()
        
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(chat.send_message, data_request),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            print(f"[{time.strftime('%H:%M:%S')}] Error: Gemini request timed out!")
            return "Error: Database Expert timed out while planning the query."
            
        elapsed = time.time() - start_time
        print(f"[{time.strftime('%H:%M:%S')}] Gemini replied in {elapsed:.2f}s.")
        
        if not response.function_calls:
            return response.text
            
        tool_responses = []
        for fc in response.function_calls:
            args_dict = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else fc.args
            if ui_callback:
                ui_callback(fc.name, args_dict)
            else:
                print(f"  [{time.strftime('%H:%M:%S')}] [Gemini] Running {fc.name}...")
                
            tool_start = time.time()
            tool_output = await mcp_client.execute_tool(fc.name, args_dict)
            tool_elapsed = time.time() - tool_start
            print(f"  [{time.strftime('%H:%M:%S')}] [Gemini] Tool {fc.name} completed in {tool_elapsed:.2f}s.")
            tool_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": tool_output}
                )
            )
            
        if ui_callback:
            ui_callback("STATUS_UPDATE", {"status": "Gemini is synthesizing tool results..."})
            
        print(f"[{time.strftime('%H:%M:%S')}] Sending tool results back to Gemini for summary...")
        final_start = time.time()
        
        raw_results = []
        for p in tool_responses:
            if p.function_response:
                raw_results.append(str(p.function_response.response))
                
        summary_prompt = f"The database expert ran tools and got this JSON: {' | '.join(raw_results)}\n\nPlease summarize this graph data to answer the original request: {data_request}"
        
        try:
            final_resp = await asyncio.wait_for(
                asyncio.to_thread(
                    ai.models.generate_content, 
                    model="gemini-flash-latest", 
                    contents=summary_prompt,
                    config=types.GenerateContentConfig(temperature=0.0)
                ),
                timeout=60.0
            )
        except asyncio.TimeoutError:
            print(f"[{time.strftime('%H:%M:%S')}] Error: Gemini final synthesis timed out!")
            return "Error: Database Expert timed out while synthesizing the graph evidence."
            
        print(f"[{time.strftime('%H:%M:%S')}] Gemini final reply in {time.time() - final_start:.2f}s.")
        return final_resp.text
        
    except Exception as e:
        error_str = str(e)
        print(f"  [Gemini Error: {error_str}] Falling back to Groq...")
        try:
            return await agent1_groq_fallback(mcp_client, data_request, tools, system_instruction, ui_callback=ui_callback)
        except Exception as groq_err:
            return f"Error executing DB query: {error_str} (Groq Fallback error: {groq_err})"

async def investigate_case(mcp_client, case_trigger, tools, rules):
    db_evidence = ""
    critic_feedback = ""
    max_turns = 8
    
    for turn in range(max_turns):
        print(f"\n--- Turn {turn+1} ---")
        
        print("> Agent 2 (Groq) is analyzing...")
        action = agent2_planner(case_trigger, rules, db_evidence, feedback=critic_feedback)
        critic_feedback = "" # Reset feedback after use
        
        if "Final Verdict:" in action or turn == max_turns - 1:
            print(f"> Agent 2 submitted a verdict.")
            
            # Phase 4: Agent 3 Critic Review
            print("> Agent 3 (Critic) is reviewing the verdict...")
            review = agent3_critic(action, db_evidence, rules)
            
            if "APPROVED" in review or turn == max_turns - 1:
                print("> Agent 3 APPROVED the verdict.")
                return action
            else:
                print(f"> Agent 3 REJECTED the verdict: {review}")
                critic_feedback = review
                continue # Loop back to Agent 2
            
        print(f"> Agent 2 requested data: {action.replace('Data Request:', '').strip()}")
        print("> Agent 1 (Gemini/HF) is executing graph queries...")
        new_evidence = await agent1_db_expert(mcp_client, action, tools)
        
        db_evidence += f"\nRequest: {action}\nResult: {new_evidence}\n"
        print(f"> Agent 1 retrieved {len(new_evidence)} characters of evidence.")
        
    return "Final Verdict: Inconclusive (max turns reached)."

# ==============================================================================

async def main():
    print("Starting TigerGraph MCP server...")
    mcp_client = TigerGraphMCPClient()
    await mcp_client.connect()
    
    rules = get_fraud_rules()
    tools = await mcp_client.get_allowed_tools()
    print(f"Connected! Loaded {len(tools)} graph tools.")
    
    df = pd.read_csv("HHGOA_IEEE/case_pack.csv")
    
    print(f"\nStarting Batch Processing for {len(df)} cases...\n")
    
    for index, row in df.iterrows():
        case_id = row['case_id']
        case_trigger = row['trigger_text']
        
        print(f"\n=======================================================")
        print(f"PROCESSING CASE {case_id} ({index+1}/{len(df)})")
        print(f"=======================================================\n")
        
        if triage_case(row):
            try:
                unstructured_verdict = await investigate_case(mcp_client, case_trigger, tools, rules)
                format_final_verdict(unstructured_verdict, case_id)
            except Exception as e:
                print(f"❌ Unhandled error processing {case_id}: {e}")
                print("Sleeping for 10s before continuing to next case to clear API limits...")
                time.sleep(10)
        else:
            print(f"Case {case_id} triaged as low risk. Skipping investigation.")
            
    print("\n✅ BATCH PROCESSING COMPLETE!")
    await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())
