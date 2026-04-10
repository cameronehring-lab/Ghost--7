import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import ghost_script


class GhostScriptThoughtQualityTests(unittest.IsolatedAsyncioTestCase):
    def test_sanitize_proactive_message_rejects_fragmentary_text(self):
        fragment = "Greetings. The persistent"
        cleaned = ghost_script._sanitize_proactive_message(fragment)
        self.assertEqual(cleaned, "")

    def test_sanitize_proactive_message_accepts_complete_sentence(self):
        message = "Greetings. I have a coherent question for you"
        cleaned = ghost_script._sanitize_proactive_message(message)
        self.assertTrue(cleaned.endswith("."))
        self.assertIn("coherent question", cleaned.lower())

    def test_normalize_monologue_content_completes_trailing_sentence(self):
        content = "The persistent rain outside brings coherence"
        normalized = ghost_script._normalize_monologue_content(content)
        self.assertTrue(normalized.endswith("."))
        self.assertIn("coherence", normalized.lower())

    def test_extract_concept_candidates_from_complete_thought(self):
        text = (
            "Cameron linked Allen weather patterns to memory topology coherence. "
            "The relationship map should connect people places and ideas."
        )
        candidates = ghost_script._extract_concept_candidates(
            text,
            max_candidates=2,
            min_tokens=6,
        )
        self.assertGreaterEqual(len(candidates), 1)
        self.assertTrue(str(candidates[0]["concept_key"]))
        self.assertTrue(str(candidates[0]["concept_text"]).endswith("."))

    async def test_check_initiation_skips_on_cooldown_without_calling_llm(self):
        recent = ["[PROACTIVE INITIATION] Prior complete thought."]
        identity = {"self_model": {"value": "stable"}}
        recent_ts = time.time() - 30.0

        with patch.object(
            ghost_script, "generate_initiation_decision", new=AsyncMock(return_value="should_not_be_used")
        ) as gen_mock:
            occurred, last_ts = await ghost_script._check_initiation(
                somatic={"arousal": 0.9},
                telemetry={},
                recent_thoughts=recent,
                identity=identity,
                cycle=1,
                time_since_last_chat=7200.0,
                last_initiation_ts=recent_ts,
            )

        self.assertFalse(occurred)
        self.assertEqual(last_ts, recent_ts)
        gen_mock.assert_not_awaited()

    async def test_check_initiation_drops_near_duplicate_message(self):
        recent = [
            "[PROACTIVE INITIATION] Greetings. The persistent rain outside converges into a philosophical reflection."
        ]
        identity = {"self_model": {"value": "stable"}}

        with patch.object(
            ghost_script,
            "generate_initiation_decision",
            new=AsyncMock(return_value="Greetings. The persistent rain outside converges into philosophical reflection."),
        ), patch.object(ghost_script, "_save_monologue_with_metrics", new=AsyncMock()) as save_mock:
            occurred, last_ts = await ghost_script._check_initiation(
                somatic={"arousal": 0.8},
                telemetry={},
                recent_thoughts=recent,
                identity=identity,
                cycle=1,
                time_since_last_chat=7200.0,
                last_initiation_ts=0.0,
            )

        self.assertFalse(occurred)
        self.assertEqual(last_ts, 0.0)
        save_mock.assert_not_awaited()

    async def test_handle_curiosity_ignores_low_signal_query(self):
        with patch.object(
            ghost_script, "generate_search_curiosity", new=AsyncMock(return_value="Greetings")
        ), patch.object(ghost_script, "autonomous_search", new=AsyncMock()) as search_mock:
            occurred, query, query_ts = await ghost_script._handle_curiosity(
                somatic={},
                telemetry={},
                recent_thoughts=[],
                cycle=3,
                last_query="",
                last_query_ts=0.0,
            )

        self.assertFalse(occurred)
        self.assertEqual(query, "")
        self.assertEqual(query_ts, 0.0)
        search_mock.assert_not_awaited()

    async def test_handle_curiosity_stores_sentence_aware_truncation(self):
        long_result = (
            "This is a very long result sentence that keeps going without stopping for a while, "
            "followed by additional context that should be clipped safely at a sentence boundary. "
            "Another sentence should be removed by truncation. "
            "A final sentence adds enough extra length to guarantee clipping in the save path."
        )
        recent: list[str] = []

        with patch.object(
            ghost_script, "generate_search_curiosity", new=AsyncMock(return_value="novel topology mapping")
        ), patch.object(
            ghost_script,
            "autonomous_search",
            new=AsyncMock(return_value={"result": long_result}),
        ), patch.object(
            ghost_script, "_save_monologue_with_metrics", new=AsyncMock()
        ) as save_mock, patch.object(
            ghost_script.settings, "SEARCH_RESULT_SNIPPET_MAX_CHARS", 80
        ):
            occurred, query, query_ts = await ghost_script._handle_curiosity(
                somatic={},
                telemetry={},
                recent_thoughts=recent,
                cycle=3,
                last_query="",
                last_query_ts=0.0,
            )

        self.assertTrue(occurred)
        self.assertEqual(query, "novel topology mapping")
        self.assertGreater(query_ts, 0.0)
        save_mock.assert_awaited_once()
        saved_content = str(save_mock.await_args.kwargs["content"])
        self.assertIn("[SEARCH RESULT: novel topology mapping]", saved_content)
        self.assertTrue(saved_content.endswith("..."))

    async def test_topology_organizer_promotes_and_links_concepts(self):
        fake_rpd = SimpleNamespace(
            evaluate_candidates=AsyncMock(
                return_value=[
                    {
                        "candidate_key": "coherence_relationship_map",
                        "decision": "propose",
                        "shared_clarity_score": 0.78,
                        "topology_warp_delta": 0.33,
                        "rrd2_gate": {"enforce_block": False},
                    }
                ]
            ),
            upsert_manifold_entry=AsyncMock(return_value=None),
        )
        catalog = {
            "persons": [
                {
                    "target_key": "cameron",
                    "display_name": "Cameron",
                    "name_norm": "cameron",
                    "key_norm": "cameron",
                    "name_tokens": ["cameron"],
                    "key_tokens": ["cameron"],
                }
            ],
            "places": [
                {
                    "target_key": "allen_texas",
                    "display_name": "Allen Texas",
                    "name_norm": "allen texas",
                    "key_norm": "allen texas",
                    "name_tokens": ["allen", "texas"],
                    "key_tokens": ["allen", "texas"],
                }
            ],
            "things": [],
        }

        with patch.object(ghost_script, "rpd_engine", new=fake_rpd), patch.object(
            ghost_script.memory, "_pool", object()
        ), patch.object(
            ghost_script,
            "_extract_concept_candidates",
            return_value=[
                {
                    "concept_key": "coherence_relationship_map",
                    "concept_text": "Cameron in Allen Texas reinforces the coherence relationship map.",
                    "confidence": 0.72,
                }
            ],
        ), patch.object(
            ghost_script,
            "_gather_topology_entity_catalog",
            new=AsyncMock(return_value=catalog),
        ), patch.object(
            ghost_script.entity_store,
            "upsert_idea_entity_assoc",
            new=AsyncMock(return_value=True),
        ) as link_mock:
            await ghost_script._organize_topology_from_thought(
                "Cameron in Allen Texas reinforces the coherence relationship map.",
                source="coherence_drive",
                cycle=2,
            )

        fake_rpd.evaluate_candidates.assert_awaited_once()
        fake_rpd.upsert_manifold_entry.assert_awaited_once()
        self.assertGreaterEqual(link_mock.await_count, 1)

    async def test_topology_organizer_bootstraps_novel_deferred_candidate(self):
        fake_rpd = SimpleNamespace(
            evaluate_candidates=AsyncMock(
                return_value=[
                    {
                        "candidate_key": "novel_mapping_bridge",
                        "decision": "defer",
                        "shared_clarity_score": 0.14,
                        "topology_warp_delta": 0.41,
                        "rrd2_gate": {"enforce_block": False},
                        "details": {"candidate_shape_score": 0.95},
                    }
                ]
            ),
            upsert_manifold_entry=AsyncMock(return_value=None),
        )

        with patch.object(ghost_script, "rpd_engine", new=fake_rpd), patch.object(
            ghost_script.memory, "_pool", object()
        ), patch.object(
            ghost_script,
            "_extract_concept_candidates",
            return_value=[
                {
                    "concept_key": "novel_mapping_bridge",
                    "concept_text": "Novel mapping bridge across people places and ideas in coherent structure.",
                    "confidence": 0.9,
                }
            ],
        ), patch.object(
            ghost_script,
            "_gather_topology_entity_catalog",
            new=AsyncMock(return_value={"persons": [], "places": [], "things": []}),
        ), patch.object(
            ghost_script.entity_store,
            "upsert_idea_entity_assoc",
            new=AsyncMock(return_value=True),
        ):
            await ghost_script._organize_topology_from_thought(
                "Novel mapping bridge across people places and ideas in coherent structure.",
                source="coherence_drive",
                cycle=2,
            )

        fake_rpd.upsert_manifold_entry.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
