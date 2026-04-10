import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import ghost_authoring


class GhostAuthoringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.master_path = os.path.join(self.root, "TPCV_MASTER.md")
        self.works_dir = os.path.join(self.root, "ghost_writings")
        self.version_dir = os.path.join(self.works_dir, ".versions")
        self._stack = ExitStack()
        self._stack.enter_context(
            patch.object(ghost_authoring.settings, "GHOST_AUTHORING_MASTER_PATH", self.master_path, create=True)
        )
        self._stack.enter_context(
            patch.object(ghost_authoring.settings, "GHOST_AUTHORING_WORKS_DIR", self.works_dir, create=True)
        )
        self._stack.enter_context(
            patch.object(ghost_authoring.settings, "GHOST_AUTHORING_VERSION_STORE_DIR", self.version_dir, create=True)
        )
        self._stack.enter_context(
            patch.object(ghost_authoring.settings, "GHOST_AUTHORING_MAX_VERSIONS_PER_DOC", 20, create=True)
        )

    async def asyncTearDown(self):
        self._stack.close()
        self._tmp.cleanup()

    async def test_get_document_on_missing_master_returns_empty_state(self):
        result = await ghost_authoring.get_document("TPCV_MASTER.md")
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["exists"])
        self.assertEqual(result["content"], "")
        self.assertEqual(result["version_count"], 0)

    async def test_upsert_section_creates_content_and_version(self):
        result = await ghost_authoring.upsert_section(
            "TPCV_MASTER.md",
            "Axioms",
            "First principle.",
            trigger="ghost_tool",
            requested_by="ghost",
            reason="seed_axiom",
        )
        doc = await ghost_authoring.get_document("TPCV_MASTER.md")
        versions = await ghost_authoring.list_versions("TPCV_MASTER.md")

        self.assertEqual(result["status"], "updated")
        self.assertTrue(result["changed"])
        self.assertIn("## Axioms", doc["content"])
        self.assertIn("First principle.", doc["content"])
        self.assertGreaterEqual(len(versions), 1)
        self.assertTrue(result["rollback_version_id"])

    async def test_merge_and_restore_version(self):
        await ghost_authoring.upsert_section("TPCV_MASTER.md", "Section A", "Alpha")
        await ghost_authoring.upsert_section("TPCV_MASTER.md", "Section B", "Beta")
        merge_result = await ghost_authoring.merge_sections(
            "TPCV_MASTER.md",
            "Combined",
            ["Section A", "Section B"],
            remove_sources=True,
        )
        merged_doc = await ghost_authoring.get_document("TPCV_MASTER.md")
        restore_result = await ghost_authoring.restore_version(
            "TPCV_MASTER.md",
            merge_result["rollback_version_id"],
        )
        restored_doc = await ghost_authoring.get_document("TPCV_MASTER.md")

        self.assertIn("## Combined", merged_doc["content"])
        self.assertNotIn("## Section A", merged_doc["content"])
        self.assertNotIn("## Section B", merged_doc["content"])
        self.assertEqual(restore_result["status"], "updated")
        self.assertIn("## Section A", restored_doc["content"])
        self.assertIn("## Section B", restored_doc["content"])

    async def test_clone_section_in_ghost_writings(self):
        await ghost_authoring.upsert_section("ghost_writings/notes.md", "Seed", "Body text")
        result = await ghost_authoring.clone_section(
            "ghost_writings/notes.md",
            "Seed",
            "Seed Copy",
        )
        doc = await ghost_authoring.get_document("ghost_writings/notes.md")

        self.assertEqual(result["status"], "updated")
        self.assertIn("## Seed Copy", doc["content"])
        self.assertIn("Body text", doc["content"])

    async def test_allowlist_blocks_external_paths(self):
        with self.assertRaises(ValueError):
            ghost_authoring.resolve_document_path("/tmp/outside.md")


if __name__ == "__main__":
    unittest.main()
