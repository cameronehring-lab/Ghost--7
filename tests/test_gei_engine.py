import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from gei.engine import GEIEngine
from gei.adapters import MockNewsAdapter, GEISignal

class TestGEIEngine(unittest.IsolatedAsyncioTestCase):
    async def test_ingestion_cycle(self):
        # 1. Setup Mock World Model
        mock_wm = MagicMock()
        mock_wm.upsert_observation = MagicMock()
        
        # 2. Instantiate Engine
        engine = GEIEngine(world_model=mock_wm)
        
        # 3. Register Mock Adapter
        adapter = MockNewsAdapter()
        engine.register_adapter(adapter)
        
        # 4. Mock Gemini Call (to avoid real API usage during test)
        # We need to mock _generate_with_retry which is imported in engine.py
        import gei.engine
        gei.engine._generate_with_retry = AsyncMock(return_value=MagicMock(text='{"observations": ["Test event"], "concepts": [], "relations": []}'))
        
        # 5. Run Ingestion Cycle
        await engine.run_ingestion_cycle()
        
        # 6. Verify Mock World Model was called
        self.assertTrue(mock_wm.upsert_observation.called)
        call_args = mock_wm.upsert_observation.call_args[1]
        self.assertEqual(call_args['text'], "Test event")
        self.assertEqual(call_args['source'], "GEI")

if __name__ == '__main__':
    asyncio.run(unittest.main())
