import unittest
from unittest.mock import AsyncMock, patch

import main


class RolodexIncludeArchivedQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_rolodex_passes_include_archived_flag(self):
        pool_obj = object()
        fetch_entries = AsyncMock(return_value=[])
        with patch.object(main.memory, "_pool", pool_obj), patch(
            "person_rolodex.fetch_rolodex_with_associations",
            new=fetch_entries,
        ):
            result = await main.get_rolodex(limit=25, include_archived=True)

        fetch_entries.assert_awaited_once_with(
            pool_obj,
            ghost_id=main.settings.GHOST_ID,
            limit=25,
            include_archived=True,
        )
        self.assertEqual(result, {"entries": []})

    async def test_get_rolodex_person_passes_include_archived_flag(self):
        pool_obj = object()
        details_payload = {
            "person_key": "archived_person",
            "display_name": "Archived Person",
            "invalidated_at": 1710000000.0,
            "facts": [],
        }
        fetch_details = AsyncMock(return_value=details_payload)
        with patch.object(main.memory, "_pool", pool_obj), patch(
            "person_rolodex.fetch_person_details",
            new=fetch_details,
        ):
            result = await main.get_rolodex_person("archived_person", fact_limit=33, include_archived=True)

        fetch_details.assert_awaited_once_with(
            pool_obj,
            ghost_id=main.settings.GHOST_ID,
            person_key="archived_person",
            fact_limit=33,
            include_archived=True,
        )
        self.assertEqual(result["person_key"], "archived_person")
        self.assertIsNotNone(result["invalidated_at"])


if __name__ == "__main__":
    unittest.main()
