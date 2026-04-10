import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from substrate.adapter import SubstrateManifest
from substrate.discovery import SubstrateDiscoveryService


class SubstrateDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_local_psutil_adapter_and_discovers_manifest(self):
        service = SubstrateDiscoveryService()
        service.load_adapters("local_psutil")
        self.assertIn("local_psutil", service.active_adapters)

        manifests = await service.run_discovery()
        self.assertIn("local_psutil", manifests)
        manifest = manifests["local_psutil"]
        self.assertIsInstance(manifest, SubstrateManifest)
        self.assertEqual(manifest.host_type, "local_psutil")
        self.assertIn("cpu_percent", manifest.sensors)

    async def test_invalid_adapter_name_fails_softly(self):
        service = SubstrateDiscoveryService()
        service.load_adapters("definitely_missing_adapter")
        self.assertEqual(service.active_adapters, {})
        manifests = await service.run_discovery()
        self.assertEqual(manifests, {})


if __name__ == "__main__":
    unittest.main()
