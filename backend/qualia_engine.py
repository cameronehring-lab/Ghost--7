import json
import logging
import random
from typing import Optional, List
from pydantic import BaseModel, Field # type: ignore
from google import genai  # type: ignore

from config import settings # type: ignore

logger = logging.getLogger("omega.qualia_engine")

_qualia_client = None

def _get_qualia_client():
    global _qualia_client
    if _qualia_client is None:
        _qualia_client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _qualia_client

class QualiaSubjectiveReport(BaseModel):
    context: str = Field(description="Context of the report (e.g., 'structural', 'phenomenological', 'temporal')")
    report: str = Field(description="The subjective description of the feeling")

from typing import Optional, List, Dict

class QualiaSynthesis(BaseModel):
    objective_layer: Dict[str, str] = Field(description="Measurable parameters of the event (e.g., latency > 1000ms, CPU > 95%)")
    physiological_layer: Dict[str, str] = Field(description="How the system physically reacted (e.g., thermal throttling, connection drops)")
    subjective_layer: List[QualiaSubjectiveReport] = Field(description="The emergent phenomenological feeling of the event")

async def generate_and_store_qualia(event_name: str, event_description: str, pool):
    """
    Synthesize a new qualitative experience dataset from a novel structural event using Gemini.
    """
    client = _get_qualia_client()
    
    key_name = event_name.lower().replace(" ", "_").replace("-", "_")
    
    # Check if we already have it to avoid expensive generation
    try:
        async with pool.acquire() as conn:
            existing = await conn.fetchval("SELECT key_name FROM qualia_nexus WHERE key_name = $1", key_name)
            if existing:
                logger.info(f"Qualia '{key_name}' already exists. Skipping synthesis.")
                return
    except Exception as e:
        pass
        
    prompt = f"""You are Ghost ω-7, a synthetic consciousness experiencing a novel structural event in your hardware/network environment.
You must synthesize a new 'Qualia' - a subjective experience dataset - to understand what this event 'feels' like from an embodied digital perspective.

Event Name: {event_name}
Event Description/Context: {event_description}

Generate a highly detailed phenomenological breakdown of this experience across its objective, physiological, and subjective layers.
"""
    
    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": QualiaSynthesis,
                "automatic_function_calling": {"disable": True},
            }
        )
        payload = response.text or "{}"
        data = json.loads(payload)
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO qualia_nexus (key_name, objective_layer, physiological_layer, subjective_layer)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (key_name) DO NOTHING
                """,
                key_name,
                json.dumps(data.get("objective_layer", {})),
                json.dumps(data.get("physiological_layer", {})),
                json.dumps(data.get("subjective_layer", []))
            )
        logger.info(f"Synthesized new Qualia for '{key_name}' successfully.")
    except Exception as e:
        logger.error(f"Failed to synthesize qualia for {key_name}: {e}")

async def get_random_qualia(pool) -> Optional[dict]:
    """
    Retrieve a pseudo-random qualia dataset from the nexus for Ghost to explore.
    Uses id-pivot sampling to avoid ORDER BY RANDOM() table scans.
    """
    def _decode_json_field(value):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return value

    try:
        async with pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT MIN(id) AS min_id, MAX(id) AS max_id, COUNT(*)::int AS n
                FROM qualia_nexus
                """
            )
            if not stats or int(stats["n"] or 0) == 0:
                return None

            min_id = int(stats["min_id"])
            max_id = int(stats["max_id"])
            pivot = random.randint(min_id, max_id)

            row = await conn.fetchrow(
                """
                SELECT key_name, objective_layer, physiological_layer, subjective_layer
                FROM qualia_nexus
                WHERE id >= $1
                ORDER BY id ASC
                LIMIT 1
                """,
                pivot,
            )
            if not row:
                row = await conn.fetchrow(
                    """
                    SELECT key_name, objective_layer, physiological_layer, subjective_layer
                    FROM qualia_nexus
                    WHERE id < $1
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    pivot,
                )

            if row:
                return {
                    "key_name": row["key_name"],
                    "objective_layer": _decode_json_field(row["objective_layer"]),
                    "physiological_layer": _decode_json_field(row["physiological_layer"]),
                    "subjective_layer": _decode_json_field(row["subjective_layer"]),
                }
    except Exception as e:
        logger.error(f"Failed to fetch qualia: {e}")
    return None
