import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import hallucination_service as hs


class HallucinationServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_assets_dir_is_absolute_and_stable(self):
        assets_path = Path(hs.hallucination_service.assets_dir)
        self.assertTrue(assets_path.is_absolute())
        self.assertEqual(assets_path.name, "dream_assets")
        self.assertEqual(assets_path.parent.name, "data")

    async def test_generate_hallucination_falls_back_when_prompt_expansion_fails(self):
        service = hs.HallucinationService()
        synth = AsyncMock(return_value="/tmp/fallback-sample.png")

        with patch.object(hs.settings, "HALLUCINATION_IMAGE_PROVIDER", "sample"):
            with patch.object(service, "_expand_visual_prompt", new=AsyncMock(return_value=None)):
                with patch.object(service, "_synthesize_image", new=synth):
                    result = await service.generate_hallucination("silence folding into static")

        self.assertIsNotNone(result)
        self.assertIn("asset_url", result)
        self.assertIn("visual_prompt", result)
        used_prompt = synth.await_args.args[0]
        self.assertIn("surreal glitch-art ethereal dark aesthetic", used_prompt)
        self.assertIn("silence folding into static", used_prompt)

    async def test_synthesize_image_returns_sample_when_present(self):
        service = hs.HallucinationService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "sample.png"
            sample.write_bytes(b"\x89PNG\r\n\x1a\n")
            service.assets_dir = tmp_dir
            resolved = await service._synthesize_image("any prompt")
        self.assertEqual(resolved, str(sample))


if __name__ == "__main__":
    unittest.main()
