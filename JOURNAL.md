# Decision Journal

## 2026-06-15: Separate Product From Demo Knowledge

The earlier build served a complete travel Wiki. Re-reading the product requirement showed that the reusable tool, not the author's knowledge base, is the primary deliverable. The travel build was preserved locally in `archive3/`, while one screenshot remains as proof that the tool can support a real domain.

## 2026-06-15: Start Empty

The public repository now starts with no Wiki pages or raw sources. Empty-state validation is considered a valid system state. The first interaction directs the user to add one source and complete the review pipeline.

## 2026-06-15: Reduce To The Reusable Core

Travel planning tools and local AI conversation were removed from the MVP. The product retains 12 domain-neutral MCP tools, a human approval boundary, source lineage, validation, and a Wiki Curator Skill. This reduces setup and makes the intended reuse clear.

## 2026-06-15: Add Optional Read-Only Chat

The Tool panel alone made the product harder to use interactively. A separate Chat tab now detects an existing Codex CLI installation, retrieves evidence through MCP, and asks the CLI only to compose an answer. The core MVP still has no LLM dependency, and all writes remain behind visible approval controls.
