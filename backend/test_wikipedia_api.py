import unittest
from unittest.mock import patch

import wikipedia_api


class WikipediaApiTests(unittest.TestCase):
    def test_search_pages_strips_html_snippet(self):
        payload = {
            "query": {
                "search": [
                    {
                        "title": "Alan Turing",
                        "snippet": "<span class=\"searchmatch\">English</span> mathematician and logician",
                        "pageid": 123,
                    }
                ]
            }
        }
        with patch.object(wikipedia_api, "_fetch_json", return_value=payload):
            rows = wikipedia_api.search_pages("Alan Turing", limit=3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Alan Turing")
        self.assertIn("English mathematician", rows[0]["snippet"])

    def test_build_query_context_contains_link(self):
        payload = {
            "query": {
                "search": [
                    {
                        "title": "Alan Turing",
                        "snippet": "English mathematician and logician",
                        "pageid": 123,
                    }
                ]
            }
        }
        with patch.object(wikipedia_api, "_fetch_json", return_value=payload):
            context = wikipedia_api.build_query_context("Alan Turing")
        self.assertIn("[WIKIPEDIA_API_CONTEXT]", context)
        self.assertIn("Alan Turing", context)
        self.assertIn("https://en.wikipedia.org/wiki/Alan_Turing", context)


if __name__ == "__main__":
    unittest.main()
