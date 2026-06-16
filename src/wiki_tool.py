"""Deterministic tools for a domain-neutral Markdown LLM Wiki."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
WIKI_ROOT = REPO_ROOT / "wiki"
RAW_ROOT = REPO_ROOT / "raw"
RAW_INBOX = RAW_ROOT / "inbox"
RAW_PROCESSED = RAW_ROOT / "processed"
SUPPORTED_RAW_SUFFIXES = {".md", ".txt", ".pdf"}
MAX_RAW_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 60_000
PAGE_TYPES = {"note", "concept", "guide", "reference", "project", "journal"}
PAGE_FOLDERS = {page_type: page_type + "s" for page_type in PAGE_TYPES}
REQUIRED_METADATA = ["type", "status", "tags", "last_verified", "source_url"]
REQUIRED_SECTIONS = [
    "## Summary", "## Key Points", "## Source", "## Related Pages",
    "## User Questions", "## Maintenance Notes",
]
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)(?:#[^)]+)?\)")

logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass
class SearchResult:
    path: str
    title: str
    score: int
    preview: str
    meta: dict[str, str]


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
    return metadata, text[end + 5:]


def _title(text: str, fallback: str) -> str:
    _, body = _parse_frontmatter(text)
    match = TITLE_RE.search(body)
    return match.group(1).strip() if match else fallback


def _contained(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if root.resolve() not in [target, *target.parents]:
        raise ValueError(f"path escapes allowed root: {value}")
    return target


def _wiki_path(value: str | Path) -> Path:
    return _contained(WIKI_ROOT, str(value).removeprefix("wiki/"))


def _raw_path(value: str | Path) -> Path:
    return _contained(RAW_ROOT, str(value).removeprefix("raw/"))


def _relative(path: Path) -> str:
    resolved = path.resolve()
    if WIKI_ROOT.resolve() in [resolved, *resolved.parents]:
        return "wiki/" + resolved.relative_to(WIKI_ROOT.resolve()).as_posix()
    if RAW_ROOT.resolve() in [resolved, *resolved.parents]:
        return "raw/" + resolved.relative_to(RAW_ROOT.resolve()).as_posix()
    return resolved.relative_to(REPO_ROOT.resolve()).as_posix()


def _pages() -> list[Path]:
    if not WIKI_ROOT.exists():
        return []
    return sorted(path for path in WIKI_ROOT.rglob("*.md") if not path.name.startswith("."))


def _extract_section(text: str, heading: str) -> str:
    _, body = _parse_frontmatter(text)
    match = re.search(rf"^{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)", body, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    meta, _ = _parse_frontmatter(text)
    return {"path": _relative(path), "title": _title(text, path.stem), "meta": meta}


def list_pages() -> list[dict[str, Any]]:
    return [_record(path) for path in _pages()]


def search_wiki(query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = re.findall(r"[\w가-힣]+", query.lower())
    if not terms:
        return []
    results: list[SearchResult] = []
    for path in _pages():
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        title = _title(text, path.stem)
        haystack = (body + " " + " ".join(meta.values())).lower()
        score = sum(haystack.count(term) + (5 if term in title.lower() else 0) for term in terms)
        if score:
            preview = " ".join(_extract_section(text, "## Summary").split())[:220]
            results.append(SearchResult(_relative(path), title, score, preview, meta))
    results.sort(key=lambda item: (-item.score, item.path))
    return [asdict(item) for item in results[:limit]]


def read_page(path: str) -> dict[str, Any]:
    target = _wiki_path(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"Wiki page not found: {path}")
    text = target.read_text(encoding="utf-8")
    meta, _ = _parse_frontmatter(text)
    return {"path": _relative(target), "title": _title(text, target.stem), "meta": meta, "content": text}


def page_summary(path: str) -> dict[str, Any]:
    page = read_page(path)
    return {
        "path": page["path"], "title": page["title"], "meta": page["meta"],
        "summary": _extract_section(page["content"], "## Summary"),
        "key_points": _extract_section(page["content"], "## Key Points"),
    }


def suggest_links(path: str, limit: int = 6) -> list[dict[str, Any]]:
    page = page_summary(path)
    query = " ".join([page["title"], page["summary"], page["key_points"], " ".join(page["meta"].values())])
    return [item for item in search_wiki(query, limit + 1) if item["path"] != page["path"]][:limit]


def _raw_links() -> dict[str, list[str]]:
    links: dict[str, list[str]] = {}
    for page in _pages():
        meta, _ = _parse_frontmatter(page.read_text(encoding="utf-8"))
        if meta.get("raw_source"):
            links.setdefault(meta["raw_source"], []).append(_relative(page))
    return links


def list_raw_items() -> list[dict[str, Any]]:
    links = _raw_links()
    items = []
    for folder, status in ((RAW_INBOX, "pending"), (RAW_PROCESSED, "processed")):
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and not path.name.startswith("."):
                rel = _relative(path)
                items.append({
                    "path": rel, "name": path.name, "format": path.suffix.lower().lstrip("."),
                    "bytes": path.stat().st_size, "status": status, "wiki_pages": links.get(rel, []),
                })
    return items


def store_raw_item(filename: str, content_base64: str) -> dict[str, Any]:
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        raise ValueError("filename must not contain a path")
    if Path(safe_name).suffix.lower() not in SUPPORTED_RAW_SUFFIXES:
        raise ValueError("supported raw formats are .md, .txt, and .pdf")
    try:
        payload = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if not payload:
        raise ValueError("raw item is empty")
    if len(payload) > MAX_RAW_BYTES:
        raise ValueError("raw item exceeds the 10 MB limit")
    RAW_INBOX.mkdir(parents=True, exist_ok=True)
    target = _contained(RAW_INBOX, safe_name)
    if target.exists() or (RAW_PROCESSED / safe_name).exists():
        raise ValueError(f"raw item already exists: {safe_name}")
    target.write_bytes(payload)
    return {"path": _relative(target), "name": safe_name, "bytes": len(payload), "status": "pending"}


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("text file must use UTF-8 or CP949 encoding")


def _extract_pdf(path: Path) -> tuple[str, int]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages[:40]).strip()
    except ImportError as exc:
        raise RuntimeError("PDF support requires pypdf") from exc
    except Exception as exc:
        raise ValueError(f"could not read PDF: {path.name}") from exc
    if not text:
        raise ValueError("PDF has no extractable text; scanned PDFs need OCR first")
    return text, len(reader.pages)


def read_raw_item(path: str) -> dict[str, Any]:
    target = _raw_path(path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"raw item not found: {path}")
    if target.suffix.lower() not in SUPPORTED_RAW_SUFFIXES:
        raise ValueError("unsupported raw format")
    pages = None
    if target.suffix.lower() == ".pdf":
        text, pages = _extract_pdf(target)
    else:
        text = _decode_text(target.read_bytes())
    original = len(text)
    return {
        "path": _relative(target), "name": target.name, "format": target.suffix.lower().lstrip("."),
        "text": text[:MAX_EXTRACTED_CHARS], "characters": original,
        "truncated": original > MAX_EXTRACTED_CHARS, "pages": pages,
    }


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", "-", value.lower()).strip("-")[:80] or "wiki-page"


def _plain_summary(text: str) -> str:
    cleaned = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:420] + ("..." if len(cleaned) > 420 else "")


def draft_page_from_raw(path: str, page_type: str = "note", title: str = "", tags: str = "imported") -> dict[str, Any]:
    if page_type not in PAGE_TYPES:
        raise ValueError(f"page_type must be one of: {', '.join(sorted(PAGE_TYPES))}")
    raw = read_raw_item(path)
    source_text = raw["text"].strip()
    detected = TITLE_RE.search(source_text) if raw["format"] == "md" else None
    page_title = (title or (detected.group(1).strip() if detected else Path(raw["name"]).stem.replace("-", " ").replace("_", " "))).strip()
    suggested_path = f"{PAGE_FOLDERS[page_type]}/{_slugify(page_title)}.md"
    excerpt = "\n".join(f"> {line}" if line.strip() else ">" for line in source_text[:6000].splitlines())
    content = f"""---
