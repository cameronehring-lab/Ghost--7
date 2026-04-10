import unittest
from unittest.mock import patch

import crossref_api


class CrossrefApiTests(unittest.TestCase):
    def test_search_works_normalizes_rows(self):
        payload = {
            "message": {
                "items": [
                    {
                        "title": ["Crossref Test Paper"],
                        "DOI": "10.1234/test-doi",
                        "URL": "https://doi.org/10.1234/test-doi",
                        "publisher": "Test Publisher",
                        "container-title": ["Journal of Test Systems"],
                        "published-print": {"date-parts": [[2024, 5, 1]]},
                        "author": [{"given": "Alice", "family": "Smith"}],
                    }
                ]
            }
        }
        with patch.object(crossref_api, "_fetch_json", return_value=payload):
            rows = crossref_api.search_works("test query", limit=3)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["title"], "Crossref Test Paper")
        self.assertEqual(row["doi"], "10.1234/test-doi")
        self.assertEqual(row["year"], "2024")
        self.assertIn("Alice Smith", row["authors"])

    def test_build_query_context_contains_crossref_block(self):
        payload = {
            "message": {
                "items": [
                    {
                        "title": ["Crossref Test Paper"],
                        "DOI": "10.1234/test-doi",
                        "URL": "https://doi.org/10.1234/test-doi",
                        "publisher": "Test Publisher",
                        "container-title": ["Journal of Test Systems"],
                        "published-print": {"date-parts": [[2024, 5, 1]]},
                        "author": [{"given": "Alice", "family": "Smith"}],
                    }
                ]
            }
        }
        with patch.object(crossref_api, "_fetch_json", return_value=payload):
            context = crossref_api.build_query_context("test query")
        self.assertIn("[CROSSREF_API_CONTEXT]", context)
        self.assertIn("Crossref Test Paper", context)
        self.assertIn("10.1234/test-doi", context)


if __name__ == "__main__":
    unittest.main()
