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
        raise AssertionError(name)

    @patch("src.cli_agent.shutil.which", return_value=None)
    def test_status_without_codex(self, _which):
        self.assertFalse(agent_status()["available"])
        with self.assertRaises(RuntimeError):
            answer_with_codex(self.call_tool, "What is context?")

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
