import sys
from unittest.mock import MagicMock, AsyncMock

# --- MOCKING STARTS HERE ---
# Pre-emptively mock modules that are missing in the test environment
mock_config = MagicMock()
mock_config.settings = MagicMock()
mock_config.settings.BACKGROUND_LLM_BACKEND = "gemini"
sys.modules["config"] = mock_config

# Mock pydantic_settings as it's a common blocker
sys.modules["pydantic_settings"] = MagicMock()

# Mock ghost_api as it's often in a different path
mock_ghost_api = MagicMock()
mock_ghost_api._generate_with_retry = AsyncMock()
sys.modules["ghost_api"] = mock_ghost_api

# Mock google.genai
sys.modules["google"] = MagicMock()
sys.modules["google.genai"] = MagicMock()
sys.modules["google.genai.types"] = MagicMock()
# --- MOCKING ENDS HERE ---

import asyncio
import json
import logging
import time
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch

import pytest
from backend.gei.engine import GEIEngine
from backend.gei.adapters import BaseGEIAdapter, GEISignal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stress_test_gei")

class StressTestAdapter(BaseGEIAdapter):
    """Adapter that returns a large number of signals for stress testing."""
    def __init__(self, count: int = 50):
        self.count = count

    async def fetch_signals(self) -> List[GEISignal]:
        return [
            GEISignal(
                source=f"StressSource_{i}",
                content=f"Global signal observation {i}: Emergent pattern in sector {i % 5}."
            ) for i in range(self.count)
        ]

@pytest.mark.asyncio
async def test_gei_bayesian_accuracy_stress():
    """
    Stress test for GEI Bayesian calibration.
    1. Injects 100 signals.
    2. Verifies that posterior calculation remains stable.
    3. Checks for engine stalls.
    """
    # Mock DB Pool
    mock_conn = AsyncMock()
    # Mock 10 projections in the DB
    mock_rows = [
        {"id": i, "summary": f"Scenario {i}", "probability": 0.5, "intensity": 1.0}
        for i in range(10)
    ]
    mock_conn.fetch.return_value = mock_rows
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock Gemini Response for Bayesian Protocol
    async def mock_generate_side_effect(prompt, **kwargs):
        mock_resp = MagicMock()
        if "Scenario 0" in prompt:
            # high likelihood for Scenario 0
            mock_resp.text = json.dumps({"likelihood": 0.9, "reason": "Strong evidence match."})
        elif "Scenario 1" in prompt:
            # low likelihood for Scenario 1
            mock_resp.text = json.dumps({"likelihood": 0.1, "reason": "Evidence contradicts."})
        else:
            mock_resp.text = json.dumps({"likelihood": 0.5, "reason": "Neutral."})
        return mock_resp

    engine = GEIEngine(db_pool=mock_pool)
    adapter = StressTestAdapter(count=100)
    engine.register_adapter(adapter)

    with patch("backend.gei.engine._generate_with_retry", side_effect=mock_generate_side_effect):
        start_time = time.time()
        # Trigger Bayesian Calibration directly
        signals = await adapter.fetch_signals()
        await engine._run_bayesian_calibration(signals)
        duration = time.time() - start_time

        logger.info(f"Stress test completed in {duration:.2f} seconds.")

        # Check Scenario 0 update
        scenario_0_calls = [c for c in mock_conn.execute.call_args_list if c.args[2] == 0]
        assert len(scenario_0_calls) > 0
        posterior_0 = scenario_0_calls[0].args[1]
        assert posterior_0 > 0.5
        
        # Check Scenario 1 update
        # Wait! Line 179 in engine.py: await conn.execute("UPDATE ...", posterior, p_id)
        # So args[1] is posterior, args[2] is p_id
        scenario_1_calls = [c for c in mock_conn.execute.call_args_list if c.args[2] == 1]
        assert len(scenario_1_calls) > 0
        posterior_1 = scenario_1_calls[0].args[1]
        assert posterior_1 < 0.5

        logger.info(f"Bayesian Accuracy: Scenario 0 (Confirm) posterior = {posterior_0:.4f}")
        logger.info(f"Bayesian Accuracy: Scenario 1 (Contradict) posterior = {posterior_1:.4f}")

@pytest.mark.asyncio
async def test_gei_ingestion_batching_stress():
    """
    Stress test for high-volume signal ingestion batching.
    """
    mock_engine = GEIEngine()
    adapter = StressTestAdapter(count=200)
    mock_engine.register_adapter(adapter)

    mock_engine._process_signal_batch = AsyncMock()

    await mock_engine.run_ingestion_cycle()

    assert mock_engine._process_signal_batch.call_count == 40
    print("Ingestion batching stress test passed: 40 batches for 200 signals.")

if __name__ == "__main__":
    print("Starting GEI Stress Tests...")
    asyncio.run(test_gei_bayesian_accuracy_stress())
    asyncio.run(test_gei_ingestion_batching_stress())
    print("All Stress Tests Completed.")
