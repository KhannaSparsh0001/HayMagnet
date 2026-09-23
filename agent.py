import os
import sys
import asyncio
import pandas as pd
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types

load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
    print("Please add it: GEMINI_API_KEY=your_google_ai_studio_key")
    sys.exit(1)

# Initialize new Google GenAI SDK
ai = genai.Client(api_key=gemini_api_key)

def get_fraud_rules():
    rules_file = "fraud_rules.txt"
    if not os.path.exists(rules_file):
        raise FileNotFoundError(f"Missing {rules_file}. Please run extract_rules.py first!")
        
    with open(rules_file, "r", encoding="utf-8") as f:
        return f.read()

def clean_schema(schema):
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for k, v in schema.items():
        # Gemini's strict OpenAPI validator rejects these standard JSON schema keys
        if k in ["examples", "default", "title", "$ref", "$defs"]:
            continue
        if isinstance(v, dict):
            cleaned[k] = clean_schema(v)
        elif isinstance(v, list):
            cleaned[k] = [clean_schema(item) for item in v]
        else:
            cleaned[k] = v
    return cleaned

def convert_mcp_tool_to_gemini(mcp_tool):
    """Translates the TigerGraph MCP tool JSON schema into a Gemini Function Declaration."""
    safe_schema = clean_schema(mcp_tool.input_schema)
    return types.FunctionDeclaration(
        name=mcp_tool.name,
        description=mcp_tool.description,
        parameters=safe_schema
    )

import time
from google.genai import errors

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

async def investigate_case(session, case_trigger, tools, rules):
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
    
    # Configure Gemini with our translated MCP tools
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[{"function_declarations": gemini_tools}],
        temperature=0.0
    )
    
    # Use the fastest, most capable reasoning model
    chat = ai.chats.create(model="gemini-3.6-flash", config=config)
    
    response = send_message_with_retry(chat, case_trigger)
    
    # The Tool Calling Loop (Bridging Gemini to the MCP Server)
    while response.function_calls:
        tool_responses = []
        for fc in response.function_calls:
            print(f"> Gemini is running TigerGraph Tool: {fc.name}()")
            
            # Execute the tool on the TigerGraph MCP server
            # Convert args to a dict (Gemini provides a structured object or dict)
            args_dict = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else fc.args
            
            try:
                mcp_result = await session.call_tool(fc.name, arguments=args_dict)
                tool_output = str(mcp_result.content)
            except Exception as e:
                tool_output = f"Error executing tool: {e}"
                
            # Accumulate the database results
            tool_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": tool_output}
                )
            )
            
        # Send all accumulated responses back to Gemini in a single message
        response = send_message_with_retry(chat, tool_responses)
            
    final_text = response.text
    if not final_text:
        final_text = f"[No text in response. Raw response: {response}]"
        
    print(f"\nFINAL VERDICT:\n{final_text}\n")

async def main():
    print("Starting TigerGraph MCP server...")
    
    # Launch the TigerGraph MCP server in the background
    mcp_executable = os.path.join(sys.prefix, "Scripts", "tigergraph-mcp.exe") if sys.platform == "win32" else "tigergraph-mcp"
    
    server_params = StdioServerParameters(
        command=mcp_executable,
        args=[],
        env=os.environ.copy() # Passes TG_HOST and TG_SECRET from .env automatically
    )
    
    rules = get_fraud_rules()
    
    # Connect the MCP Client to the Server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            tools_response = await session.list_tools()
            
            # Filter the 69 tools down to just what the Agent needs for investigation
            allowed_tools = [
                "tigergraph__gsql", 
                "tigergraph__get_node", 
                "tigergraph__get_node_edges", 
                "tigergraph__get_graph_schema",
                "tigergraph__run_query"
            ]
            tools = [t for t in tools_response.tools if t.name in allowed_tools]
            print(f"Connected! Loaded {len(tools)} graph tools: {[t.name for t in tools]}\n")
            
            # Load the cases
            df = pd.read_csv("HHGOA_IEEE/case_pack.csv")
            
            # Let's test it on the very first case
            first_case = df.iloc[0]['trigger_text']
            await investigate_case(session, first_case, tools, rules)

if __name__ == "__main__":
    asyncio.run(main())
