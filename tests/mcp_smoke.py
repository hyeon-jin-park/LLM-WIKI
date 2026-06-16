import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.mcp_client import MCPClient


client = MCPClient()
try:
    tools = client.list_tools()
    pages = client.call_tool("list_pages")
    raw = client.call_tool("list_raw_items")
    validation = client.call_tool("validate_wiki")
    print(json.dumps({
        "server": client.server_info["serverInfo"],
        "protocol_version": client.server_info["protocolVersion"],
        "tool_count": len(tools),
        "empty_pages_ok": pages == [],
        "empty_raw_ok": raw == [],
        "validate_ok": validation["ok"] and validation["page_count"] == 0,
    }, ensure_ascii=False, indent=2))
finally:
    client.close()
