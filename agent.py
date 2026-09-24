import os
import time
import sys
import asyncio
import pandas as pd
import json
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
if not gemini_api_key:
    print("ERROR: GEMINI_API_KEY not found in .env file!")
    sys.exit(1)
ai = genai.Client(api_key=gemini_api_key)

# Setup Groq (Primary Planner, Critic & Formatter)
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key and groq_api_key != "your_groq_api_key_here" else None
async_groq_client = AsyncGroq(api_key=groq_api_key) if groq_api_key and groq_api_key != "your_groq_api_key_here" else None

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
    """Groq GPT-OSS 120B acts as the Lead Investigator, yielding chunks asynchronously."""
    if not async_groq_client:
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
    stream = await async_groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0,
        stream=True
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content

async def async_agent3_critic(verdict, db_evidence, rules):
    """Async Groq Overseer."""
    if not async_groq_client:
        return "APPROVED"
        
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
    completion = await async_groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "system", "content": prompt}],
        temperature=0.0
    )
    return completion.choices[0].message.content

async def async_format_final_verdict(verdict_text, case_id, is_inconclusive=False):
    """Uses AsyncGroq to extract structured JSON from the unstructured verdict."""
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
        completion = await async_groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0
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
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": data_request}
    ]
    
    try:
        response = await async_groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=groq_tools,
            temperature=0.0
        )
        
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or "No relevant evidence returned by Groq fallback model."
            
        messages.append(msg)
        
        for tool_call in msg.tool_calls:
            args_dict = json.loads(tool_call.function.arguments)
            if ui_callback:
                ui_callback(tool_call.function.name, args_dict)
            else:
                print(f"  [Groq Fallback] Running {tool_call.function.name}...")
                
            tool_output = await mcp_client.execute_tool(tool_call.function.name, args_dict)
            
            messages.append({
                "role": "tool",
                "name": tool_call.function.name,
                "content": str(tool_output),
                "tool_call_id": tool_call.id
            })
            
        final_resp = await async_groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            temperature=0.0
        )
        return final_resp.choices[0].message.content or "Database query complete."
    except Exception as e:
        return f"Groq Fallback tool execution error: {e}"

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
        completion = await async_groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.0
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Investigation incomplete: Encountered system errors during database retrieval and analysis trace ({e})."

async def agent1_db_expert(mcp_client, data_request, tools, ui_callback=None):
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
    
    # Try gemini-2.5-flash primary
    chat = ai.chats.create(model="gemini-2.5-flash", config=config)
    
    try:
        if ui_callback:
            ui_callback("STATUS_UPDATE", {"status": "Waiting for Gemini to plan tools..."})
        print(f"[{time.strftime('%H:%M:%S')}] Sending request to Gemini 2.5 Flash...")
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
                    model="gemini-2.5-flash", 
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
