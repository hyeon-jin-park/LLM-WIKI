"""Chat assistant grounded in MCP Wiki evidence.

Codex CLI is optional. When it is unavailable, a deterministic local assistant
still handles common Wiki operations and returns approval-gated edit drafts.
"""

from __future__ import annotations

import json
import posixpath
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


def _normalize_markdown_body(body: str) -> str:
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for line in text.split("\n"):
        stripped_right = line.rstrip()
        stripped = stripped_right.lstrip()
        indent = stripped_right[: len(stripped_right) - len(stripped)]
        bullet_match = re.match(r"^[\uf06f•●▪◦○]\s*(.+)$", stripped)
        if bullet_match:
            lines.append(f"{indent}- {bullet_match.group(1).strip()}")
            continue
        numbered_bullet = re.match(r"^([0-9]+)[.)]\s+(.+)$", stripped)
        if numbered_bullet and not stripped.startswith(tuple(f"{i}." for i in range(1, 10))):
            lines.append(f"{indent}{numbered_bullet.group(1)}. {numbered_bullet.group(2).strip()}")
            continue
        lines.append(stripped_right)

    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"\n(#{1,6}\s+)", r"\n\n\1", normalized)
    normalized = re.sub(r"(#{1,6}\s+[^\n]+)\n(?!\n)", r"\1\n\n", normalized)
    return normalized.strip()


def _ensure_title(body: str) -> str:
    if re.search(r"^#\s+.+$", body, re.MULTILINE):
        return body
    return "# Wiki Page\n\n" + body.strip()


def _ensure_required_sections(body: str) -> str:
    required = {
        "## Summary": "이 페이지의 핵심 맥락을 짧게 적어 두세요.",
        "## Key Points": "- 원본에서 확인한 주요 내용을 유지하세요.",
        "## Source": "- 원본 자료를 확인하세요.",
        "## Related Pages": "",
        "## User Questions": "- 이 자료를 보고 어떤 질문에 답할 수 있나요?",
        "## Maintenance Notes": "- 원본과 대조해 날짜, 이름, 수치, 고유명사를 확인하세요.",
    }
    output = body.rstrip()
    for heading, placeholder in required.items():
        if re.search(rf"^{re.escape(heading)}\s*$", output, re.MULTILINE):
            continue
        output += f"\n\n{heading}\n\n{placeholder}".rstrip()
    return output


def _polish_markdown(content: str) -> str:
    frontmatter, body = _split_frontmatter(content)
    polished = _ensure_required_sections(_ensure_title(_normalize_markdown_body(body)))
    return (frontmatter + polished).rstrip() + "\n"


def _pick_page_type(query: str) -> str:
    lower = query.casefold()
    for page_type in ("concept", "guide", "reference", "project", "journal", "note"):
        if page_type in lower:
            return page_type
    if "개념" in lower:
        return "concept"
    if "가이드" in lower or "방법" in lower:
        return "guide"
    if "참고" in lower or "레퍼런스" in lower:
        return "reference"
    if "프로젝트" in lower:
        return "project"
    if "기록" in lower or "저널" in lower:
        return "journal"
    return "note"


def _relative_wiki_link(from_path: str, to_path: str) -> str:
    source_dir = posixpath.dirname(from_path.removeprefix("wiki/")) or "."
    target = to_path.removeprefix("wiki/")
    return posixpath.relpath(target, source_dir)


def _insert_related_links(content: str, page_path: str, links: list[dict[str, Any]]) -> str:
    frontmatter, body = _split_frontmatter(content)
    body = _ensure_required_sections(_ensure_title(_normalize_markdown_body(body)))
    link_lines = [f"- [{item['title']}]({_relative_wiki_link(page_path, item['path'])})" for item in links]
    related = _section(body, "## Related Pages")
    existing = {line.strip() for line in related.splitlines() if line.strip()}
    merged = related.rstrip()
    for line in link_lines:
        if line not in existing:
            merged += ("\n" if merged else "") + line
    replacement = f"## Related Pages\n\n{merged.strip()}".rstrip()
    updated = re.sub(r"^## Related Pages\s*$[\s\S]*?(?=^##\s+|\Z)", replacement + "\n\n", body, count=1, flags=re.MULTILINE)
    return (frontmatter + updated).rstrip() + "\n"


