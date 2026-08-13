"""Text extraction, chunking, indexing, and search."""

import os
import unittest
import zipfile

from tests.base import DbCase

from harness.rag import extract
from harness.rag import index as rag


def make_docx(path, paragraphs):
    doc = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.'
           'openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join('<w:p><w:r><w:t>%s</w:t></w:r></w:p>' % p
                     for p in paragraphs)
           + '</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", doc)


def make_pptx(path, slides):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for i, text in enumerate(slides, 1):
            z.writestr("ppt/slides/slide%d.xml" % i,
                       '<?xml version="1.0"?><p:sld xmlns:a="x"><a:p><a:t>%s'
                       '</a:t></a:p></p:sld>' % text)


class TestExtraction(DbCase):
    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_plain_text(self):
        p = self.path("a.txt")
        open(p, "w").write("Mission analysis is the longest step.")
        text, note = extract.extract(p)
        self.assertIn("longest step", text)
        self.assertEqual(note, "")

    def test_markdown(self):
        p = self.path("a.md")
        open(p, "w").write("# Heading\n\nSome doctrine text here.")
        text, _n = extract.extract(p)
        self.assertIn("doctrine text", text)

    def test_html_tags_are_stripped(self):
        p = self.path("a.html")
        open(p, "w").write("<html><style>x{}</style><body><h1>Title</h1>"
                           "<p>The commander's intent &amp; the end state.</p>"
                           "<script>bad()</script></body></html>")
        text, _n = extract.extract(p)
        self.assertIn("commander's intent & the end state", text)
        self.assertNotIn("bad()", text)
        self.assertNotIn("<h1>", text)

    def test_docx(self):
        p = self.path("a.docx")
        make_docx(p, ["Paragraph one about fires.",
                      "Paragraph two about sustainment."])
        text, note = extract.extract(p)
        self.assertIn("about fires", text)
        self.assertIn("about sustainment", text)
        self.assertEqual(note, "")

    def test_docx_entities_are_decoded(self):
        p = self.path("b.docx")
        make_docx(p, ["Fires &amp; effects &lt;coordinated&gt;"])
        text, _n = extract.extract(p)
        self.assertIn("Fires & effects <coordinated>", text)

    def test_pptx_slides_are_labelled(self):
        p = self.path("a.pptx")
        make_pptx(p, ["Slide one content", "Slide two content"])
        text, _n = extract.extract(p)
        self.assertIn("Slide 1", text)
        self.assertIn("Slide one content", text)
        self.assertIn("Slide two content", text)

    def test_unsupported_type_is_reported_not_raised(self):
        p = self.path("a.zzz")
        open(p, "w").write("x")
        text, note = extract.extract(p)
        self.assertEqual(text, "")
        self.assertIn("unsupported", note)

    def test_corrupt_pdf_does_not_raise(self):
        p = self.path("bad.pdf")
        open(p, "wb").write(b"%PDF-1.4\nthis is not really a pdf\n%%EOF")
        text, note = extract.extract(p)
        self.assertIsInstance(text, str)
        self.assertIn("scanned", note)   # nothing recovered -> the OCR hint

    def test_pdf_string_decoding(self):
        self.assertEqual(extract._decode_pdf_string(rb"(hello)"), "hello")
        self.assertEqual(extract._decode_pdf_string(rb"(a\(b\))"), "a(b)")
        self.assertEqual(extract._decode_pdf_string(rb"(line\nbreak)"),
                         "line\nbreak")
        self.assertEqual(extract._decode_pdf_string(rb"<48656C6C6F>"), "Hello")
        self.assertEqual(extract._decode_pdf_string(rb"(\101)"), "A")

    def test_latin1_and_utf16_files(self):
        p = self.path("u16.txt")
        open(p, "wb").write("Commander's intent".encode("utf-16"))
        text, _n = extract.extract(p)
        self.assertIn("intent", text)


