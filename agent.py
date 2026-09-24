import os
import sys
import asyncio
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types

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
            
            # Execute tool using our new wrapper client
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
        
    print(f"\nFINAL VERDICT:\n{final_text}\n")

async def main():
    print("Starting TigerGraph MCP server...")
    
    mcp_client = TigerGraphMCPClient()
    await mcp_client.connect()
    
    rules = get_fraud_rules()
    
    tools = await mcp_client.get_allowed_tools()
    print(f"Connected! Loaded {len(tools)} graph tools: {[t.name for t in tools]}\n")
    
    df = pd.read_csv("HHGOA_IEEE/case_pack.csv")
    first_case = df.iloc[0]['trigger_text']
    
    await investigate_case(mcp_client, first_case, tools, rules)
    
    await mcp_client.close()

if __name__ == "__main__":
    asyncio.run(main())
