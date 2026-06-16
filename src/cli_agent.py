"""Chat assistant grounded in MCP Wiki evidence.

Codex CLI is optional. When it is unavailable, a deterministic local assistant
still handles common Wiki operations and returns approval-gated edit drafts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import re
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
ToolCaller = Callable[[str, dict[str, Any] | None], Any]


def agent_status() -> dict[str, Any]:
    binary = _find_codex()
    return {
        "available": True,
        "provider": "codex-cli" if binary else "local-mcp",
        "binary": Path(binary).name if binary else "",
        "codex_available": bool(binary),
        "read_only": True,
    }


def _find_codex() -> str | None:
    for name in ("codex", "codex.cmd", "codex.exe"):
        binary = shutil.which(name)
        if binary:
            return binary
    return None


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


def _split_frontmatter(content: str) -> tuple[str, str]:
    if not content.startswith("---\n"):
        return "", content
    end = content.find("\n---\n", 4)
    if end < 0:
        return "", content
    return content[:end + 5], content[end + 5:].lstrip()


def _section(body: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _polish_markdown(content: str) -> str:
    frontmatter, body = _split_frontmatter(content)
    title_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Wiki Page"
    summary = _section(body, "## Summary")
    key_points = _section(body, "## Key Points")
    source = _section(body, "## Source")
    related = _section(body, "## Related Pages")
    questions = _section(body, "## User Questions")
    notes = _section(body, "## Maintenance Notes")

    bullets = []
    for line in key_points.splitlines():
        cleaned = line.strip()
        if cleaned.startswith(("-", "*")):
            bullets.append("- " + cleaned[1:].strip())
    if not bullets and summary:
        bullets = ["- 핵심 내용을 한 문장씩 다시 정리하세요.", "- 원본에서 확인 가능한 사실만 남기세요."]

    polished = f"""# {title}

## Summary

{summary or "이 페이지는 원본 자료에서 추출한 핵심 내용을 정리하기 위한 Wiki 문서입니다."}

## Key Points

{chr(10).join(bullets[:8])}

## Source

{source or "- 원본 자료를 확인하세요."}

## Related Pages

{related}

## User Questions

{questions or "- 이 자료에서 가장 먼저 확인해야 할 내용은 무엇인가요?\n- 이후에 연결할 관련 문서는 무엇인가요?"}

## Maintenance Notes

