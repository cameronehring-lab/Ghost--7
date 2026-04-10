import unittest
from unittest.mock import patch

import philosophers_api


class PhilosophersApiTests(unittest.TestCase):
    def test_search_philosophers_normalizes_rows(self):
        payload = [
            {
                "id": "abc",
                "name": "Jean-Paul Sartre",
                "life": "(1905-1980)",
                "school": "Existentialism",
                "interests": "Ontology, Ethics",
                "speLink": "https://plato.stanford.edu/entries/sartre/",
                "iepLink": "https://www.iep.utm.edu/sartre-ex/",
            }
        ]
        with patch.object(philosophers_api, "_fetch_json", return_value=payload):
            rows = philosophers_api.search_philosophers("sartre", limit=3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Jean-Paul Sartre")
        self.assertEqual(rows[0]["school"], "Existentialism")

    def test_build_query_context_includes_detail_quotes_and_ideas(self):
        search_payload = [
            {
                "id": "abc",
                "name": "Jean-Paul Sartre",
                "life": "(1905-1980)",
                "school": "Existentialism",
                "interests": "Ontology, Ethics",
                "speLink": "https://plato.stanford.edu/entries/sartre/",
                "iepLink": "https://www.iep.utm.edu/sartre-ex/",
            }
        ]
        detail_payload = {
            "id": "abc",
            "name": "Jean-Paul Sartre",
            "hasEBooks": True,
            "quotes": [{"quote": "Existence precedes essence."}],
            "keyIdeas": [{"idea": "Radical freedom"}],
        }

        def fake_fetch(path: str):
            if path.startswith("/api/philosophers/search"):
                return search_payload
            if path.startswith("/api/philosophers/name/"):
                return detail_payload
            return None

        with patch.object(philosophers_api, "_fetch_json", side_effect=fake_fetch):
            context = philosophers_api.build_query_context("sartre")
        self.assertIn("[PHILOSOPHERS_API_CONTEXT]", context)
        self.assertIn("Jean-Paul Sartre", context)
        self.assertIn("top_match_quotes", context)
        self.assertIn("top_match_key_ideas", context)
        self.assertIn("top_match_has_ebooks=true", context)


if __name__ == "__main__":
    unittest.main()
