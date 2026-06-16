# PRD: LLM WIKI MVP

## Goal

Enable a first-time user to clone an empty repository, add one source, review a generated Markdown draft, publish it through MCP, and inspect it in the viewer within 30 minutes.

## Core Requirements

- Start with zero Wiki pages and validate successfully.
- Accept MD, TXT, and text-based PDF files under 10 MB.
- Generate a domain-neutral draft without writing automatically.
- Require visible human approval before publishing.
- Preserve source lineage and validate after every write.
- Search, read, summarize, suggest links, trace sources, and edit pages.
- Expose the same 12 operations through a real stdio MCP server.
- Run with `python3 run.py` and work without external services or local LLM setup.
- Offer optional read-only conversation when Codex CLI is already installed.

## Agent Specification

The Wiki Curator Agent may read, search, draft, suggest links, trace, and validate automatically. It may publish only after explicit approval. It may not create unsupported facts, silently repair validation errors, access paths outside the Wiki roots, or treat generated summaries as verified truth.

The optional Chat Agent receives MCP-retrieved evidence and may only answer. It runs in a read-only ephemeral subprocess and cannot publish or edit Wiki pages.

## Success Criteria

- A clean clone reports `0 pages, 12 MCP tools`.
- A source remains in the inbox until approval.
- Approval creates one valid page and moves its source to processed storage.
- The browser displays the page, source trace, validation, and MCP activity.
- Automated tests cover the empty state and the complete first-page pipeline.
