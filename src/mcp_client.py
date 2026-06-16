"""Reusable stdio MCP client for the GUI and tests."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class MCPClient:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_id = 1
        self._history: list[dict[str, Any]] = []
        self._process = subprocess.Popen(
            [sys.executable, "tools/mcp_server.py"], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.server_info = self._initialize()

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            if self._process.poll() is not None:
                raise RuntimeError("MCP server process is not running")
            request_id = self._next_id
            self._next_id += 1
            message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
            assert self._process.stdin and self._process.stdout
            self._process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
            line = self._process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout")
            response = json.loads(line)
            if "error" in response:
                raise RuntimeError(response["error"]["message"])
            return response["result"]

    def _notify(self, method: str) -> None:
        with self._lock:
            assert self._process.stdin
            self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": {}}) + "\n")
            self._process.stdin.flush()

    def _initialize(self) -> dict[str, Any]:
        result = self._request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "llm-wiki-gui", "title": "LLM WIKI GUI", "version": "4.0.0"},
        })
        self._notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        return self._request("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        result = self._request("tools/call", {"name": name, "arguments": args})
        if result.get("isError"):
            raise RuntimeError(result.get("content", [{}])[0].get("text", "Tool execution failed"))
        payload = result.get("structuredContent", {}).get("data")
        if payload is None:
            payload = json.loads(result["content"][0]["text"])
        self._history.append({"tool": name, "arguments": args})
        self._history = self._history[-40:]
        return payload

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def close(self) -> None:
        if self._process.poll() is None:
            if self._process.stdin:
                self._process.stdin.close()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.terminate()


__all__ = ["MCPClient"]
