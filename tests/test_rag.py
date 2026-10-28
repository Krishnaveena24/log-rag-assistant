import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from rag import chunk_lines, top_k  # noqa: E402


class ChunkLinesTest(unittest.TestCase):
    def test_empty_text_gives_no_chunks(self):
        self.assertEqual(chunk_lines(""), [])

    def test_every_line_is_covered(self):
        text = "\n".join(f"line {i}" for i in range(40))
        chunks = chunk_lines(text, size=10, overlap=2)
        joined = "\n".join(chunks)
        for i in range(40):
            self.assertIn(f"line {i}", joined)

    def test_chunks_overlap(self):
        text = "\n".join(f"line {i}" for i in range(20))
        chunks = chunk_lines(text, size=10, overlap=2)
        self.assertIn("line 8", chunks[0])
        self.assertIn("line 8", chunks[1])

    def test_blank_lines_are_skipped(self):
        self.assertEqual(chunk_lines("a\n\n\nb"), ["a\nb"])


class TopKTest(unittest.TestCase):
    def test_returns_most_similar_first(self):
        index = [("db error", [1.0, 0.0]), ("health ok", [0.0, 1.0]), ("mixed", [0.7, 0.7])]
        self.assertEqual(top_k([1.0, 0.0], index, k=2), ["db error", "mixed"])


if __name__ == "__main__":
    unittest.main()
