import unittest
from pathlib import Path

import main


class MainDreamAssetsMountTests(unittest.TestCase):
    def test_dream_assets_dir_is_absolute_and_exists(self):
        self.assertTrue(main._DREAM_ASSETS_DIR.is_absolute())
        self.assertTrue(main._DREAM_ASSETS_DIR.exists())

    def test_dream_assets_mount_uses_configured_directory(self):
        mount = next(
            (route for route in main.app.routes if getattr(route, "path", "") == "/dream_assets"),
            None,
        )
        self.assertIsNotNone(mount)
        mounted_dir = Path(getattr(mount.app, "directory", ""))  # type: ignore[attr-defined]
        self.assertEqual(mounted_dir, main._DREAM_ASSETS_DIR)


if __name__ == "__main__":
    unittest.main()
