"""Reusable stdio MCP client for the GUI and tests."""

from __future__ import annotations

import json
import os
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
        self._stderr_tail: list[str] = []
        self._stderr_thread: threading.Thread | None = None
        self._process: subprocess.Popen[str] | None = None
        self._start_process()
        with self._lock:
            self.server_info = self._initialize_unlocked()

    def _start_process(self) -> None:
        self._close_process_pipes()
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self._process = subprocess.Popen(
            [sys.executable, str(ROOT / "tools" / "mcp_server.py")], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1, env=env,
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _close_process_pipes(self) -> None:
        process = self._process
        if not process:
            return
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass

    def _drain_stderr(self) -> None:
        process = self._process
        if not process or not process.stderr:
            return
        for line in process.stderr:
            self._stderr_tail.append(line.rstrip())
            self._stderr_tail = self._stderr_tail[-20:]

    def _diagnostics(self) -> str:
        process = self._process
        code = None if process is None else process.poll()
        details = f"MCP server process exited with code {code}."
        if self._stderr_tail:
            details += " stderr: " + " | ".join(self._stderr_tail[-5:])
        return details

    def _ensure_process(self) -> None:
        if self._process is None or self._process.poll() is not None:
            self._start_process()
            self.server_info = self._initialize_unlocked()

    def _request_unlocked(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_process()
        request_id = self._next_id
        self._next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        process = self._process
        assert process and process.stdin and process.stdout
        try:
            process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
            process.stdin.flush()
            line = process.stdout.readline()
        except BrokenPipeError as exc:
            raise RuntimeError(self._diagnostics()) from exc
        if not line:
            raise RuntimeError(self._diagnostics())
        response = json.loads(line)
        if "error" in response:
            raise RuntimeError(response["error"]["message"])
        return response["result"]

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            return self._request_unlocked(method, params)

    def _notify_unlocked(self, method: str) -> None:
        self._ensure_process()
        assert self._process and self._process.stdin
        try:
            self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": {}}) + "\n")
            self._process.stdin.flush()
        except BrokenPipeError as exc:
            raise RuntimeError(self._diagnostics()) from exc

    def _notify(self, method: str) -> None:
        with self._lock:
            self._notify_unlocked(method)

    def _initialize_unlocked(self) -> dict[str, Any]:
        result = self._request_unlocked("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "llm-wiki-gui", "title": "LLM WIKI GUI", "version": "4.0.0"},
        })
        self._notify_unlocked("notifications/initialized")
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
        process = self._process
        if process and process.poll() is None:
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
        self._close_process_pipes()


__all__ = ["MCPClient"]
