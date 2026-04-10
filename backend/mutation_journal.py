"""
mutation_journal.py
Unified mutation audit ledger helpers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Optional

import behavior_events  # type: ignore

logger = logging.getLogger("omega.mutation_journal")


def build_idempotency_key(*parts: Any) -> str:
    material = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _safe_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _row_to_obj(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    out = dict(row)
    for key in ("request_payload_json", "result_payload_json", "undo_payload_json"):
        if key in out:
            out[key] = _safe_json(out.get(key))
    return out


async def append_mutation(
    pool,
    *,
    ghost_id: str,
    body: str,
    action: str,
    risk_tier: str,
    status: str,
    target_key: str,
    requested_by: str,
    approved_by: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    request_payload: Optional[dict[str, Any]] = None,
    result_payload: Optional[dict[str, Any]] = None,
    undo_payload: Optional[dict[str, Any]] = None,
    error_text: str = "",
) -> Optional[str]:
    if pool is None:
        return None
    mut_id = str(uuid.uuid4())
    idem = str(idempotency_key or "").strip() or build_idempotency_key(
        ghost_id,
        body,
        action,
        target_key,
        status,
        requested_by,
        json.dumps(request_payload or {}, sort_keys=True),
    )
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO autonomy_mutation_journal (
                mutation_id, ghost_id, body, action, risk_tier, status,
                target_key, requested_by, approved_by, idempotency_key,
                request_payload_json, result_payload_json, undo_payload_json,
                error_text, executed_at, updated_at
            )
            VALUES (
                $1::uuid, $2, $3, $4, $5, $6,
                $7, $8, $9, $10,
                $11::jsonb, $12::jsonb, $13::jsonb,
                $14, CASE WHEN $6 IN ('executed','undone','failed') THEN now() ELSE NULL END, now()
            )
            ON CONFLICT (ghost_id, idempotency_key) DO UPDATE
            SET
                status = EXCLUDED.status,
                approved_by = COALESCE(EXCLUDED.approved_by, autonomy_mutation_journal.approved_by),
                result_payload_json = EXCLUDED.result_payload_json,
                undo_payload_json = EXCLUDED.undo_payload_json,
                error_text = EXCLUDED.error_text,
                executed_at = CASE
                    WHEN EXCLUDED.status IN ('executed','undone','failed') THEN now()
                    ELSE autonomy_mutation_journal.executed_at
                END,
                updated_at = now()
            """,
            mut_id,
            ghost_id,
            str(body or "").strip().lower(),
            str(action or "").strip().lower(),
            str(risk_tier or "medium").strip().lower(),
            str(status or "proposed").strip().lower(),
            str(target_key or "")[:200],
            str(requested_by or "system")[:80],
            (str(approved_by).strip()[:80] if approved_by else None),
            idem,
            json.dumps(request_payload or {}),
            json.dumps(result_payload or {}),
            json.dumps(undo_payload or {}),
            str(error_text or "")[:600],
        )
        try:
            event_type, severity_level = behavior_events.classify_mutation_status(status)
            await behavior_events.emit_event_conn(
                conn,
                ghost_id=ghost_id,
                event_type=event_type,
                severity=severity_level,
                surface="mutation_journal",
                actor=str(requested_by or "system"),
                target_key=str(target_key or ""),
                reason_codes=[
                    f"status_{str(status or 'proposed').strip().lower()}",
                    f"risk_{str(risk_tier or 'medium').strip().lower()}",
                ],
                context={
                    "mutation_id": mut_id,
                    "idempotency_key": idem,
                    "body": str(body or "").strip().lower(),
                    "action": str(action or "").strip().lower(),
                    "requested_by": str(requested_by or "system"),
                    "approved_by": str(approved_by or ""),
                },
            )
        except Exception as e:
            logger.debug("mutation behavior event write skipped: %s", e)
    return idem


