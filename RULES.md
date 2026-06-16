# LLM WIKI Rules

## Filesystem Boundary

- Keep source material under `raw/` and knowledge pages under `wiki/`.
- Reject absolute paths, parent traversal, unsupported formats, duplicate filenames, and files over 10 MB.
- Do not commit personal raw material.

## Evidence And Schema

- Every page requires `type`, `status`, `tags`, `last_verified`, and `source_url`.
- Imported pages preserve a valid `raw_source` path.
- Use only headings defined in the common template as the required base structure.
- State when evidence is missing; never fill gaps with invented claims.

## Human Approval

- Reading, searching, drafting, linking suggestions, tracing, and validation may run automatically.
- Draft generation never writes to `wiki/`.
- A person must review the complete draft before `upsert_page`.
- Validate immediately after every write.

## Optional Chat

- Retrieve Wiki evidence through MCP before invoking Codex CLI.
- Run the CLI with ephemeral and read-only sandbox options.
- Do not let chat claims replace the import, review, or edit approval flow.
- Keep the core product functional when no CLI is installed.

## Public Repository

- Do not publish secrets, private source files, archives, caches, or generated ZIP files.
- Demo images may prove usage but must not become required runtime data.
