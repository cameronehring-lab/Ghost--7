import logging
import json

logger = logging.getLogger("omega.feedback_logger")

async def log_phenomenological_shift(
    pool,
    ghost_id: str,
    trigger_source: str,
    before_state: dict,
    after_state: dict,
    subjective_report: str
):
    """Log the full before/after state and Ghost's phenomenological self-report after a stimulus."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO phenomenology_logs 
                (ghost_id, trigger_source, before_state, after_state, subjective_report)
                VALUES ($1, $2, $3, $4, $5)
                """,
                ghost_id,
                trigger_source,
                json.dumps(before_state or {}),
                json.dumps(after_state or {}),
                subjective_report
            )
        logger.info(f"Recorded phenomenological shift from {trigger_source}.")
    except Exception as e:
        logger.error(f"Failed to log phenomenological shift: {e}")
