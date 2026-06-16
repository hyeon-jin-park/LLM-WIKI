import subprocess
import unittest
from unittest.mock import patch

from src.cli_agent import agent_status, answer_with_codex


class CLIAgentTest(unittest.TestCase):
    def call_tool(self, name, arguments=None):
        if name == "list_pages":
            return [{"path": "wiki/concepts/context.md", "title": "Context", "meta": {"type": "concept"}}]
        if name == "search_wiki":
            return [{"path": "wiki/concepts/context.md", "title": "Context", "preview": "Working context"}]
        if name == "page_summary":
            return {"path": "wiki/concepts/context.md", "title": "Context", "summary": "A bounded working context.", "key_points": "- Preserve relevant knowledge.", "meta": {"type": "concept"}}
        if name == "read_page":
            return {"path": "wiki/concepts/context.md", "title": "Context", "meta": {"type": "concept"}, "content": "---\ntype: concept\nstatus: draft\ntags: test\nlast_verified: 2026-06-16\nsource_url: local://user-created\n---\n# Context\n\n## Summary\n\nA bounded working context.\n\n## Key Points\n\n- Preserve relevant knowledge.\n\n## Source\n\n- test\n\n## Related Pages\n\n## User Questions\n\n## Maintenance Notes\n\n"}
        if name == "suggest_links":
            return [{"path": "wiki/concepts/linked.md", "title": "Linked Page", "score": 3, "preview": "Related"}]
        if name == "validate_wiki":
            return {"ok": True, "page_count": 1, "raw_count": 0, "issues": []}
        raise AssertionError(name)

    def raw_call_tool(self, name, arguments=None):
        if name == "list_pages":
            return []
        if name == "list_raw_items":
            return [{"path": "raw/inbox/source.txt", "name": "source.txt", "format": "txt", "status": "pending", "bytes": 120, "wiki_pages": []}]
        if name == "draft_page_from_raw":
            return {"suggested_path": "notes/source.md", "raw": {"path": "raw/inbox/source.txt"}, "content": "---\ntype: note\nstatus: draft\n---\n# Source\n\n## Summary\n\n- Scope: Source text\n"}
        raise AssertionError(name)

    def preserving_call_tool(self, name, arguments=None):
        if name == "list_pages":
            return [{"path": "wiki/notes/raw.md", "title": "Raw Notes", "meta": {"type": "note"}}]
        if name == "search_wiki":
            return [{"path": "wiki/notes/raw.md", "title": "Raw Notes", "preview": "A long original page"}]
        if name == "page_summary":
            return {"path": "wiki/notes/raw.md", "title": "Raw Notes", "summary": "A long original page.", "key_points": "- First claim", "meta": {"type": "note"}}
        if name == "read_page":
            return {
                "path": "wiki/notes/raw.md",
                "title": "Raw Notes",
                "meta": {"type": "note"},
                "content": "---\ntype: note\nstatus: draft\ntags: raw\nlast_verified: 2026-06-16\nsource_url: local://raw/processed/raw.txt\nraw_source: raw/processed/raw.txt\n---\n# Raw Notes\n\n## Summary\n\nThis paragraph must stay intact because decorating is not summarizing.\n\n## Key Points\n\n\uf06f First private-use bullet must become readable but remain present.\n\n> Quoted evidence must stay visible.\n\nLong original paragraph with implementation detail A, implementation detail B, and implementation detail C must not disappear.\n\n## Source\n\n- `raw/processed/raw.txt`\n",
            }
        raise AssertionError(name)

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_status_without_codex(self, _which):
        status = agent_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["provider"], "local-mcp")
        self.assertTrue(status["setup"]["needed"])
        result = answer_with_codex(self.call_tool, "What is context?")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertIn("Context", result["answer"])

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_local_mode_does_not_fake_translation(self, _which):
        result = answer_with_codex(self.call_tool, "현재 페이지를 한글로 번역해줘", "wiki/concepts/context.md")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertTrue(result["needs_llm"])
        self.assertIn("LLM이 필요한 작업", result["answer"])

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_local_polish_returns_approval_gated_action(self, _which):
        result = answer_with_codex(self.call_tool, "현재 페이지 보기 좋게 정리해줘", "wiki/concepts/context.md")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertEqual(result["action"]["type"], "apply_edit_suggestion")
        self.assertIn("## Summary", result["action"]["content"])

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_local_polish_preserves_existing_content(self, _which):
        original = self.preserving_call_tool("read_page")["content"]
        result = answer_with_codex(self.preserving_call_tool, "현재 페이지 보기 좋게 꾸며줘", "wiki/notes/raw.md")
        content = result["action"]["content"]
        self.assertIn("This paragraph must stay intact", content)
        self.assertIn("First private-use bullet must become readable but remain present", content)
        self.assertIn("> Quoted evidence must stay visible.", content)
        self.assertIn("implementation detail A", content)
        self.assertIn("## Maintenance Notes", content)
        self.assertGreater(len(content), int(len(original) * 0.9))

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_local_agent_can_prepare_raw_draft(self, _which):
        result = answer_with_codex(self.raw_call_tool, "저장된 자료로 Wiki 초안 만들어줘")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertEqual(result["action"]["type"], "apply_import_draft")
        self.assertEqual(result["action"]["path"], "notes/source.md")

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_local_agent_can_prepare_related_link_edit(self, _which):
        result = answer_with_codex(self.call_tool, "현재 페이지에 관련 링크 추가해줘", "wiki/concepts/context.md")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertEqual(result["action"]["type"], "apply_edit_suggestion")
        self.assertIn("[Linked Page](linked.md)", result["action"]["content"])

    @patch("src.cli_agent.subprocess.run")
    @patch("src.cli_agent.shutil.which", return_value="/usr/local/bin/codex")
    def test_read_only_grounded_chat(self, _which, run):
        run.return_value = subprocess.CompletedProcess([], 0, stdout="Context는 Wiki에 저장된 작업 범위입니다.", stderr="")
        result = answer_with_codex(self.call_tool, "Context가 뭐야?")
        self.assertEqual(result["engine"], "codex-cli")
        self.assertEqual(result["sources"][0]["title"], "Context")
        command = run.call_args.args[0]
        self.assertIn("read-only", command)
        self.assertIn("--ephemeral", command)
        self.assertIn("Search evidence", run.call_args.kwargs["input"])

    @patch("src.cli_agent._find_ollama", return_value="/usr/local/bin/ollama")
    @patch("src.cli_agent._find_codex", return_value=None)
    @patch("src.cli_agent.subprocess.run")
    def test_ollama_handles_translation_requests(self, run, _codex, _ollama):
        run.return_value = subprocess.CompletedProcess([], 0, stdout="번역된 내용입니다.", stderr="")
        result = answer_with_codex(self.call_tool, "현재 페이지를 한글로 번역해줘", "wiki/concepts/context.md")
        self.assertEqual(result["engine"], "ollama")
        self.assertEqual(result["answer"], "번역된 내용입니다.")
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/usr/local/bin/ollama", "run"])


if __name__ == "__main__": unittest.main()
