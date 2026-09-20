import os
import sys
import asyncio
import pandas as pd
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai
from google.genai import types
import PyPDF2

load_dotenv()

gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
    print("Please add it: GEMINI_API_KEY=your_google_ai_studio_key")
    sys.exit(1)

# Initialize new Google GenAI SDK
ai = genai.Client(api_key=gemini_api_key)

def get_fraud_rules():
    print("Extracting fraud rules from PDF...")
    # Read the rules directly from the PDF you provided earlier
    pdf_path = r"C:\Users\khann\.gemini\antigravity-ide\brain\b8687f02-95f5-4011-8161-68c87ffd03b1\.tempmediaStorage\media_1789898966134.pdf"
    if not os.path.exists(pdf_path):
        print(f"Warning: Rules PDF not found at {pdf_path}")
        return "No specific rules provided."
    text = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def convert_mcp_tool_to_gemini(mcp_tool):
    """Translates the TigerGraph MCP tool JSON schema into a Gemini Function Declaration."""
    return types.FunctionDeclaration(
        name=mcp_tool.name,
        description=mcp_tool.description,
        parameters=mcp_tool.inputSchema
    )

async def investigate_case(session, case_trigger, tools, rules):
    print(f"\n==============================================")
    print(f"🕵️ INVESTIGATING CASE: {case_trigger}")
    print(f"==============================================\n")
    
    system_instruction = f"""
    You are an elite fraud investigator acting as a graph database agent.
    You have direct access to a TigerGraph database containing Customers, Cards, and Transactions.
    
    Your job is to evaluate closed cases to determine if they are fraudulent.
    You MUST adhere strictly to the Bank's Fraud Rules (R1-R10) below:
    
    {rules}
    
    Instructions:
    1. Read the trigger text and use your TigerGraph tools to extract and traverse the graph.
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
    chat = ai.chats.create(model="gemini-2.5-flash", config=config)
    
    response = chat.send_message(case_trigger)
    
    # The Tool Calling Loop (Bridging Gemini to the MCP Server)
    while response.function_calls:
        for fc in response.function_calls:
            print(f"🤖 Gemini is running TigerGraph Tool: {fc.name}()")
            
            # Execute the tool on the TigerGraph MCP server
            # Convert args to a dict (Gemini provides a structured object or dict)
            args_dict = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else fc.args
            
            try:
                mcp_result = await session.call_tool(fc.name, arguments=args_dict)
                tool_output = str(mcp_result.content)
            except Exception as e:
                tool_output = f"Error executing tool: {e}"
                
            # Send the database results back to Gemini
            tool_response = types.Part.from_function_response(
                name=fc.name,
                response={"result": tool_output}
            )
            response = chat.send_message(tool_response)
            
    print(f"\n✅ FINAL VERDICT:\n{response.text}\n")

async def main():
    print("Starting TigerGraph MCP server...")
    
    # Launch the TigerGraph MCP server in the background
    server_params = StdioServerParameters(
        command="tigergraph-mcp",
        args=[],
        env=os.environ.copy() # Passes TG_HOST and TG_SECRET from .env automatically
    )
    
    rules = get_fraud_rules()
    
    # Connect the MCP Client to the Server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            tools_response = await session.list_tools()
            tools = tools_response.tools
            print(f"Connected! Loaded {len(tools)} graph tools (e.g., {[t.name for t in tools]}).\n")
            
            # Load the cases
            df = pd.read_csv("HHGOA_IEEE/case_pack.csv")
            
            # Let's test it on the very first case
            first_case = df.iloc[0]['trigger_text']
            await investigate_case(session, first_case, tools, rules)

if __name__ == "__main__":
    asyncio.run(main())
