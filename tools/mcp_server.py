"""Minimal stdio MCP server for the domain-neutral LLM WIKI tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.wiki_tool import TOOLS


def configure_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def tool(name: str, title: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None, write: bool = False) -> dict[str, Any]:
    return {
        "name": name, "title": title, "description": description,
        "inputSchema": {"type": "object", "properties": properties or {}, **({"required": required} if required else {})},
        "annotations": {"readOnlyHint": not write, "destructiveHint": False, "idempotentHint": not write},
    }


TOOL_SCHEMAS = [
    tool("list_pages", "List Wiki Pages", "List every Markdown Wiki page and its metadata."),
    tool("search_wiki", "Search Wiki", "Search page titles, content, and metadata.", {"query": {"type": "string"}, "limit": {"type": "integer", "default": 8}}, ["query"]),
    tool("read_page", "Read Wiki Page", "Read one complete Markdown page.", {"path": {"type": "string"}}, ["path"]),
    tool("page_summary", "Summarize Wiki Page", "Return a page summary, key points, and metadata.", {"path": {"type": "string"}}, ["path"]),
    tool("suggest_links", "Suggest Links", "Find related pages that may be linked.", {"path": {"type": "string"}, "limit": {"type": "integer", "default": 6}}, ["path"]),
    tool("list_raw_items", "List Raw Items", "List pending and processed source materials."),
    tool("store_raw_item", "Store Raw Item", "Store one base64 MD, TXT, or PDF in the inbox.", {"filename": {"type": "string"}, "content_base64": {"type": "string"}}, ["filename", "content_base64"], True),
    tool("read_raw_item", "Read Raw Item", "Extract text from one source material.", {"path": {"type": "string"}}, ["path"]),
    tool("draft_page_from_raw", "Draft Wiki Page", "Create a schema-compliant draft without changing the Wiki.", {
        "path": {"type": "string"}, "page_type": {"type": "string", "enum": ["note", "concept", "guide", "reference", "project", "journal"], "default": "note"},
        "title": {"type": "string", "default": ""}, "tags": {"type": "string", "default": "imported"},
    }, ["path"]),
    tool("source_trace", "Trace Source", "Trace a Wiki page to its raw source and verification date.", {"path": {"type": "string"}}, ["path"]),
    tool("validate_wiki", "Validate Wiki", "Check metadata, required sections, sources, links, and duplicate titles."),
    tool("upsert_page", "Publish Wiki Page", "Create or update an approved Markdown page and finalize its raw source.", {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"], True),
]


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": request_id}
    payload["error" if error else "result"] = error or result
    return payload


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method, request_id = message.get("method"), message.get("id")
    if method == "notifications/initialized": return None
    if method == "initialize":
        return response(request_id, {"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "llm-wiki", "title": "LLM WIKI MCP Server", "version": "4.0.0"}})
    if method == "tools/list": return response(request_id, {"tools": TOOL_SCHEMAS})
    if method == "tools/call":
        params = message.get("params") or {}
        name, arguments = params.get("name", ""), params.get("arguments") or {}
        if name not in TOOLS:
            return response(request_id, error={"code": -32601, "message": f"unknown tool: {name}"})
        try:
            data = TOOLS[name](**arguments)
            return response(request_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}], "structuredContent": {"data": data}, "isError": False})
        except Exception as exc:
            return response(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
    return response(request_id, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> None:
    configure_stdio()
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            output = dispatch(json.loads(line))
        except Exception as exc:
            output = response(None, error={"code": -32603, "message": str(exc)})
        if output is not None:
            print(json.dumps(output, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
