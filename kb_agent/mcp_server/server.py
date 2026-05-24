"""MCP Server — stdio transport exposing KB tools to AI coding agents."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from kb_agent.mcp_server.tools import KBTools

# Minimal MCP stdio server (no external SDK dependency).
# Implements enough of the MCP protocol for Claude Code, Cursor, etc.


class MCPServer:
    """JSON-RPC 2.0 MCP server over stdio."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb_dir = kb_dir.resolve()
        self._tools = KBTools(kb_dir)
        self._tool_map = {
            "kb_search": ("Search symbols by name or meaning", {"query": "string", "top_k": "int"}),
            "kb_context": ("Build relevant context for a task", {"question": "string"}),
            "kb_callers": ("Find what calls a function/method", {"symbol": "string"}),
            "kb_callees": ("Find what a function/method calls", {"symbol": "string"}),
            "kb_impact": ("Analyze impact of changing a symbol", {"symbol": "string", "depth": "int"}),
            "kb_node": ("Get details about a specific symbol", {"symbol": "string"}),
            "kb_explore": ("Return source code for related symbols", {"question": "string", "top_k": "int"}),
            "kb_status": ("Check knowledge base health and statistics", {}),
            "kb_files": ("Get indexed file structure", {}),
        }

    async def run(self) -> None:
        """Run the MCP server, reading JSON-RPC from stdin, writing to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        while True:
            line = await reader.readline()
            if not line:
                break

            try:
                message = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            response = await self._handle_message(message)
            if response is not None:
                response_bytes = (json.dumps(response) + "\n").encode("utf-8")
                writer.write(response_bytes)
                await writer.drain()

    async def _handle_message(self, message: dict) -> dict | None:
        """Route JSON-RPC messages to handlers."""
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {})

        if method == "initialize":
            return self._success(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kb-agent", "version": "1.0.0"},
            })

        if method == "notifications/initialized":
            return None  # No response for notifications

        if method == "tools/list":
            tools = []
            for name, (desc, schema) in self._tool_map.items():
                props = {}
                required = []
                for pname, ptype in schema.items():
                    props[pname] = {"type": ptype, "description": f"The {pname} parameter"}
                    if ptype == "string":
                        required.append(pname)
                tools.append({
                    "name": name,
                    "description": desc,
                    "inputSchema": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                })
            return self._success(msg_id, {"tools": tools})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return await self._call_tool(msg_id, tool_name, arguments)

        if method == "ping":
            return self._success(msg_id, {})

        return self._error(msg_id, -32601, f"Method not found: {method}")

    async def _call_tool(self, msg_id, tool_name: str, arguments: dict) -> dict:
        """Execute a tool and return the result."""
        try:
            result_text = ""

            if tool_name == "kb_search":
                result_text = self._tools.kb_search(
                    query=arguments.get("query", ""),
                    top_k=arguments.get("top_k", 5),
                )
            elif tool_name == "kb_context":
                result_text = self._tools.kb_context(
                    question=arguments.get("question", ""),
                )
            elif tool_name == "kb_callers":
                result_text = self._tools.kb_callers(
                    symbol=arguments.get("symbol", ""),
                )
            elif tool_name == "kb_callees":
                result_text = self._tools.kb_callees(
                    symbol=arguments.get("symbol", ""),
                )
            elif tool_name == "kb_impact":
                result_text = self._tools.kb_impact(
                    symbol=arguments.get("symbol", ""),
                    depth=arguments.get("depth", 2),
                )
            elif tool_name == "kb_node":
                result_text = self._tools.kb_node(
                    symbol=arguments.get("symbol", ""),
                )
            elif tool_name == "kb_explore":
                result_text = self._tools.kb_explore(
                    question=arguments.get("question", ""),
                    top_k=arguments.get("top_k", 5),
                )
            elif tool_name == "kb_status":
                result_text = self._tools.kb_status()
            elif tool_name == "kb_files":
                result_text = self._tools.kb_files()
            else:
                return self._error(msg_id, -32601, f"Unknown tool: {tool_name}")

            return self._success(msg_id, {
                "content": [{"type": "text", "text": result_text}],
            })

        except Exception as e:
            return self._error(msg_id, -32603, f"Tool error: {e}")

    def _success(self, msg_id, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def _error(self, msg_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def run_server(kb_dir: Path) -> None:
    """Entry point for running the MCP server."""
    server = MCPServer(kb_dir)
    asyncio.run(server.run())
