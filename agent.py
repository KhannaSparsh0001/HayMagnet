import os
import sys
import asyncio
import pandas as pd
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq

# Import our new modularized tools
from tools import TigerGraphMCPClient, convert_mcp_tool_to_gemini
import time
from google.genai import errors

load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
    print("Please add it: GEMINI_API_KEY=your_google_ai_studio_key")
    sys.exit(1)

# Initialize Google GenAI SDK (Agent 1 Primary)
ai = genai.Client(api_key=gemini_api_key)

# Initialize Groq for the JSON formatting
groq_api_key = os.getenv("GROQ_API_KEY")
if groq_api_key and groq_api_key != "your_groq_api_key_here":
    groq_client = Groq(api_key=groq_api_key)
else:
    groq_client = None

def get_fraud_rules():
    rules_file = "fraud_rules.txt"
    if not os.path.exists(rules_file):
        raise FileNotFoundError(f"Missing {rules_file}. Please run extract_rules.py first!")
        
    with open(rules_file, "r", encoding="utf-8") as f:
        return f.read()

def send_message_with_retry(chat, message, max_retries=8):
    """Wraps Gemini calls with a 30s backoff for Free Tier limits and server overloads."""
    for attempt in range(max_retries):
        try:
            return chat.send_message(message)
        except errors.APIError as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "503" in error_str or "UNAVAILABLE" in error_str:
                print(f"[API Overload/Limit Hit] Sleeping 30s (Attempt {attempt+1}/{max_retries})...")
                time.sleep(32)
            else:
                raise e
    raise Exception("Max retries exceeded for Gemini API.")

# ==============================================================================
# PHASE 2: TRIAGE & JSON FORMATTING FOUNDATIONS
# ==============================================================================

def triage_case(row):
    """
    Evaluates the CSV row to determine if the case is worth the LLM compute cost.
    Returns True if suspicious (trigger agents), False if low risk (skip).
    """
    trigger_type = row.get('trigger_type', '')
    
    # Customer reports are always investigated
    if trigger_type == 'customer_report':
        return True
        
    # Automated risk score models
    if trigger_type == 'risk_score':
        try:
            score = float(row.get('risk_score', 0))
            if score < 0.5:
                print(f"Skipping {row.get('case_id')}: Risk score ({score}) below threshold.")
                return False
        except (ValueError, TypeError):
            pass # Play it safe if score is corrupted
            
    return True # Default to investigate

def format_final_verdict(verdict_text, case_id):
    """Uses Groq's fast Llama 3 8B model to extract structured JSON from the unstructured verdict."""
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
        
        # Save to file
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

async def investigate_case(mcp_client, case_trigger, tools, rules):
    print(f"\n==============================================")
    print(f"INVESTIGATING CASE: {case_trigger}")
    print(f"==============================================\n")
    
    system_instruction = f"""
    You are an elite fraud investigator acting as a graph database agent.
    You have direct access to a TigerGraph database containing Customers, Cards, and Transactions.
    The name of the graph is `FraudGraph`.
    
    Your job is to evaluate closed cases to determine if they are fraudulent.
    You MUST adhere strictly to the Bank's Fraud Rules (R1-R10) below:
    
    {rules}
    
    Instructions:
    1. Read the trigger text and use your TigerGraph tools to extract and traverse the graph. Always use `FraudGraph` when a graph name is required (e.g. in GSQL queries `USE GRAPH FraudGraph`).
    2. Write queries to look for patterns matching R1-R10.
    3. Once you have a conclusion, output a final JSON decision exactly like this:
    {{
        "decision": "Confirmed Fraud" | "False Positive",
        "reasoning": "Detailed explanation citing the specific R-rule and the graph evidence."
    }}
    """
    
    gemini_tools = [convert_mcp_tool_to_gemini(t) for t in tools]
    
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[{"function_declarations": gemini_tools}],
        temperature=0.0
    )
    
    chat = ai.chats.create(model="gemini-2.5-flash", config=config)
    
    response = send_message_with_retry(chat, case_trigger)
    
    # The Tool Calling Loop (Bridging Gemini to the MCP Server)
    while response.function_calls:
        tool_responses = []
        for fc in response.function_calls:
            print(f"> Gemini is running TigerGraph Tool: {fc.name}()")
            
            args_dict = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else fc.args
            
            tool_output = await mcp_client.execute_tool(fc.name, args_dict)
                
            tool_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": tool_output}
                )
            )
            
        response = send_message_with_retry(chat, tool_responses)
            
    final_text = response.text
    if not final_text:
        final_text = f"[No text in response. Raw response: {response}]"
        
    print(f"\nUNSTRUCTURED VERDICT:\n{final_text}\n")
    return final_text

async def main():
    print("Starting TigerGraph MCP server...")
    
    mcp_client = TigerGraphMCPClient()
    await mcp_client.connect()
    
    rules = get_fraud_rules()
    
    tools = await mcp_client.get_allowed_tools()
    print(f"Connected! Loaded {len(tools)} graph tools: {[t.name for t in tools]}\n")
    
    df = pd.read_csv("HHGOA_IEEE/case_pack.csv")
    first_row = df.iloc[0]
    first_case_trigger = first_row['trigger_text']
    first_case_id = first_row['case_id']
    
    # Phase 2: Triage Test
    should_investigate = triage_case(first_row)
    
    if should_investigate:
        # Phase 1: Investigation Test
        unstructured_verdict = await investigate_case(mcp_client, first_case_trigger, tools, rules)
        
        # Phase 2: JSON Formatting Test
        format_final_verdict(unstructured_verdict, first_case_id)
    else:
        print(f"Case {first_case_id} was triaged as low risk. Skipping investigation.")
    
    await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())
