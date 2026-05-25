"""Run MCP server: python -m kb_agent.mcp_server"""
from pathlib import Path
from kb_agent.mcp_server.server import run_server

if __name__ == "__main__":
    run_server(Path(".kb"))