def _local_answer(call_tool: ToolCaller, query: str, page_path: str = "") -> dict[str, Any]:
    evidence, sources, calls = _collect_context(call_tool, query, page_path)
    lower = query.casefold()

    wants_draft = any(word in lower for word in ("초안", "draft", "페이지 만들어", "정리해줘", "wiki로")) and any(word in lower for word in ("원본", "자료", "raw", "파일"))

    if any(word in lower for word in ("원본 목록", "자료 목록", "raw 목록", "inbox", "저장된 자료")) and not wants_draft:
        raw_items = call_tool("list_raw_items", {})
        calls.append({"tool": "list_raw_items", "arguments": {}})
        if not raw_items:
            answer = "아직 저장된 원본 자료가 없습니다. `+ 자료 추가`로 파일을 넣으면 제가 초안 생성까지 이어서 도와줄 수 있습니다."
        else:
            lines = ["저장된 원본 자료입니다."]
            for item in raw_items[:8]:
                pages = item.get("wiki_pages") or []
                linked = f" → {', '.join(pages)}" if pages else ""
                lines.append(f"- {item['name']} · {item['status']} · `{item['path']}`{linked}")
            answer = "\n".join(lines)
        return {"answer": answer, "sources": sources, "tool_calls": calls, "engine": "local-mcp", "read_only": True}

    if wants_draft:
        raw_items = call_tool("list_raw_items", {})
        calls.append({"tool": "list_raw_items", "arguments": {}})
        candidates = [item for item in raw_items if item.get("status") == "pending"] or raw_items
        if not candidates:
            return {
                "answer": "초안을 만들 원본 자료가 없습니다. 먼저 `+ 자료 추가`로 파일을 저장해 주세요.",
                "sources": sources,
                "tool_calls": calls,
                "engine": "local-mcp",
                "read_only": True,
            }
        raw = candidates[0]
        draft = call_tool("draft_page_from_raw", {"path": raw["path"], "page_type": _pick_page_type(query), "title": "", "tags": "imported"})
        calls.append({"tool": "draft_page_from_raw", "arguments": {"path": raw["path"], "page_type": _pick_page_type(query), "title": "", "tags": "imported"}})
        return {
            "answer": f"`{raw['name']}`로 Wiki 초안을 준비했습니다.\n\n아래 **초안 열기**를 누르면 자료 추가 화면의 검토 단계로 이동합니다. 아직 저장하지 않았고, 내용을 확인한 뒤 `승인하고 Wiki에 저장`을 눌러야 반영됩니다.",
            "sources": [],
            "tool_calls": calls,
            "engine": "local-mcp",
            "read_only": True,
            "action": {
                "type": "apply_import_draft",
                "label": "초안 열기",
                "path": draft["suggested_path"],
                "raw_path": draft["raw"]["path"],
                "content": draft["content"],
            },
        }

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

    if any(word in lower for word in ("링크 추가", "링크 넣", "관련 링크", "연결해", "link add")) and page_path:
        links = call_tool("suggest_links", {"path": page_path.removeprefix("wiki/"), "limit": 6})
        calls.append({"tool": "suggest_links", "arguments": {"path": page_path.removeprefix("wiki/"), "limit": 6}})
        if not links:
            return {"answer": "현재 페이지에 넣을 만한 관련 링크를 찾지 못했습니다. Wiki 페이지가 더 쌓이면 자동 연결이 더 좋아집니다.", "sources": sources, "tool_calls": calls, "engine": "local-mcp", "read_only": True}
        page = call_tool("read_page", {"path": page_path.removeprefix("wiki/")})
        calls.append({"tool": "read_page", "arguments": {"path": page_path.removeprefix("wiki/")}})
        suggestion = _insert_related_links(page["content"], page["path"], links)
        answer = "관련 페이지 후보를 `Related Pages` 섹션에 넣은 편집안을 만들었습니다.\n\n" + "\n".join(f"- {item['title']}" for item in links)
        return {
            "answer": answer + "\n\n아래 버튼으로 편집기에 적용한 뒤 저장 여부를 결정하세요.",
            "sources": [{"title": item["title"], "path": item["path"]} for item in links],
            "tool_calls": calls,
            "engine": "local-mcp",
            "read_only": True,
            "action": {"type": "apply_edit_suggestion", "label": "링크안 적용", "path": page["path"], "content": suggestion},
        }

    if any(word in lower for word in ("요약", "핵심", "summary", "brief")) and page_path:
        summary = call_tool("page_summary", {"path": page_path.removeprefix("wiki/")})
        calls.append({"tool": "page_summary", "arguments": {"path": page_path.removeprefix("wiki/")}})
        answer = f"**{summary['title']}**\n\n{summary.get('summary') or 'Summary가 비어 있습니다.'}\n\n**Key Points**\n{summary.get('key_points') or '- 핵심 포인트가 비어 있습니다.'}"
        return {"answer": answer, "sources": [{"title": summary["title"], "path": summary["path"]}], "tool_calls": calls, "engine": "local-mcp", "read_only": True}

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
            "answer": "현재 페이지를 **요약하지 않고**, 원문을 보존하는 방식으로 보기 좋게 다듬은 제안을 만들었습니다.\n\n공백, bullet, heading, 필수 섹션만 정리했고 바로 저장하지는 않았습니다. 아래 **편집기에 적용**을 누르면 편집 화면에 들어가고, 내용을 확인한 뒤 `저장 및 검증`을 누르면 반영됩니다.",
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
        "꾸며", "정리", "다듬", "보기 좋", "format", "polish", "초안", "draft",
        "원본", "자료 목록", "raw", "inbox", "요약", "핵심",
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
