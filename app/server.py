"""Local web viewer backed exclusively by the LLM WIKI stdio MCP server."""

from __future__ import annotations

import argparse
import errno
import json
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(ROOT))
from src.mcp_client import MCPClient
from src.cli_agent import agent_status, answer_with_codex

MCP: MCPClient | None = None


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        relative = urlparse(path).path.lstrip("/") or "index.html"
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in [target, *target.parents]:
            return str(STATIC / "index.html")
        return str(target)

    def json_response(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def tool_response(self, name: str, arguments: dict | None = None) -> None:
        assert MCP is not None
        args = arguments or {}
        self.json_response(200, {"tool": name, "arguments": args, "data": MCP.call_tool(name, args)})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        if parsed.path == "/": self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error(404); return
        try:
            length = int(self.headers.get("content-length", "0"))
            if length > 15 * 1024 * 1024: raise ValueError("request exceeds 15 MB")
            body = json.loads(self.rfile.read(length) or b"{}")
            self.handle_api_post(parsed.path, body)
        except Exception as exc:
            sys.stderr.write(f"[llm-wiki] API error {parsed.path}: {exc}\n")
            self.json_response(500, {"error": str(exc)})

    def handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            assert MCP is not None
            if path == "/api/status":
                return self.json_response(200, {"server": MCP.server_info["serverInfo"], "protocolVersion": MCP.server_info["protocolVersion"], "tools": MCP.list_tools(), "validation": MCP.call_tool("validate_wiki"), "activity": MCP.history(), "agent": agent_status()})
            if path == "/api/chat/status": return self.json_response(200, agent_status())
            if path == "/api/pages": return self.tool_response("list_pages")
            if path == "/api/raw": return self.tool_response("list_raw_items")
            if path == "/api/validate": return self.tool_response("validate_wiki")
            if path == "/api/search": return self.tool_response("search_wiki", {"query": query.get("q", [""])[0], "limit": 20})
            if path == "/api/page": return self.tool_response("read_page", {"path": query.get("path", [""])[0].removeprefix("wiki/")})
            if path == "/api/suggest": return self.tool_response("suggest_links", {"path": query.get("path", [""])[0].removeprefix("wiki/"), "limit": 6})
            if path == "/api/trace": return self.tool_response("source_trace", {"path": query.get("path", [""])[0].removeprefix("wiki/")})
            self.json_response(404, {"error": "not found"})
        except Exception as exc:
            sys.stderr.write(f"[llm-wiki] API error {path}: {exc}\n")
            self.json_response(500, {"error": str(exc)})

    def handle_api_post(self, path: str, body: dict) -> None:
        assert MCP is not None
        if path == "/api/chat":
            return self.json_response(200, answer_with_codex(
                MCP.call_tool, str(body.get("question", "")), str(body.get("page_path", "")), body.get("history") or [],
            ))
        if path == "/api/raw/upload":
            return self.tool_response("store_raw_item", {"filename": str(body.get("filename", "")), "content_base64": str(body.get("content_base64", ""))})
        if path == "/api/raw/draft":
            return self.tool_response("draft_page_from_raw", {"path": str(body.get("path", "")), "page_type": str(body.get("page_type", "note")), "title": str(body.get("title", "")), "tags": str(body.get("tags", "imported"))})
        if path == "/api/raw/publish":
            target, content = str(body.get("path", "")).removeprefix("wiki/"), str(body.get("content", ""))
            if not target or not content.strip(): raise ValueError("approved path and Markdown are required")
            saved = MCP.call_tool("upsert_page", {"path": target, "content": content})
            return self.json_response(200, {"saved": saved, "validation": MCP.call_tool("validate_wiki"), "trace": MCP.call_tool("source_trace", {"path": saved["path"]})})
        if path == "/api/save":
            target, content = str(body.get("path", "")).removeprefix("wiki/"), str(body.get("content", ""))
            saved = MCP.call_tool("upsert_page", {"path": target, "content": content})
            return self.json_response(200, {"saved": saved, "validation": MCP.call_tool("validate_wiki")})
        self.json_response(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("[llm-wiki] " + format % args + "\n")


def create_server(host: str, preferred_port: int) -> ThreadingHTTPServer:
    for port in range(preferred_port, preferred_port + 20):
        try: return ThreadingHTTPServer((host, port), Handler)
        except OSError as exc:
            if exc.errno not in {errno.EADDRINUSE, errno.EACCES}: raise
    raise OSError("no available port")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM WIKI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    global MCP
    server = create_server(args.host, args.port)
    MCP = MCPClient()
    url = f"http://{args.host}:{server.server_address[1]}"
    print(f"LLM WIKI: {url}", flush=True)
    if args.open: threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nLLM WIKI stopped.")
    finally:
        server.server_close()
        if MCP: MCP.close()


if __name__ == "__main__": main()