class TestChunking(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        chunks = extract.chunk("a" * 200)
        self.assertEqual(len(chunks), 1)

    def test_long_text_is_split(self):
        para = ("The commander's intent describes the purpose, the key tasks, "
                "and the end state. ") * 40
        chunks = extract.chunk(para, size=600)
        self.assertGreater(len(chunks), 2)
        for c in chunks:
            self.assertLess(len(c), 1200)

    def test_paragraph_boundaries_are_preferred(self):
        text = "\n\n".join("Paragraph %d text here." % i for i in range(20))
        chunks = extract.chunk(text, size=200)
        self.assertTrue(all(c.strip() for c in chunks))

    def test_empty_input(self):
        self.assertEqual(extract.chunk(""), [])
        self.assertEqual(extract.chunk(None), [])

    def test_tiny_fragments_are_dropped(self):
        self.assertEqual(extract.chunk("hi"), [])


class TestIndex(DbCase):
    def write(self, name, text):
        p = os.path.join(self.tmp, name)
        open(p, "w").write(text)
        return p

    def test_ingest_and_search(self):
        self.write("fm5.md", "# Mission analysis\n\n"
                             + "An essential task must be executed for the "
                               "mission to succeed. " * 8)
        rag.ingest_dir(self.tmp)
        hits = rag.search("essential task mission succeed")
        self.assertTrue(hits)
        self.assertIn("essential task", hits[0]["snippet"])
        self.assertEqual(hits[0]["title"], "fm5")

    def test_ingest_is_idempotent(self):
        self.write("a.md", "Doctrine content about fires and effects. " * 20)
        first = rag.ingest_dir(self.tmp)
        second = rag.ingest_dir(self.tmp)
        self.assertEqual(first[0]["status"], "indexed")
        self.assertEqual(second[0]["status"], "unchanged")
        self.assertEqual(rag.stats()["chunks"], first[0]["chunks"])

    def test_changed_file_is_reindexed_without_duplicating(self):
        p = self.write("a.md", "Original doctrine text about fires. " * 20)
        rag.ingest_dir(self.tmp)
        open(p, "w").write("Replacement doctrine text about sustainment. " * 20)
        rag.ingest_dir(self.tmp)
        self.assertEqual(len(rag.stats()["documents"]), 1)
        self.assertTrue(rag.search("sustainment"))
        self.assertFalse([h for h in rag.search("fires")
                          if "Original" in h["snippet"]])

    def test_readme_at_the_corpus_root_is_skipped(self):
        self.write("README.md", "How to use this folder. " * 20)
        self.write("doctrine.md", "Real doctrine content here. " * 20)
        rag.ingest_dir(self.tmp)
        titles = [d["title"] for d in rag.stats()["documents"]]
        self.assertNotIn("README", titles)
        self.assertIn("doctrine", titles)

    def test_readme_inside_a_subfolder_is_indexed(self):
        sub = os.path.join(self.tmp, "seed")
        os.makedirs(sub)
        open(os.path.join(sub, "README.md"), "w").write("Seed notes. " * 30)
        rag.ingest_dir(self.tmp)
        self.assertEqual(len(rag.stats()["documents"]), 1)

    def test_search_survives_hostile_input(self):
        self.write("a.md", "Ordinary doctrine text. " * 20)
        rag.ingest_dir(self.tmp)
        for q in ['"', "AND OR NOT", "*", "()", "NEAR/2", "'; DROP TABLE docs;--",
                  "a" * 500, "", "   ", "\x00weird"]:
            self.assertIsInstance(rag.search(q), list, repr(q))
        # the index must still be intact
        self.assertTrue(rag.stats()["chunks"] > 0)

    def test_search_with_no_usable_terms_returns_nothing(self):
        self.assertEqual(rag.search("a an the"), [])

    def test_clear_empties_the_index(self):
        self.write("a.md", "Doctrine. " * 40)
        rag.ingest_dir(self.tmp)
        rag.clear()
        self.assertEqual(rag.stats()["chunks"], 0)
        self.assertEqual(rag.search("doctrine"), [])

    def test_empty_file_is_reported_not_indexed(self):
        self.write("empty.md", "")
        results = rag.ingest_dir(self.tmp)
        self.assertEqual(results[0]["status"], "empty")

    def test_shipped_seed_corpus_indexes_and_is_searchable(self):
        root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "corpus")
        results = rag.ingest_dir(root)
        indexed = [r for r in results if r["status"] == "indexed"]
        self.assertGreaterEqual(len(indexed), 10)
        for query in ["commander's intent key tasks end state",
                      "feasible acceptable suitable distinguishable complete",
                      "belt avenue-in-depth box war game",
                      "specified implied essential tasks",
                      "probability severity risk level",
                      "PACE plan primary alternate contingency emergency"]:
            self.assertTrue(rag.search(query), "no hit for: %s" % query)


if __name__ == "__main__":
    unittest.main()
