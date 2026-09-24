import os
import sys
import json
import asyncio
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from tools import TigerGraphMCPClient
from agent import (
    get_fraud_rules, 
    init_graph_schema_strategy,
    async_agent2_planner_stream, 
    async_agent3_critic, 
    agent1_db_expert, 
    async_format_final_verdict,
    async_agent_failure_analyst
)

# Global state wrapper
class AppState:
    def __init__(self):
        self.mcp_client = None
        self.tools = []
        self.rules = ""
        self.df = None

app_state = AppState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[INIT] Starting HayMagnet Backend Server...")
    # Load dataset
    csv_path = "HHGOA_IEEE/case_pack.csv"
    if os.path.exists(csv_path):
        app_state.df = pd.read_csv(csv_path)
        print(f"[DATA] Loaded {len(app_state.df)} cases from {csv_path}")
    else:
        print(f"[WARN] Dataset {csv_path} not found.")

    # Load fraud rules
    app_state.rules = get_fraud_rules()
    print("[RULES] Loaded fraud rules.")

    # Connect to TigerGraph MCP Server
    print("[MCP] Connecting to TigerGraph MCP Server...")
    app_state.mcp_client = TigerGraphMCPClient()
    await app_state.mcp_client.connect()
    app_state.tools = await app_state.mcp_client.get_allowed_tools()
    print(f"[MCP] TigerGraph MCP Connected! {len(app_state.tools)} graph tools active.")

    # Pre-processing graph schema & query strategy
    await init_graph_schema_strategy(app_state.mcp_client)

    yield

    print("[SHUTDOWN] Shutting down HayMagnet Backend Server...")
    if app_state.mcp_client:
        await app_state.mcp_client.close()
        print("[MCP] TigerGraph MCP Client disconnected.")

app = FastAPI(title="HayMagnet Backend API", lifespan=lifespan)

# Allow CORS for local frontend execution
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def sse_format(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "service": "HayMagnet Backend API",
        "mcp_connected": app_state.mcp_client is not None,
        "tools_count": len(app_state.tools)
    }

@app.get("/api/cases")
async def list_cases():
    if app_state.df is None:
        raise HTTPException(status_code=500, detail="Dataset not loaded")
    
    clean_df = app_state.df.fillna("")
    cases = clean_df.to_dict(orient="records")
    return {"cases": cases}

@app.get("/api/investigate/{case_id}")
async def investigate_case_stream(case_id: str):
    if app_state.df is None:
        raise HTTPException(status_code=500, detail="Dataset not loaded")
        
    case_rows = app_state.df[app_state.df['case_id'] == case_id]
    if case_rows.empty:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
        
    row = case_rows.iloc[0].to_dict()
    case_trigger = row.get('trigger_text', '')

    async def event_generator():
        try:
            yield sse_format("start", {
                "case_id": case_id,
                "trigger_text": case_trigger,
                "ts": str(row.get('ts', '')),
                "trigger_type": str(row.get('trigger_type', '')),
                "risk_score": str(row.get('risk_score', ''))
            })

            db_evidence = ""
            critic_feedback = ""
            max_turns = 5
            verdict_approved = False

            for turn in range(max_turns):
                yield sse_format("turn_start", {"turn": turn + 1})
                
                # Collect Agent 2 planner streamed response
                planner_output = ""
                async for chunk in async_agent2_planner_stream(case_trigger, app_state.rules, db_evidence, feedback=critic_feedback):
                    planner_output += chunk
                    yield sse_format("planner_chunk", {"chunk": chunk, "turn": turn + 1})
                
                critic_feedback = "" # reset after use

                if "Final Verdict:" in planner_output:
                    yield sse_format("verdict_submitted", {"action": planner_output, "turn": turn + 1})

                    # Agent 3 Critic Review
                    yield sse_format("critic_start", {"turn": turn + 1})
                    review = await async_agent3_critic(planner_output, db_evidence, app_state.rules)
                    approved = "APPROVED" in review

                    yield sse_format("critic_review", {
                        "review": review,
                        "approved": approved,
                        "turn": turn + 1
                    })

                    if approved:
                        verdict_approved = True
                        json_res = await async_format_final_verdict(planner_output, case_id, mcp_client=app_state.mcp_client)
                        yield sse_format("final_verdict", {
                            "case_id": case_id,
                            "raw_verdict": planner_output,
                            "json_verdict": json_res
                        })
                        yield sse_format("complete", {"status": "success", "case_id": case_id})
                        return
                    else:
                        critic_feedback = review
                        if turn == max_turns - 1:
                            break
                        continue

                # Data request phase
                requested_data = planner_output.replace('Data Request:', '').strip()
                yield sse_format("data_request", {"request": requested_data, "turn": turn + 1})

                tool_calls_executed = []
                def ui_callback(tool_name, args):
                    if tool_name != "STATUS_UPDATE":
                        tool_calls_executed.append({"tool_name": tool_name, "args": args})

                new_evidence = await agent1_db_expert(
                    app_state.mcp_client, 
                    planner_output, 
                    app_state.tools, 
                    ui_callback=ui_callback
                )

                for t in tool_calls_executed:
                    yield sse_format("tool_exec", {"tool_name": t["tool_name"], "args": t["args"], "turn": turn + 1})

                db_evidence += f"\nRequest: {planner_output}\nResult: {new_evidence}\n"
                yield sse_format("evidence_retrieved", {
                    "evidence_length": len(new_evidence),
                    "evidence": new_evidence,
                    "turn": turn + 1
                })

            # If loop completed without an approved verdict -> Failure Analysis Agent
            failure_analysis = await async_agent_failure_analyst(case_trigger, db_evidence, critic_feedback)
            json_res = await async_format_final_verdict(failure_analysis, case_id, is_inconclusive=True, mcp_client=app_state.mcp_client)

            yield sse_format("final_verdict", {
                "case_id": case_id,
                "raw_verdict": failure_analysis,
                "json_verdict": json_res
            })
            yield sse_format("complete", {"status": "inconclusive", "case_id": case_id})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            err_msg = str(exc)
            yield sse_format("error", {"error": err_msg})
            yield sse_format("final_verdict", {
                "case_id": case_id,
                "raw_verdict": f"Investigation halted due to unexpected system error: {err_msg}",
                "json_verdict": json.dumps({
                    "decision": "Inconclusive / System Error",
                    "reasoning": f"Stream error encountered: {err_msg}"
                })
            })
            yield sse_format("complete", {"status": "error", "case_id": case_id})

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
