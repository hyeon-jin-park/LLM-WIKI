---
name: wiki-curator
description: Build and maintain a domain-neutral, sourced Markdown Wiki through LLM WIKI MCP tools. Use when an agent needs to import MD, TXT, or PDF material; create a draft for human review; search or read saved knowledge; suggest links; trace sources; publish an approved page; or validate the Wiki.
---

# Wiki Curator

Use MCP tools as the only boundary for raw materials and Wiki pages.

## Import Material

1. Call `list_raw_items` and reject duplicate filenames.
2. Call `store_raw_item` for one MD, TXT, or text-based PDF under 10 MB.
3. Call `read_raw_item` to confirm extraction.
4. Call `draft_page_from_raw` with a page type, title, and tags.
5. Show the complete Markdown and suggested path to the user.
6. Do not call `upsert_page` until the user explicitly approves the draft.
7. After publishing, call `source_trace` and `validate_wiki`.

## Answer From The Wiki

1. Call `search_wiki` with the user's wording.
2. Call `page_summary` or `read_page` for relevant results.
3. Answer only from returned pages and cite their paths.
4. State clearly when the Wiki has no supporting evidence.

## Maintain Knowledge

- Search for duplicates before writing.
- Use one of: `note`, `concept`, `guide`, `reference`, `project`, `journal`.
- Require the metadata and headings defined in `schema/wiki-page.schema.json` and `schema/page-template.md`.
- Use `suggest_links` after a page exists; do not invent links.
- Preserve `raw_source` lineage for imported pages.
- Run `validate_wiki` immediately after every write and report all issues.
- Never write outside `raw/` and `wiki/`.
