import unittest
from unittest.mock import patch

import wikidata_api


class WikidataApiTests(unittest.TestCase):
    def test_search_entities_normalizes_rows(self):
        payload = {
            "search": [
                {
                    "id": "Q42",
                    "label": "Douglas Adams",
                    "description": "English writer and humorist",
                    "concepturi": "http://www.wikidata.org/entity/Q42",
                }
            ]
        }
        with patch.object(wikidata_api, "_fetch_json", return_value=payload):
            rows = wikidata_api.search_entities("Douglas Adams", limit=3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "Q42")
        self.assertEqual(rows[0]["label"], "Douglas Adams")

    def test_build_query_context_contains_qid(self):
        payload = {
            "search": [
                {
                    "id": "Q42",
                    "label": "Douglas Adams",
                    "description": "English writer and humorist",
                    "concepturi": "http://www.wikidata.org/entity/Q42",
                }
            ]
        }
        with patch.object(wikidata_api, "_fetch_json", return_value=payload):
            context = wikidata_api.build_query_context("Douglas Adams")
        self.assertIn("[WIKIDATA_API_CONTEXT]", context)
        self.assertIn("Q42", context)
        self.assertIn("Douglas Adams", context)


if __name__ == "__main__":
    unittest.main()
