import unittest
import base64

from src.mcp_client import MCPClient


class MCPIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.client = MCPClient()
    @classmethod
    def tearDownClass(cls): cls.client.close()

    def test_protocol_and_exact_tool_contract(self):
        self.assertEqual(self.client.server_info["protocolVersion"], "2025-06-18")
        names = [item["name"] for item in self.client.list_tools()]
        self.assertEqual(names, [
            "list_pages", "search_wiki", "read_page", "page_summary", "suggest_links",
            "list_raw_items", "store_raw_item", "read_raw_item", "draft_page_from_raw",
            "source_trace", "validate_wiki", "upsert_page",
        ])

    def test_clean_repository_is_empty_and_valid(self):
        self.assertEqual(self.client.call_tool("list_pages"), [])
        result = self.client.call_tool("validate_wiki")
        self.assertTrue(result["ok"])
        self.assertEqual(result["page_count"], 0)

    def test_client_recovers_if_stdio_server_exits(self):
        self.client._process.terminate()
        self.client._process.wait(timeout=5)
        names = [item["name"] for item in self.client.list_tools()]
        self.assertIn("draft_page_from_raw", names)

    def test_stdio_handles_pdf_private_use_unicode(self):
        payload = base64.b64encode("PDF bullet \uf06f survives stdio.".encode("utf-8")).decode()
        stored = self.client.call_tool("store_raw_item", {"filename": "unicode-stdio-test.txt", "content_base64": payload})
        try:
            draft = self.client.call_tool("draft_page_from_raw", {"path": stored["path"], "page_type": "note", "title": "Unicode Stdio Test"})
            self.assertIn("\uf06f", draft["content"])
        finally:
            from pathlib import Path
            target = Path(stored["path"])
            if target.exists():
                target.unlink()


if __name__ == "__main__": unittest.main()
