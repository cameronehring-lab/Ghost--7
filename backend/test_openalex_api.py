import unittest
from unittest.mock import patch

import openalex_api


class OpenAlexApiTests(unittest.TestCase):
    def test_search_works_normalizes_rows(self):
        payload = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "display_name": "Test Work Title",
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1234/test-doi",
                    "authorships": [
                        {"author": {"display_name": "Alice Example"}},
                        {"author": {"display_name": "Bob Example"}},
                    ],
                    "primary_location": {"source": {"display_name": "Nature"}},
                    "concepts": [{"display_name": "Large language models"}],
                }
            ]
        }
        with patch.object(openalex_api, "_fetch_json", return_value=payload):
            rows = openalex_api.search_works("test query", limit=3)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Test Work Title")
        self.assertEqual(row["source"], "Nature")
        self.assertIn("Alice Example", row["authors"])

    def test_build_query_context_contains_openalex_block(self):
        payload = {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "display_name": "Test Work Title",
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.1234/test-doi",
                    "authorships": [{"author": {"display_name": "Alice Example"}}],
                    "primary_location": {"source": {"display_name": "Nature"}},
                    "concepts": [{"display_name": "Large language models"}],
                }
            ]
        }
        with patch.object(openalex_api, "_fetch_json", return_value=payload):
            context = openalex_api.build_query_context("test query")
        self.assertIn("[OPENALEX_API_CONTEXT]", context)
        self.assertIn("Test Work Title", context)
        self.assertIn("https://openalex.org/W123", context)


if __name__ == "__main__":
    unittest.main()
