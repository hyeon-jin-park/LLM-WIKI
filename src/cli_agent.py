"""Optional read-only Codex CLI chat grounded in MCP Wiki evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ToolCaller = Callable[[str, dict[str, Any] | None], Any]


def agent_status() -> dict[str, Any]:
    binary = shutil.which("codex")
    return {
        "available": bool(binary),
        "provider": "codex-cli" if binary else "none",
        "binary": Path(binary).name if binary else "",
        "read_only": True,
    }


def _collect_context(call_tool: ToolCaller, question: str, page_path: str = "") -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, str]] = []
    calls: list[dict[str, Any]] = []

    def use(name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        result = call_tool(name, args)
        calls.append({"tool": name, "arguments": args})
        return result

    pages = use("list_pages")
    if page_path:
        try:
            current = use("page_summary", {"path": page_path.removeprefix("wiki/")})
            evidence.append(current)
            sources.append({"title": current["title"], "path": current["path"]})
        except (FileNotFoundError, RuntimeError, ValueError):
            pass

    results = use("search_wiki", {"query": question, "limit": 5}) if pages else []
    known = {source["path"] for source in sources}
    for item in results[:4]:
        if item["path"] in known:
            continue
        summary = use("page_summary", {"path": item["path"].removeprefix("wiki/")})
        evidence.append(summary)
        sources.append({"title": summary["title"], "path": summary["path"]})
        known.add(item["path"])
    return evidence, sources, calls


def answer_with_codex(call_tool: ToolCaller, question: str, page_path: str = "", history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    query = question.strip()
    if not query:
        raise ValueError("질문을 입력해 주세요.")
    binary = shutil.which("codex")
    if not binary:
        raise RuntimeError("Codex CLI가 설치되어 있지 않습니다. 외부 MCP Agent를 연결하거나 Codex CLI를 설치해 주세요.")

    evidence, sources, calls = _collect_context(call_tool, query, page_path)
    recent = [
        {"role": item.get("role"), "content": str(item.get("content", ""))[:1200]}
        for item in (history or [])[-6:] if item.get("role") in {"user", "assistant"}
    ]
    prompt = f"""You are the read-only chat assistant inside LLM WIKI.
Answer naturally in Korean unless the user asks for another language.
The application already retrieved Wiki evidence through MCP. Base factual claims about the user's knowledge base only on that evidence.
If the Wiki is empty or evidence is missing, say so clearly. You may explain how to use LLM WIKI using README.md.
Never edit files, run write operations, or claim that a page was created or changed. Direct write requests to the visible 자료 추가 or 편집 approval flow.
Do not reveal chain-of-thought. Give a concise final answer and mention relevant Wiki page names when evidence exists.

Current page: {page_path or 'none'}
Recent conversation: {json.dumps(recent, ensure_ascii=False)}
MCP Wiki evidence: {json.dumps(evidence, ensure_ascii=False)}
User question: {query}
"""
    completed = subprocess.run(
        [binary, "exec", "--ephemeral", "--sandbox", "read-only", "-C", str(ROOT), "-"],
        input=prompt, text=True, capture_output=True, timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "Codex CLI 실행에 실패했습니다.")[-700:])
    answer = completed.stdout.strip()
    if not answer:
        raise RuntimeError("Codex CLI가 빈 응답을 반환했습니다.")
    return {"answer": answer, "sources": sources, "tool_calls": calls, "engine": "codex-cli", "read_only": True}


__all__ = ["agent_status", "answer_with_codex"]