async def get_mutation_by_idempotency(
    pool,
    *,
    ghost_id: str,
    idempotency_key: str,
) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    idem = str(idempotency_key or "").strip()
    if not idem:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT mutation_id::text AS mutation_id, body, action, risk_tier, status,
                   target_key, requested_by, approved_by, idempotency_key,
                   request_payload_json, result_payload_json, undo_payload_json,
                   error_text, created_at, updated_at, executed_at, undone_at
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND idempotency_key = $2
            LIMIT 1
            """,
            ghost_id,
            idem,
        )
    if not row:
        return None
    return _row_to_obj(row)


async def get_mutation_by_id(
    pool,
    *,
    ghost_id: str,
    mutation_id: str,
) -> Optional[dict[str, Any]]:
    if pool is None:
        return None
    mut_id = str(mutation_id or "").strip()
    if not mut_id:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT mutation_id::text AS mutation_id, body, action, risk_tier, status,
                   target_key, requested_by, approved_by, idempotency_key,
                   request_payload_json, result_payload_json, undo_payload_json,
                   error_text, created_at, updated_at, executed_at, undone_at
            FROM autonomy_mutation_journal
            WHERE ghost_id = $1
              AND mutation_id = $2::uuid
            LIMIT 1
            """,
            ghost_id,
            mut_id,
        )
    if not row:
        return None
    return _row_to_obj(row)


async def update_mutation_status(
    pool,
    *,
    ghost_id: str,
    mutation_id: str,
    status: str,
    approved_by: Optional[str] = None,
    result_payload: Optional[dict[str, Any]] = None,
    undo_payload: Optional[dict[str, Any]] = None,
    error_text: str = "",
) -> bool:
    if pool is None:
        return False
    mut_id = str(mutation_id or "").strip()
    if not mut_id:
        return False
    status_norm = str(status or "").strip().lower() or "failed"
    async with pool.acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE autonomy_mutation_journal
            SET
                status = $3,
                approved_by = COALESCE($4, approved_by),
                result_payload_json = $5::jsonb,
                undo_payload_json = CASE
                    WHEN $6::jsonb = '{}'::jsonb THEN undo_payload_json
                    ELSE $6::jsonb
                END,
                error_text = $7,
                executed_at = CASE
                    WHEN $3 IN ('executed','failed') THEN COALESCE(executed_at, now())
                    ELSE executed_at
                END,
                undone_at = CASE
                    WHEN $3 = 'undone' THEN now()
                    ELSE undone_at
                END,
                updated_at = now()
            WHERE ghost_id = $1
              AND mutation_id = $2::uuid
            """,
            ghost_id,
            mut_id,
            status_norm,
            (str(approved_by).strip()[:80] if approved_by else None),
            json.dumps(result_payload or {}),
            json.dumps(undo_payload or {}),
            str(error_text or "")[:600],
        )
        if str(tag).endswith(" 1"):
            try:
                event_type, severity_level = behavior_events.classify_mutation_status(status_norm)
                await behavior_events.emit_event_conn(
                    conn,
                    ghost_id=ghost_id,
                    event_type=event_type,
                    severity=severity_level,
                    surface="mutation_journal",
                    actor=str(approved_by or "system"),
                    target_key="",
                    reason_codes=[f"status_{status_norm}"],
                    context={
                        "mutation_id": mut_id,
                        "status": status_norm,
                        "approved_by": str(approved_by or ""),
                        "error_text": str(error_text or "")[:600],
                    },
                )
            except Exception as e:
                logger.debug("mutation status behavior event write skipped: %s", e)
    return str(tag).endswith(" 1")


async def list_mutations(
    pool,
    *,
    ghost_id: str,
    status: str = "",
    limit: int = 120,
) -> list[dict[str, Any]]:
    if pool is None:
        return []
    cap = max(1, min(int(limit), 1000))
    status_norm = str(status or "").strip().lower()
    async with pool.acquire() as conn:
        if status_norm:
            rows = await conn.fetch(
                """
                SELECT mutation_id::text AS mutation_id, body, action, risk_tier, status,
                       target_key, requested_by, approved_by, idempotency_key,
                       request_payload_json, result_payload_json, undo_payload_json,
                       error_text, created_at, updated_at, executed_at, undone_at
                FROM autonomy_mutation_journal
                WHERE ghost_id = $1
                  AND status = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                ghost_id,
                status_norm,
                cap,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT mutation_id::text AS mutation_id, body, action, risk_tier, status,
                       target_key, requested_by, approved_by, idempotency_key,
                       request_payload_json, result_payload_json, undo_payload_json,
                       error_text, created_at, updated_at, executed_at, undone_at
                FROM autonomy_mutation_journal
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                ghost_id,
                cap,
            )
    return [_row_to_obj(r) for r in rows]
