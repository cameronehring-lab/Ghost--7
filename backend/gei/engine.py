import asyncio
import logging
import re
import time
import json
from typing import List, Dict, Any, Optional

from config import settings  # type: ignore
from .adapters import BaseGEIAdapter, GEISignal
from ghost_api import _generate_with_retry  # type: ignore
from google.genai import types  # type: ignore

logger = logging.getLogger("omega.gei.engine")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_llm_json(text: str) -> Any:
    """Parse JSON from LLM output, tolerating markdown wrappers and common Gemini quirks."""
    if not text:
        raise ValueError("empty response text")
    # Strip ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    # First attempt: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Repair common Gemini output quirks
    # Python literals → JSON literals
    repaired = re.sub(r'\bNone\b', 'null', cleaned)
    repaired = re.sub(r'\bTrue\b', 'true', repaired)
    repaired = re.sub(r'\bFalse\b', 'false', repaired)
    # Trailing commas before ] or }
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    # Single-quoted strings → double-quoted (simple cases)
    repaired = re.sub(r"(?<![\\])'", '"', repaired)
    return json.loads(repaired)


class GEIEngine:
    """
    Global Event Inducer (GEI) Engine.
    Orchestrates the ingestion (D_DIGS) and induction (P_CAP) of global events.
    """

    def __init__(self, world_model: Any = None, db_pool: Any = None):
        self.world_model = world_model
        self.db_pool = db_pool  # PostgreSQL pool for projections
        self.adapters: List[BaseGEIAdapter] = []
        self._last_cycle_ts = 0.0
        self._last_induction_ts = 0.0
        self._induction_interval = 300.0  # 5 minutes
        self.is_running = False

    def register_adapter(self, adapter: BaseGEIAdapter):
        logger.info("Registering GEI adapter: %s", adapter.name())
        self.adapters.append(adapter)

    async def run_ingestion_cycle(self):
        """Perform one cycle of data ingestion and semantic extraction."""
        logger.info("GEI: Starting ingestion cycle...")
        all_signals: List[GEISignal] = []

        # 1. Fetch signals from all adapters
        for adapter in self.adapters:
            try:
                signals = await adapter.fetch_signals()
                all_signals.extend(signals)
            except Exception as e:
                logger.error("GEI: Adapter %s fetch failed: %s", adapter.name(), e)

        if not all_signals:
            logger.info("GEI: No new signals fetched.")
            return

        # 2. Extract semantic triplets using Gemini
        batch_size = 5
        for i in range(0, len(all_signals), batch_size):
            await self._process_signal_batch(all_signals[i : i + batch_size])

        self._last_cycle_ts = time.time()
        logger.info("GEI: Ingestion cycle complete. Processed %d signals.", len(all_signals))

        # 3. Trigger or Refine Inductions (P_CAP)
        if time.time() - self._last_induction_ts > self._induction_interval:
            await self.run_induction_cycle(source_signals=all_signals)
        else:
            await self._run_bayesian_calibration(all_signals)

    async def _process_signal_batch(self, batch: List[GEISignal]):
        """Use Gemini to extract entities and relations from a batch of signals."""
        signals_text = "\n".join([f"- [{s['source']}] {s['content']}" for s in batch])

        prompt = f"""
        You are the D_DIGS (Data Ingestion) component of Ghost's Global Event Inducer.
        Analyze the following real-time global signals and extract key entities, events, and causal relations.

        SIGNALS:
        {signals_text}

        Format your response as a JSON object with:
        - "observations": A list of extracted core facts/events.
        - "concepts": Key entities or thematic concepts.
        - "relations": Causal or temporal links (Source -> Relation -> Target).
        """

        try:
            response = await _generate_with_retry(
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
                backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
            )

            if response and response.text:
                data = _parse_llm_json(response.text)
                self._write_to_world_model(data)
        except Exception as e:
            logger.error("GEI: Semantic extraction failed: %s", e)

    async def run_induction_cycle(self, source_signals: Optional[List[GEISignal]] = None):
        """Quantum-Inspired Scenario Induction (P_CAP)."""
        logger.info("GEI: Starting induction cycle (P_CAP)...")

        # Build context from recent ingested signals (prefer live; fall back to DB)
        context_lines: List[str] = []

        if source_signals:
            for s in source_signals[:12]:
                context_lines.append(f"- [{s['source']}] {s['content'][:200]}")
        elif self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT summary FROM gei_projections
                        WHERE ghost_id = $1
                        ORDER BY created_at DESC LIMIT 8
                        """,
                        getattr(settings, "GHOST_ID", "omega-7"),
                    )
                    for row in rows:
                        context_lines.append(f"- {row['summary']}")
            except Exception as e:
                logger.warning("GEI: Could not fetch context from DB for induction: %s", e)

        if not context_lines:
            context_lines = ["- Insufficient signal data for this induction cycle."]

        context_text = "\n".join(context_lines)
        source_signal_contents = [s["content"] for s in (source_signals or [])]

        prompt = rf"""
        [ OMEGA GEI INDUCTION PROTOCOL ]
        Induce a superposition of potential future states based on recent world signals:

        {context_text}

        Identify:
        1. Potential Scenarios: Weighted futures ($| \psi \rangle$).
        2. Thermodynamic Intensity: Causal coherence (0.0 to 2.0).
        3. Bayesian Prior: Initial probability.

        Output format: JSON array of objects with keys: "summary", "probability", "intensity", "causal_graph"
        """

        try:
            response = await _generate_with_retry(
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
                backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
            )
            data = _parse_llm_json(response.text)
            if not isinstance(data, list):
                data = [data]
            for scenario in data:
                await self._save_projection(scenario, source_signals=source_signal_contents)
            self._last_induction_ts = time.time()
            logger.info("GEI: Induction cycle complete. Saved %d projections.", len(data))
        except Exception as e:
            logger.error("GEI: Induction failed: %s", e)

    async def _run_bayesian_calibration(self, new_signals: List[GEISignal]):
        """Recalibrate existing projections based on new evidence (A_FUQ)."""
        if not self.db_pool or not new_signals:
            return

        logger.info("GEI: Running Bayesian calibration against %d signals...", len(new_signals))

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, summary, probability, intensity
                    FROM gei_projections
                    WHERE ghost_id = $1
                    ORDER BY created_at DESC LIMIT 10
                    """,
                    getattr(settings, "GHOST_ID", "omega-7"),
                )
                if not rows:
                    return

                evidence_text = "\n".join([f"- {s['content']}" for s in new_signals])

                for row in rows:
                    p_id = row["id"]
                    summary = row["summary"]
                    prior_prob = row["probability"]

                    prompt = f"""
                    [ OMEGA GEI BAYESIAN PROTOCOL ]
                    Projection: {summary} (Prior: {prior_prob})
                    Evidence: {evidence_text}

                    Task: Assess the Likelihood P(Evidence | Projection).
                    - Does the evidence confirm (+1.0), contradict (-1.0), or is it neutral (0.0) to this projection?
                    - Output a 'likelihood_score' between 0.0 and 1.0.

                    Format: JSON: {{"likelihood": <float>, "reason": <string>}}
                    """

                    try:
                        response = await _generate_with_retry(
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.1,
                                response_mime_type="application/json",
                            ),
                            backend_override=getattr(settings, "BACKGROUND_LLM_BACKEND", "gemini"),
                        )
                        res_data = _parse_llm_json(response.text)
                        likelihood = float(res_data.get("likelihood", 0.5))

                        # Bayesian update: P(S|E) proportional to P(E|S) * P(S)
                        numerator = prior_prob * likelihood
                        denominator = numerator + (1 - prior_prob) * (1 - likelihood)
                        posterior = numerator / denominator if denominator > 0 else prior_prob

                        await conn.execute(
                            "UPDATE gei_projections SET probability = $1, updated_at = now() WHERE id = $2",
                            posterior, p_id,
                        )
                        logger.debug(
                            "GEI: Updated projection %s probability: %.2f -> %.2f",
                            p_id, prior_prob, posterior,
                        )
                    except Exception as e:
                        logger.warning("GEI: Bayesian update for projection %s failed: %s", p_id, e)

        except Exception as e:
            logger.error("GEI: Bayesian calibration failed: %s", e)

    async def _save_projection(
        self,
        scenario: Dict[str, Any],
        source_signals: Optional[List[str]] = None,
    ):
        """Persist a generated projection to PostgreSQL with retry logic."""
        if not self.db_pool:
            return

        ghost_id = getattr(settings, "GHOST_ID", "omega-7")
        summary = str(scenario.get("summary") or "Unknown")
        prob = float(scenario.get("probability") or 0.5)
        intensity = float(scenario.get("intensity") or 1.0)
        graph = scenario.get("causal_graph") or {}
        signals_json = json.dumps(source_signals or [])

        for attempt in range(3):
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO gei_projections
                            (ghost_id, summary, probability, intensity, causal_graph_json, source_signals)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
                        """,
                        ghost_id, summary, prob, intensity,
                        json.dumps(graph), signals_json,
                    )
                return
            except Exception as e:
                logger.warning("GEI: Save attempt %d failed: %s", attempt + 1, e)
                await asyncio.sleep(1)

        logger.error("GEI: Failed to save projection after retries: %s", summary)

    def _write_to_world_model(self, data: Dict[str, Any]):
        if not self.world_model:
            return
        for obs in data.get("observations", []):
            try:
                self.world_model.upsert_observation(
                    f"gei_obs_{int(time.time())}_{hash(str(obs)) % 10000}",
                    content=str(obs),
                    source="GEI",
                )
            except Exception as e:
                logger.warning("GEI: WorldModel write failed: %s", e)

    async def run_loop(self, interval_seconds: float = 600.0):
        self.is_running = True
        logger.info("GEI: Starting loop (%.0fs interval)", interval_seconds)
        while self.is_running:
            try:
                await self.run_ingestion_cycle()
            except Exception as e:
                logger.error("GEI: Loop error: %s", e)
            await asyncio.sleep(interval_seconds)
