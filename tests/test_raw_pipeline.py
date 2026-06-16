import base64
import importlib.util
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from src import wiki_tool


class RawPipelineTest(unittest.TestCase):
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

    def store(self, name="source.txt", content="Knowledge systems preserve decisions and source context."):
        return wiki_tool.store_raw_item(name, base64.b64encode(content.encode()).decode())

    def test_text_markdown_and_non_writing_draft(self):
        text = self.store()
        markdown = self.store("concept.md", "# Context Window\n\nA bounded working context.")
        self.assertIn("preserve decisions", wiki_tool.read_raw_item(text["path"])["text"])
        self.assertIn("Context Window", wiki_tool.read_raw_item(markdown["path"])["text"])
        draft = wiki_tool.draft_page_from_raw(markdown["path"], "concept")
        self.assertEqual(draft["suggested_path"], "concepts/context-window.md")
        self.assertIn("- Scope:", draft["content"])
        self.assertIn("- Signals:", draft["content"])
        self.assertIn("## Key Points", draft["content"])
        self.assertIn("## Source Excerpt", draft["content"])
        self.assertNotIn("Review and replace", draft["content"])
        self.assertEqual(wiki_tool.list_pages(), [])

    def test_publish_moves_source_and_preserves_trace(self):
        item = self.store("project.txt")
        draft = wiki_tool.draft_page_from_raw(item["path"], "project", "My Project", "project, decisions")
        saved = wiki_tool.upsert_page(draft["suggested_path"], draft["content"])
        self.assertFalse((wiki_tool.RAW_INBOX / "project.txt").exists())
        self.assertTrue((wiki_tool.RAW_PROCESSED / "project.txt").exists())
        self.assertEqual(wiki_tool.source_trace(saved["path"])["raw"]["path"], "raw/processed/project.txt")
        self.assertTrue(wiki_tool.validate_wiki()["ok"])

    def test_rejects_duplicate_unsupported_escape_and_corrupt_pdf(self):
        self.store()
        with self.assertRaises(ValueError): self.store()
        with self.assertRaises(ValueError): self.store("photo.png")
        with self.assertRaises(ValueError): wiki_tool.read_raw_item("../secret.txt")
        broken = wiki_tool.store_raw_item("broken.pdf", base64.b64encode(b"not pdf").decode())
        with self.assertRaises(ValueError): wiki_tool.read_raw_item(broken["path"])

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf installed")
    def test_pdf_extraction_and_draft(self):
        from pypdf import PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
        output = BytesIO(); writer = PdfWriter(); page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject(); stream.set_data(b"BT /F1 12 Tf 72 720 Td (Hello Knowledge PDF) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream); writer.write(output)
        item = wiki_tool.store_raw_item("knowledge.pdf", base64.b64encode(output.getvalue()).decode())
        raw = wiki_tool.read_raw_item(item["path"])
        self.assertIn("Hello Knowledge PDF", raw["text"])
        self.assertIn("Hello Knowledge PDF", wiki_tool.draft_page_from_raw(item["path"], "reference")["content"])


if __name__ == "__main__": unittest.main()
