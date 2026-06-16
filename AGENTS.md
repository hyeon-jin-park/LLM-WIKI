# AGENTS.md

This repository is a domain-neutral LLM WIKI harness. It starts with no Wiki content and turns user-provided sources into reviewed Markdown knowledge.

## Startup

Read `README.md`, `RULES.md`, `PRD.md`, `schema/page-template.md`, and `skills/wiki-curator/SKILL.md` before maintaining the Wiki.

## Operating Rules

- Use MCP tools as the boundary for `raw/` and `wiki/`.
- Search existing pages before drafting or publishing.
- Store sources with `store_raw_item`; inspect them with `read_raw_item`.
- `draft_page_from_raw` must not change the Wiki.
- Show the complete draft and target path before requesting approval.
- Call `upsert_page` only after explicit human approval.
- Preserve `raw_source` lineage and run `source_trace` after publishing.
- Run `validate_wiki` after every write and report every issue.
- Do not invent sources, links, metadata, or facts absent from the material.
- Never write outside `raw/` and `wiki/` through MCP.

## Required Checks

```bash
python3 run.py --check
.venv/bin/python -m unittest discover -s tests -p "test_*.py"
.venv/bin/python tests/mcp_smoke.py
```
