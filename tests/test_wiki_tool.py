import tempfile
import unittest
from pathlib import Path

from src import wiki_tool


class WikiToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.originals = (wiki_tool.WIKI_ROOT, wiki_tool.RAW_ROOT, wiki_tool.RAW_INBOX, wiki_tool.RAW_PROCESSED)
        wiki_tool.WIKI_ROOT = root / "wiki"
        wiki_tool.RAW_ROOT = root / "raw"
        wiki_tool.RAW_INBOX = wiki_tool.RAW_ROOT / "inbox"
        wiki_tool.RAW_PROCESSED = wiki_tool.RAW_ROOT / "processed"
        wiki_tool.WIKI_ROOT.mkdir(parents=True)
        wiki_tool.RAW_INBOX.mkdir(parents=True)
        wiki_tool.RAW_PROCESSED.mkdir(parents=True)

    def tearDown(self):
        wiki_tool.WIKI_ROOT, wiki_tool.RAW_ROOT, wiki_tool.RAW_INBOX, wiki_tool.RAW_PROCESSED = self.originals
        self.tmp.cleanup()

    def page(self, title="Knowledge Graph", page_type="concept"):
        return f"""---
type: {page_type}
status: active
tags: knowledge, graph
last_verified: 2026-06-15
source_url: https://example.com/source
---
# {title}

## Summary

A linked representation of reusable knowledge.

## Key Points

- Pages connect through explicit links.

## Source

- https://example.com/source

## Related Pages

## User Questions

- How is knowledge connected?

## Maintenance Notes

- Review when the model changes.
"""

    def test_empty_wiki_is_valid(self):
        self.assertEqual(wiki_tool.list_pages(), [])
        self.assertEqual(wiki_tool.search_wiki("anything"), [])
        self.assertEqual(wiki_tool.validate_wiki(), {"ok": True, "page_count": 0, "raw_count": 0, "issues": []})

    def test_upsert_read_search_summary_and_links(self):
        first = wiki_tool.upsert_page("concepts/knowledge-graph.md", self.page())
        second = wiki_tool.upsert_page("notes/linked-note.md", self.page("Linked Note", "note").replace("## Related Pages\n", "## Related Pages\n\n- [Knowledge Graph](../concepts/knowledge-graph.md)\n"))
        self.assertTrue(first["created"])
        self.assertEqual(wiki_tool.read_page(first["path"])["title"], "Knowledge Graph")
        self.assertEqual(wiki_tool.page_summary(first["path"])["meta"]["type"], "concept")
        self.assertEqual(wiki_tool.search_wiki("knowledge graph")[0]["title"], "Knowledge Graph")
        self.assertTrue(any(item["path"] == second["path"] for item in wiki_tool.suggest_links(first["path"])))
        self.assertTrue(wiki_tool.validate_wiki()["ok"])

    def test_rejects_escape_and_invalid_type(self):
        with self.assertRaises(ValueError):
            wiki_tool.upsert_page("../outside.md", self.page())
        with self.assertRaises(ValueError):
            wiki_tool.upsert_page("notes/bad.md", self.page().replace("type: concept", "type: trip"))

    def test_validation_reports_missing_sections_and_broken_links(self):
        bad = self.page().replace("## Maintenance Notes", "## Removed").replace("## Related Pages\n", "## Related Pages\n\n- [Missing](missing.md)\n")
        wiki_tool.upsert_page("notes/bad.md", bad)
        result = wiki_tool.validate_wiki()
        codes = {issue["code"] for issue in result["issues"]}
        self.assertIn("missing_section", codes)
        self.assertIn("broken_link", codes)


if __name__ == "__main__": unittest.main()
