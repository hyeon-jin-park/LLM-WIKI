import unittest

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


if __name__ == "__main__": unittest.main()
