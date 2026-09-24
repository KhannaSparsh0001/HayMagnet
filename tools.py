import os
import sys
import shutil
from contextlib import AsyncExitStack
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google.genai import types

def clean_schema(schema):
    """Cleans standard JSON schema keys that Gemini's strict OpenAPI validator rejects."""
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for k, v in schema.items():
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

def convert_mcp_to_openai_schema(mcp_tool):
    """Translates the TigerGraph MCP tool JSON schema into the standard OpenAI format.
       Used by Groq SDK and Hugging Face InferenceClient.
    """
    safe_schema = clean_schema(mcp_tool.input_schema)
    return {
        "type": "function",
        "function": {
            "name": mcp_tool.name,
            "description": mcp_tool.description,
            "parameters": safe_schema
        }
    }

class TigerGraphMCPClient:
    """A wrapper class to manage the lifecycle of the TigerGraph MCP server."""
    
    def __init__(self):
        self.session = None
        self._exit_stack = None

    async def connect(self):
        """Starts the local MCP server as a subprocess and establishes a session."""
        self._exit_stack = AsyncExitStack()
        
        mcp_executable = shutil.which("tigergraph-mcp") or (
            os.path.join(sys.prefix, "Scripts", "tigergraph-mcp.exe") if sys.platform == "win32" else "tigergraph-mcp"
        )
        
        server_params = StdioServerParameters(
            command=mcp_executable,
            args=[],
            env=os.environ.copy() # Passes TG_HOST and TG_SECRET from .env automatically
        )
        
        stdio_cm = stdio_client(server_params)
        self._read, self._write = await self._exit_stack.enter_async_context(stdio_cm)
        
        session_cm = ClientSession(self._read, self._write)
        self.session = await self._exit_stack.enter_async_context(session_cm)
        
        await self.session.initialize()

    async def get_allowed_tools(self):
        """Fetches the available tools and filters them down to the essential graph tools."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected. Call connect() first.")
            
        tools_response = await self.session.list_tools()
        allowed_tools = [
            "tigergraph__gsql", 
            "tigergraph__get_node", 
            "tigergraph__get_node_edges", 
            "tigergraph__get_graph_schema",
            "tigergraph__show_graph_details",
            "tigergraph__get_neighbors",
            "tigergraph__run_query"
        ]
        return [t for t in tools_response.tools if t.name in allowed_tools]

    async def execute_tool(self, tool_name, args_dict):
        """Executes a tool on the TigerGraph MCP server and returns the result as a string."""
        if not self.session:
            raise RuntimeError("MCP Client is not connected. Call connect() first.")
            
        try:
            mcp_result = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments=args_dict),
                timeout=45.0
            )
            return str(mcp_result.content)
        except asyncio.TimeoutError:
            return f"Error: Tool execution timed out after 45 seconds."
        except Exception as e:
            return f"Error executing tool: {e}"

    async def close(self):
        """Cleanly shuts down the MCP server process."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self.session = None
