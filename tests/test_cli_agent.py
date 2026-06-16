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
        if name == "validate_wiki":
            return {"ok": True, "page_count": 1, "raw_count": 0, "issues": []}
        raise AssertionError(name)

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_status_without_codex(self, _which):
        status = agent_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["provider"], "local-mcp")
        result = answer_with_codex(self.call_tool, "What is context?")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertIn("Context", result["answer"])

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_local_polish_returns_approval_gated_action(self, _which):
        result = answer_with_codex(self.call_tool, "현재 페이지 보기 좋게 정리해줘", "wiki/concepts/context.md")
        self.assertEqual(result["engine"], "local-mcp")
        self.assertEqual(result["action"]["type"], "apply_edit_suggestion")
        self.assertIn("## Summary", result["action"]["content"])

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
        self.assertIn("MCP Wiki evidence", run.call_args.kwargs["input"])


if __name__ == "__main__": unittest.main()
