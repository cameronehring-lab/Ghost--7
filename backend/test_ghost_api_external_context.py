import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import ghost_api


class GhostApiExternalContextTests(unittest.IsolatedAsyncioTestCase):
    def test_should_use_philosophers_api(self):
        self.assertTrue(ghost_api._should_use_philosophers_api("Compare Sartre and Camus on freedom."))
        self.assertFalse(ghost_api._should_use_philosophers_api("Show CPU telemetry now."))

    def test_should_use_arxiv_api(self):
        self.assertTrue(ghost_api._should_use_arxiv_api("Find papers on diffusion transformers."))
        self.assertTrue(ghost_api._should_use_arxiv_api("Summarize arXiv: 2401.12345v2"))
        self.assertFalse(ghost_api._should_use_arxiv_api("Show weather in Allen Texas."))

    def test_should_use_wikidata_api(self):
        self.assertTrue(ghost_api._should_use_wikidata_api("Who is Douglas Adams in Wikidata?"))
        self.assertFalse(ghost_api._should_use_wikidata_api("Show CPU telemetry now."))

    def test_should_use_wikipedia_api(self):
        self.assertTrue(ghost_api._should_use_wikipedia_api("Give me a Wikipedia summary of Turing."))
        self.assertFalse(ghost_api._should_use_wikipedia_api("Set local TTS rate to 0.8."))

    def test_should_use_crossref_api(self):
        self.assertTrue(ghost_api._should_use_crossref_api("Find DOI 10.1234/abc"))
        self.assertTrue(ghost_api._should_use_crossref_api("crossref citation lookup for this paper"))
        self.assertFalse(ghost_api._should_use_crossref_api("What's the weather in Texas?"))

    async def test_external_reference_context_combines_blocks(self):
        with patch.object(ghost_api.settings, "PHILOSOPHERS_API_ENABLED", True), patch.object(
            ghost_api.settings, "ARXIV_API_ENABLED", True
        ), patch.object(
            ghost_api, "_should_use_philosophers_api", return_value=True
        ), patch.object(
            ghost_api, "_should_use_arxiv_api", return_value=True
        ), patch.object(
            ghost_api, "_should_use_wikidata_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_wikipedia_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_openalex_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_crossref_api", return_value=False
        ), patch.object(
            ghost_api.philosophers_api, "build_query_context", return_value="[PHILOSOPHERS_API_CONTEXT]\nmatch"
        ), patch.object(
            ghost_api.arxiv_api, "build_query_context", return_value="[ARXIV_API_CONTEXT]\nmatch"
        ), patch.object(
            ghost_api.asyncio, "to_thread", new=AsyncMock(side_effect=["[PHILOSOPHERS_API_CONTEXT]\nmatch", "[ARXIV_API_CONTEXT]\nmatch"])
        ):
            context = await ghost_api._external_reference_context("Compare Sartre with recent ML papers.")
        self.assertIn("[EXTERNAL_GROUNDING_PROVENANCE]", context)
        self.assertIn("attempted_count=2", context)
        self.assertIn("source_count=2", context)
        self.assertIn("- source=arxiv", context)
        self.assertIn("- source=philosophers", context)
        self.assertIn("status=ok", context)
        self.assertIn("[GROUNDING_SOURCE key=arxiv", context)
        self.assertIn("[GROUNDING_SOURCE key=philosophers", context)
        self.assertLess(
            context.find("[GROUNDING_SOURCE key=arxiv"),
            context.find("[GROUNDING_SOURCE key=philosophers"),
        )
        self.assertIn("[PHILOSOPHERS_API_CONTEXT]", context)
        self.assertIn("[ARXIV_API_CONTEXT]", context)

    async def test_external_reference_context_marks_pending_sources_timed_out(self):
        async def fake_job(spec, user_message, adapter_timeout_s):  # pylint: disable=unused-argument
            if spec.key == "philosophers":
                return {
                    "key": spec.key,
                    "label": spec.label,
                    "trust_tier": spec.trust_tier,
                    "confidence": 0.8,
                    "latency_ms": 2.0,
                    "status": "ok",
                    "error": "",
                    "block": "[PHILOSOPHERS_API_CONTEXT]\nmatch",
                }
            await asyncio.sleep(0.05)
            return {
                "key": spec.key,
                "label": spec.label,
                "trust_tier": spec.trust_tier,
                "confidence": 0.86,
                "latency_ms": 50.0,
                "status": "ok",
                "error": "",
                "block": "[ARXIV_API_CONTEXT]\nlate",
            }

        with patch.object(ghost_api.settings, "PHILOSOPHERS_API_ENABLED", True), patch.object(
            ghost_api.settings, "ARXIV_API_ENABLED", True
        ), patch.object(
            ghost_api.settings, "GROUNDING_TOTAL_BUDGET_MS", 5
        ), patch.object(
            ghost_api.settings, "GROUNDING_ADAPTER_TIMEOUT_MS", 800
        ), patch.object(
            ghost_api, "_should_use_philosophers_api", return_value=True
        ), patch.object(
            ghost_api, "_should_use_arxiv_api", return_value=True
        ), patch.object(
            ghost_api, "_should_use_wikidata_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_wikipedia_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_openalex_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_crossref_api", return_value=False
        ), patch.object(
            ghost_api, "_run_external_grounding_job", side_effect=fake_job
        ):
            context = await ghost_api._external_reference_context("compare philosophy and arxiv")

        self.assertIn("[EXTERNAL_GROUNDING_PROVENANCE]", context)
        self.assertIn("attempted_count=2", context)
        self.assertIn("status=timed_out", context)
        self.assertIn("source_count=1", context)
        self.assertIn("[GROUNDING_SOURCE key=philosophers", context)
        self.assertNotIn("[GROUNDING_SOURCE key=arxiv", context)

    async def test_external_reference_context_preserves_empty_statuses(self):
        async def fake_job(spec, user_message, adapter_timeout_s):  # pylint: disable=unused-argument
            return {
                "key": spec.key,
                "label": spec.label,
                "trust_tier": spec.trust_tier,
                "confidence": 0.7,
                "latency_ms": 3.0,
                "status": "empty",
                "error": "",
                "block": "",
            }

        with patch.object(ghost_api.settings, "PHILOSOPHERS_API_ENABLED", True), patch.object(
            ghost_api, "_should_use_philosophers_api", return_value=True
        ), patch.object(
            ghost_api, "_should_use_arxiv_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_wikidata_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_wikipedia_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_openalex_api", return_value=False
        ), patch.object(
            ghost_api, "_should_use_crossref_api", return_value=False
        ), patch.object(
            ghost_api, "_run_external_grounding_job", side_effect=fake_job
        ):
            context = await ghost_api._external_reference_context("Who is Camus?")

        self.assertIn("[EXTERNAL_GROUNDING_PROVENANCE]", context)
        self.assertIn("attempted_count=1", context)
        self.assertIn("source_count=0", context)
        self.assertIn("status=empty", context)
        self.assertNotIn("[GROUNDING_SOURCE key=", context)


if __name__ == "__main__":
    unittest.main()
