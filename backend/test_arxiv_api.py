import unittest
from unittest.mock import patch

import arxiv_api


_SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <updated>2025-01-01T00:00:00Z</updated>
    <published>2025-01-01T00:00:00Z</published>
    <title>Test Paper Title</title>
    <summary>Test abstract about transformer scaling laws.</summary>
    <author><name>Alice Example</name></author>
    <author><name>Bob Example</name></author>
    <arxiv:doi>10.1000/test-doi</arxiv:doi>
    <category term="cs.AI"/>
    <link rel="alternate" href="https://arxiv.org/abs/2501.00001"/>
  </entry>
</feed>
"""


class ArxivApiTests(unittest.TestCase):
    def test_search_metadata_parses_atom_entry(self):
        with patch.object(arxiv_api, "_fetch_atom_xml", return_value=_SAMPLE_ATOM):
            rows = arxiv_api.search_metadata("transformer", max_results=3)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Test Paper Title")
        self.assertEqual(row["authors"][0], "Alice Example")
        self.assertEqual(row["categories"][0], "cs.AI")
        self.assertIn("2501.00001", row["id_url"])

    def test_build_query_context_contains_acknowledgement(self):
        with patch.object(arxiv_api, "_fetch_atom_xml", return_value=_SAMPLE_ATOM), patch.object(
            arxiv_api.settings,
            "ARXIV_API_ACKNOWLEDGEMENT",
            "Thank you to arXiv for use of its open access interoperability.",
        ):
            context = arxiv_api.build_query_context("transformer")
        self.assertIn("[ARXIV_API_CONTEXT]", context)
        self.assertIn("acknowledgement=Thank you to arXiv for use of its open access interoperability.", context)
        self.assertIn("compliance=metadata_only", context)
        self.assertIn("Test Paper Title", context)


if __name__ == "__main__":
    unittest.main()