type: {page_type}
status: draft
tags: {tags or 'imported'}
last_verified: {date.today().isoformat()}
source_url: local://{raw['path']}
raw_source: {raw['path']}
---
# {page_title}

## Summary

{_plain_summary(source_text)}

## Key Points

- Review and replace this generated excerpt with reusable knowledge.

{excerpt}

## Source

- `{raw['path']}`

## Related Pages

## User Questions

- What can this page help a future reader answer?

## Maintenance Notes

- Verify names, dates, and claims before publishing.
"""
    return {"raw": {key: raw[key] for key in ("path", "name", "format", "characters", "pages")}, "suggested_path": suggested_path, "content": content}


def source_trace(path: str) -> dict[str, Any]:
    page = read_page(path)
    raw_path = page["meta"].get("raw_source", "")
    raw = None
    if raw_path:
        try:
            raw = read_raw_item(raw_path)
        except FileNotFoundError:
            raw = {"path": raw_path, "missing": True}
    return {
        "wiki_page": page["path"], "title": page["title"], "status": page["meta"].get("status", ""),
        "last_verified": page["meta"].get("last_verified", ""), "source_url": page["meta"].get("source_url", ""),
        "raw": {key: raw.get(key) for key in ("path", "name", "format", "characters", "pages", "missing")} if raw else None,
    }


def validate_wiki() -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    seen_titles: dict[str, str] = {}
    pages = _pages()
    for page in pages:
        text = page.read_text(encoding="utf-8")
        meta, _ = _parse_frontmatter(text)
        rel = _relative(page)
        title = _title(text, page.stem)
        for key in REQUIRED_METADATA:
            if not meta.get(key):
                issues.append({"path": rel, "code": "missing_metadata", "message": key})
        if meta.get("type") not in PAGE_TYPES:
            issues.append({"path": rel, "code": "invalid_type", "message": meta.get("type", "")})
        for heading in REQUIRED_SECTIONS:
            if heading not in text:
                issues.append({"path": rel, "code": "missing_section", "message": heading})
        if meta.get("last_verified") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["last_verified"]):
            issues.append({"path": rel, "code": "invalid_date", "message": meta["last_verified"]})
        source = meta.get("source_url", "")
        if source and not (source.startswith("https://") or source.startswith("local://raw/processed/") or source == "local://user-created"):
            issues.append({"path": rel, "code": "invalid_source", "message": source})
        raw_source = meta.get("raw_source", "")
        if raw_source and (not raw_source.startswith("raw/processed/") or not _raw_path(raw_source).exists()):
            issues.append({"path": rel, "code": "missing_raw_source", "message": raw_source})
        title_key = title.casefold()
        if title_key in seen_titles:
            issues.append({"path": rel, "code": "duplicate_title", "message": seen_titles[title_key]})
        else:
            seen_titles[title_key] = rel
        for link in LINK_RE.findall(text):
            if link.startswith(("http://", "https://")):
                continue
            if not (page.parent / link).resolve().exists():
                issues.append({"path": rel, "code": "broken_link", "message": link})
    return {"ok": not issues, "page_count": len(pages), "raw_count": len(list_raw_items()), "issues": issues}


def upsert_page(path: str, content: str) -> dict[str, Any]:
    target = _wiki_path(path)
    if target.suffix.lower() != ".md":
        raise ValueError("Wiki pages must use .md")
    meta, _ = _parse_frontmatter(content)
    if meta.get("type") not in PAGE_TYPES:
        raise ValueError("content has an invalid or missing page type")
    raw_item = meta.get("raw_source", "")
    final_content = content
    if raw_item.startswith("raw/inbox/"):
        source = _raw_path(raw_item)
        if not source.exists():
            raise FileNotFoundError(f"raw item not found: {raw_item}")
        RAW_PROCESSED.mkdir(parents=True, exist_ok=True)
        destination = RAW_PROCESSED / source.name
        if destination.exists():
            raise ValueError(f"processed raw item already exists: {source.name}")
        shutil.move(str(source), str(destination))
        processed = _relative(destination)
        final_content = final_content.replace(raw_item, processed).replace(f"local://{raw_item}", f"local://{processed}")
        raw_item = processed
    existed = target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final_content.rstrip() + "\n", encoding="utf-8")
    return {"path": _relative(target), "created": not existed, "bytes": target.stat().st_size, "raw_item": raw_item}


TOOLS = {
    "list_pages": list_pages, "search_wiki": search_wiki, "read_page": read_page,
    "page_summary": page_summary, "suggest_links": suggest_links,
    "list_raw_items": list_raw_items, "store_raw_item": store_raw_item,
    "read_raw_item": read_raw_item, "draft_page_from_raw": draft_page_from_raw,
    "source_trace": source_trace, "validate_wiki": validate_wiki, "upsert_page": upsert_page,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM WIKI core tools")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("raw")
    draft = sub.add_parser("draft")
    draft.add_argument("path")
    draft.add_argument("--type", default="note", choices=sorted(PAGE_TYPES))
    draft.add_argument("--title", default="")
    trace = sub.add_parser("trace")
    trace.add_argument("path")
    args = parser.parse_args()
    if args.command == "validate": result = validate_wiki()
    elif args.command == "raw": result = list_raw_items()
    elif args.command == "draft": result = draft_page_from_raw(args.path, args.type, args.title)
    else: result = source_trace(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
