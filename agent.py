import os
import sys
import asyncio
import pandas as pd
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors
from groq import Groq
from huggingface_hub import InferenceClient

# Import our modularized tools
from tools import TigerGraphMCPClient, convert_mcp_tool_to_gemini, convert_mcp_to_openai_schema
import time

load_dotenv()

# Setup Gemini (Primary DB Agent)
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
    sys.exit(1)
ai = genai.Client(api_key=gemini_api_key)

# Setup Groq (Primary Planner & Formatter)
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key and groq_api_key != "your_groq_api_key_here" else None

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
                print(f"Skipping {row.get('case_id')}: Risk score ({score}) below threshold.")
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
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
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
        print(f"❌ Failed to format JSON for {case_id} via Groq: {e}")
        return None

# ==============================================================================
# PHASE 3: CORE ENGINE (AGENTS 1 & 2)
# ==============================================================================

def agent2_planner(case_trigger, rules, db_evidence):
    """Groq Llama 3.1 70B acts as the Lead Investigator."""
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
    
    INSTRUCTIONS:
    If you need more information from the TigerGraph database, output exactly:
    Data Request: [Your plain english request for the DB expert, e.g., 'Find all transactions for card X']
    
    If you have enough information to make a decision based on the rules, output exactly:
    Final Verdict: [Your detailed reasoning and decision (Confirmed Fraud or False Positive)]
    """
    completion = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0
    )
    return completion.choices[0].message.content

async def agent1_hf_fallback(mcp_client, data_request, tools, system_instruction):
    """Fallback tool execution using Hugging Face Serverless API."""
    if not hf_client:
        return "Error: HF Fallback triggered but HF_TOKEN is not configured."
        
    hf_tools = [convert_mcp_to_openai_schema(t) for t in tools]
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": data_request}
    ]
    
    # Notice we don't pass tool_choice="auto" right away to ensure strict compat
    response = hf_client.chat.completions.create(
        model="meta-llama/Meta-Llama-3-70B-Instruct",
        messages=messages,
        tools=hf_tools
    )
    
    msg = response.choices[0].message
    if not msg.tool_calls:
        return msg.content
        
    messages.append(msg)
    
    for tool_call in msg.tool_calls:
        print(f"  [HF Fallback] Running {tool_call.function.name}...")
        args_dict = json.loads(tool_call.function.arguments)
        tool_output = await mcp_client.execute_tool(tool_call.function.name, args_dict)
        
        messages.append({
            "role": "tool",
            "name": tool_call.function.name,
            "content": str(tool_output),
            "tool_call_id": tool_call.id
        })
        
    final_resp = hf_client.chat.completions.create(
        model="meta-llama/Meta-Llama-3-70B-Instruct",
        messages=messages
    )
    return final_resp.choices[0].message.content

async def agent1_db_expert(mcp_client, data_request, tools):
    """Gemini 2.5 Flash acts as the DB Expert with TigerGraph MCP Tools."""
    system_instruction = f"""
    You are an expert Graph Database Query Agent. You have access to TigerGraph MCP tools.
    Your goal is to answer the Lead Investigator's data request by calling the appropriate tools.
    Always use `FraudGraph` when a graph name is required.
    """
    
    gemini_tools = [convert_mcp_tool_to_gemini(t) for t in tools]
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[{"function_declarations": gemini_tools}],
        temperature=0.0
    )
    
    chat = ai.chats.create(model="gemini-2.5-flash", config=config)
    
    try:
        response = chat.send_message(data_request)
        if not response.function_calls:
            return response.text
            
        tool_responses = []
        for fc in response.function_calls:
            print(f"  [Gemini] Running {fc.name}...")
            args_dict = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else fc.args
            tool_output = await mcp_client.execute_tool(fc.name, args_dict)
            tool_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": tool_output}
                )
            )
            
        final_resp = chat.send_message(tool_responses)
        return final_resp.text
        
    except errors.APIError as e:
        error_str = str(e)
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            print("  [API Limit] Gemini exhausted. Falling back to Hugging Face...")
            return await agent1_hf_fallback(mcp_client, data_request, tools, system_instruction)
        else:
            raise e

async def investigate_case(mcp_client, case_trigger, tools, rules):
    print(f"\n==============================================")
    print(f"INVESTIGATING CASE: {case_trigger}")
    print(f"==============================================\n")
    
    db_evidence = ""
    max_turns = 5
    
    for turn in range(max_turns):
        print(f"\n--- Turn {turn+1} ---")
        
        print("> Agent 2 (Groq) is analyzing...")
        action = agent2_planner(case_trigger, rules, db_evidence)
        
        if "Final Verdict:" in action or turn == max_turns - 1:
            print(f"> Agent 2 concluded the investigation:\n{action}")
            return action
            
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
    first_row = df.iloc[0]
    
    if triage_case(first_row):
        unstructured_verdict = await investigate_case(mcp_client, first_row['trigger_text'], tools, rules)
        format_final_verdict(unstructured_verdict, first_row['case_id'])
    else:
        print(f"Case {first_row['case_id']} triaged as low risk.")
        
    await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())