{notes or "- 원본과 대조해 날짜, 이름, 수치, 고유명사를 확인하세요.\n- 필요한 경우 관련 페이지 링크를 추가하세요."}
"""
    return (frontmatter + polished).rstrip() + "\n"


def _local_answer(call_tool: ToolCaller, query: str, page_path: str = "") -> dict[str, Any]:
    evidence, sources, calls = _collect_context(call_tool, query, page_path)
    lower = query.casefold()

    if any(word in lower for word in ("검증", "validate", "검사")):
        validation = call_tool("validate_wiki", {})
        calls.append({"tool": "validate_wiki", "arguments": {}})
        state = "통과" if validation.get("ok") else f"{len(validation.get('issues', []))}개 문제 발견"
        return {
            "answer": f"Wiki 검증 결과는 **{state}**입니다.\n\nPages: {validation.get('page_count', 0)}\nRaw: {validation.get('raw_count', 0)}",
            "sources": sources,
            "tool_calls": calls,
            "engine": "local-mcp",
            "read_only": True,
        }

    if any(word in lower for word in ("출처", "source", "trace")) and page_path:
        trace = call_tool("source_trace", {"path": page_path.removeprefix("wiki/")})
        calls.append({"tool": "source_trace", "arguments": {"path": page_path.removeprefix("wiki/")}})
        raw = trace.get("raw") or {}
        return {
            "answer": f"현재 페이지의 출처 연결입니다.\n\nWiki: `{trace.get('wiki_page')}`\nRaw: `{raw.get('path') or trace.get('source_url') or '연결 없음'}`\nVerified: `{trace.get('last_verified') or 'unknown'}`",
            "sources": [{"title": trace.get("title", "current page"), "path": trace.get("wiki_page", page_path)}],
            "tool_calls": calls,
            "engine": "local-mcp",
            "read_only": True,
        }

    if any(word in lower for word in ("관련", "link", "연결")) and page_path:
        links = call_tool("suggest_links", {"path": page_path.removeprefix("wiki/"), "limit": 6})
        calls.append({"tool": "suggest_links", "arguments": {"path": page_path.removeprefix("wiki/"), "limit": 6}})
        if not links:
            answer = "아직 추천할 관련 페이지가 없습니다. Wiki 페이지가 더 쌓이면 링크 추천이 유용해집니다."
        else:
            answer = "관련 후보입니다.\n\n" + "\n".join(f"- {item['title']} (`{item['path']}`)" for item in links)
        return {"answer": answer, "sources": [{"title": item["title"], "path": item["path"]} for item in links], "tool_calls": calls, "engine": "local-mcp", "read_only": True}

    if any(word in lower for word in ("꾸며", "정리", "다듬", "보기 좋", "format", "polish")) and page_path:
        page = call_tool("read_page", {"path": page_path.removeprefix("wiki/")})
        calls.append({"tool": "read_page", "arguments": {"path": page_path.removeprefix("wiki/")}})
        suggestion = _polish_markdown(page["content"])
        return {
            "answer": "현재 페이지를 더 읽기 쉬운 Markdown 구조로 다듬은 제안을 만들었습니다.\n\n바로 저장하지는 않았습니다. 아래 **편집기에 적용**을 누르면 편집 화면에 들어가고, 내용을 확인한 뒤 `저장 및 검증`을 누르면 반영됩니다.",
            "sources": [{"title": page["title"], "path": page["path"]}],
            "tool_calls": calls,
            "engine": "local-mcp",
            "read_only": True,
            "action": {"type": "apply_edit_suggestion", "label": "편집기에 적용", "path": page["path"], "content": suggestion},
        }

    if evidence:
        lines = ["Wiki에서 찾은 근거를 기준으로 답변합니다."]
        for item in evidence[:4]:
            summary = item.get("summary") or item.get("key_points") or ""
            lines.append(f"\n**{item.get('title')}**\n{summary[:420] or '요약 정보가 비어 있습니다.'}")
        return {"answer": "\n".join(lines), "sources": sources, "tool_calls": calls, "engine": "local-mcp", "read_only": True}

    pages = call_tool("list_pages", {})
    calls.append({"tool": "list_pages", "arguments": {}})
    if not pages:
        answer = "현재 Wiki는 비어 있습니다.\n\n먼저 `+ 자료 추가`로 TXT, Markdown, PDF를 넣으면 초안을 만들 수 있습니다. 초안을 검토하고 승인하면 Wiki 페이지가 생성됩니다."
    else:
        answer = f"현재 Wiki에는 {len(pages)}개 페이지가 있습니다. 구체적인 키워드로 질문하면 `search_wiki`로 관련 페이지를 찾아 답변할 수 있습니다."
    return {"answer": answer, "sources": [], "tool_calls": calls, "engine": "local-mcp", "read_only": True}


def _is_tool_command(query: str) -> bool:
    lower = query.casefold()
    return any(word in lower for word in (
        "검증", "validate", "검사", "출처", "source", "trace", "관련", "link", "연결",
        "꾸며", "정리", "다듬", "보기 좋", "format", "polish",
    ))


def answer_with_codex(call_tool: ToolCaller, question: str, page_path: str = "", history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    query = question.strip()
    if not query:
        raise ValueError("질문을 입력해 주세요.")
    if _is_tool_command(query):
        return _local_answer(call_tool, query, page_path)
    binary = _find_codex()
    if not binary:
        return _local_answer(call_tool, query, page_path)

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
        fallback = _local_answer(call_tool, query, page_path)
        fallback["answer"] = "Codex CLI 호출에 실패해서 로컬 MCP 모드로 답변합니다.\n\n" + fallback["answer"]
        fallback["codex_error"] = (completed.stderr or "Codex CLI 실행에 실패했습니다.")[-700:]
        return fallback
    answer = completed.stdout.strip()
    if not answer:
        return _local_answer(call_tool, query, page_path)
    return {"answer": answer, "sources": sources, "tool_calls": calls, "engine": "codex-cli", "read_only": True}


__all__ = ["agent_status", "answer_with_codex"]
