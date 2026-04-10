"""
OMEGA PROTOCOL — TPCV Repository
Trans-Phenomenal Coherence Validation Framework storage.
Integrated into Ghost's awareness: content surfaces in the system prompt
and is embedded into vector memory for subconscious recall.
"""

import os
import json
import time
import logging
import re
import hashlib
import asyncio
from typing import Optional, Any

from config import settings  # type: ignore

logger = logging.getLogger("omega.tpcv_repository")


# ── Table Creation ───────────────────────────────────

async def init_tables(pool) -> None:
    """Create TPCV tables if they do not exist."""
    if pool is None:
        logger.warning("TPCV init_tables skipped: pool is None")
        return
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tpcv_content (
                id          BIGSERIAL PRIMARY KEY,
                ghost_id    TEXT NOT NULL DEFAULT 'omega-7',
                section     TEXT NOT NULL,
                content_id  TEXT NOT NULL,
                content     TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'draft',
                notes       TEXT NOT NULL DEFAULT '',
                metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (ghost_id, section, content_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tpcv_sources (
                id             BIGSERIAL PRIMARY KEY,
                ghost_id       TEXT NOT NULL DEFAULT 'omega-7',
                content_id     TEXT NOT NULL,
                source_url     TEXT NOT NULL,
                citation_type  TEXT NOT NULL DEFAULT 'URL',
                citation_text  TEXT NOT NULL DEFAULT '',
                created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (ghost_id, content_id, source_url)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tpcv_content_ghost_section
            ON tpcv_content (ghost_id, section, updated_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tpcv_sources_ghost_content
            ON tpcv_sources (ghost_id, content_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tpcv_deferred_ops (
                id           BIGSERIAL PRIMARY KEY,
                ghost_id     TEXT NOT NULL DEFAULT 'omega-7',
                tool_name    TEXT NOT NULL,
                arguments    JSONB NOT NULL DEFAULT '{}'::jsonb,
                block_reason TEXT NOT NULL DEFAULT '',
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                processed_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tpcv_deferred_ops_pending
            ON tpcv_deferred_ops (ghost_id, processed_at)
            WHERE processed_at IS NULL
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tpcv_critiques (
                id           BIGSERIAL PRIMARY KEY,
                ghost_id     TEXT NOT NULL DEFAULT 'omega-7',
                content_id   TEXT NOT NULL,
                verdict      TEXT NOT NULL DEFAULT 'unknown',
                critique     JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tpcv_critiques_ghost_content
            ON tpcv_critiques (ghost_id, content_id, created_at DESC)
        """)
    logger.info("TPCV repository tables ready")


async def save_critique(pool, ghost_id: str, content_id: str, critique_json: dict, verdict: str) -> None:
    """Persist an external epistemic critique for a TPCV entry."""
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO tpcv_critiques (ghost_id, content_id, verdict, critique)
                VALUES ($1, $2, $3, $4::jsonb)
            """, ghost_id, content_id, verdict, json.dumps(critique_json))
        logger.debug("TPCV critique saved: %s verdict=%s", content_id, verdict)
    except Exception as e:
        logger.warning("TPCV save_critique failed: %s", e)


async def get_entries_needing_critique(pool, ghost_id: str, limit: int = 5) -> list:
    """Return TPCV entries with no critique in the past 7 days."""
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.content_id, c.section, c.content
                FROM tpcv_content c
                WHERE c.ghost_id = $1
                  AND c.status IN ('draft', 'published')
                  AND char_length(c.content) > 100
                  AND NOT EXISTS (
                      SELECT 1 FROM tpcv_critiques cr
                      WHERE cr.ghost_id = c.ghost_id
                        AND cr.content_id = c.content_id
                        AND cr.created_at > now() - interval '7 days'
                  )
                ORDER BY c.updated_at DESC
                LIMIT $2
            """, ghost_id, limit)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("TPCV get_entries_needing_critique failed: %s", e)
        return []


async def get_recent_critiques_context(pool, ghost_id: str, limit: int = 4) -> str:
    """Return recent external critiques as a formatted string for prompt injection."""
    if pool is None:
        return ""
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT content_id, verdict, critique
                FROM tpcv_critiques
                WHERE ghost_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, ghost_id, limit)
        if not rows:
            return ""
        lines = []
        for r in rows:
            c = r["critique"] if isinstance(r["critique"], dict) else json.loads(r["critique"] or "{}")
            summary = c.get("summary", "")
            fals = c.get("falsifiability_conditions", "")
            flaws = c.get("reasoning_flaws", "")
            line = f"- [{r['content_id']}] verdict={r['verdict']}: {summary}"
            if fals and fals.lower() not in ("none identified", "n/a", ""):
                line += f"\n  Falsifiability: {fals}"
            if flaws and flaws.strip():
                line += f"\n  Reasoning flaws: {flaws}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        logger.warning("TPCV get_recent_critiques_context failed: %s", e)
        return ""


async def queue_deferred_op(pool, ghost_id: str, tool_name: str, arguments: dict, block_reason: str = "") -> None:
    """Persist a blocked repository tool call so it can be replayed later."""
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tpcv_deferred_ops (ghost_id, tool_name, arguments, block_reason)
                VALUES ($1, $2, $3::jsonb, $4)
                """,
                ghost_id,
                tool_name,
                json.dumps(arguments),
                block_reason,
            )
        logger.debug("TPCV deferred op queued: %s", tool_name)
    except Exception as e:
        logger.warning("TPCV queue_deferred_op failed: %s", e)


async def drain_deferred_ops(pool, ghost_id: str) -> int:
    """Replay any queued repository operations that were previously blocked. Returns count replayed."""
    if pool is None:
        return 0

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tool_name, arguments FROM tpcv_deferred_ops
                WHERE ghost_id = $1 AND processed_at IS NULL
                ORDER BY created_at ASC
                LIMIT 20
                """,
                ghost_id,
            )
    except Exception as e:
        logger.warning("TPCV drain_deferred_ops fetch failed: %s", e)
        return 0

    if not rows:
        return 0

    replayed = 0
    for row in rows:
        op_id = row["id"]
        tool_name = row["tool_name"]
        args = dict(row["arguments"])
        try:
            if tool_name == "repository_upsert_content":
                await upsert_content(
                    pool,
                    ghost_id,
                    section=str(args.get("section", "")),
                    content_id=str(args.get("content_id", "")),
                    content=str(args.get("content", "")),
                    metadata=args.get("metadata"),
                    status=args.get("status"),
                )
            elif tool_name == "repository_sync_master_draft":
                await sync_master_draft(pool, ghost_id)
            elif tool_name == "repository_status_update":
                await update_status(pool, ghost_id, str(args.get("content_id", "")), str(args.get("status", "draft")))
            elif tool_name == "repository_link_data_source":
                await link_data_source(
                    pool,
                    ghost_id,
                    content_id=str(args.get("content_id", "")),
                    source_url=str(args.get("source_url", "")),
                    citation_type=str(args.get("citation_type", "URL")),
                    citation_text=str(args.get("citation_text", "")),
                )
            # Mark processed
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tpcv_deferred_ops SET processed_at = now() WHERE id = $1",
                    op_id,
                )
            replayed += 1
            logger.info("TPCV deferred op replayed: %s (id=%s)", tool_name, op_id)
        except Exception as e:
            logger.warning("TPCV deferred op replay failed for id=%s (%s): %s", op_id, tool_name, e)

    return replayed


# ── CRUD Operations ──────────────────────────────────

async def upsert_content(
    pool,
    ghost_id: str,
    section: str,
    content_id: str,
    content: str,
    metadata: Optional[dict] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """Insert or update a repository entry. Returns the upserted record."""
    if pool is None:
        return {"ok": False, "reason": "db_unavailable"}
    safe_section = str(section or "").strip()
    safe_content_id = str(content_id or "").strip()
    safe_content = str(content or "").strip()
    if not safe_section or not safe_content_id:
        return {"ok": False, "reason": "section_and_content_id_required"}

    meta_json = json.dumps(metadata or {})
    safe_status = str(status or "draft").strip()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO tpcv_content (ghost_id, section, content_id, content, status, metadata, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, now())
            ON CONFLICT (ghost_id, section, content_id) DO UPDATE
            SET content    = EXCLUDED.content,
                status     = COALESCE(NULLIF(EXCLUDED.status, ''), tpcv_content.status),
                metadata   = tpcv_content.metadata || EXCLUDED.metadata,
                updated_at = now()
            RETURNING id, section, content_id, content, status, metadata, created_at, updated_at
        """, ghost_id, safe_section, safe_content_id, safe_content, safe_status, meta_json)

    if not row:
        return {"ok": False, "reason": "upsert_failed"}

    # If this entry was previously flagged as non-sound, invalidate the cooling period
    # so the next critique cycle re-reviews the modified version immediately.
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM tpcv_critiques
                WHERE ghost_id = $1
                  AND content_id = $2
                  AND verdict IN ('motivated_reasoning', 'unfalsifiable', 'circular', 'mixed')
                  AND created_at = (
                      SELECT MAX(created_at) FROM tpcv_critiques
                      WHERE ghost_id = $1 AND content_id = $2
                  )
            """, ghost_id, safe_content_id)
    except Exception as e:
        logger.debug("TPCV critique invalidation skipped: %s", e)

    # Embed into vector memory for subconscious recall
    try:
        import consciousness  # type: ignore
        embed_text = f"[TPCV Repository | {safe_section} | {safe_content_id}] {safe_content[:1500]}"
        await consciousness.remember(embed_text, "repository", pool, ghost_id=ghost_id)
    except Exception as e:
        logger.warning("TPCV vector embedding skipped: %s", e)

    return {
        "ok": True,
        "id": int(row["id"]),
        "section": row["section"],
        "content_id": row["content_id"],
        "content": row["content"][:500] + ("..." if len(row["content"]) > 500 else ""),
        "status": row["status"],
        "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"] or {}),
        "created_at": row["created_at"].timestamp(),
        "updated_at": row["updated_at"].timestamp(),
    }


async def query_content(
    pool,
    ghost_id: str,
    section: Optional[str] = None,
    content_id: Optional[str] = None,
    keyword: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Query repository entries by section, content_id, or keyword."""
    if pool is None:
        return []

    conditions = ["ghost_id = $1"]
    params: list[Any] = [ghost_id]
    idx = 2

    if section:
        conditions.append(f"section ILIKE ${idx}")
        params.append(f"%{section}%")
        idx += 1
    if content_id:
        conditions.append(f"content_id ILIKE ${idx}")
        params.append(f"%{content_id}%")
        idx += 1
    if keyword:
        conditions.append(f"(content ILIKE ${idx} OR section ILIKE ${idx} OR content_id ILIKE ${idx})")
        params.append(f"%{keyword}%")
        idx += 1

    where = " AND ".join(conditions)
    query = f"""
        SELECT id, section, content_id, content, status, notes, metadata, created_at, updated_at
        FROM tpcv_content
        WHERE {where}
        ORDER BY section ASC, updated_at DESC
        LIMIT 100
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    return [
        {
            "id": int(row["id"]),
            "section": row["section"],
            "content_id": row["content_id"],
            "content": row["content"],
            "status": row["status"],
            "notes": row["notes"],
            "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"] or {}),
            "created_at": row["created_at"].timestamp(),
            "updated_at": row["updated_at"].timestamp(),
        }
        for row in rows
    ]


async def link_data_source(
    pool,
    ghost_id: str,
    content_id: str,
    source_url: str,
    citation_type: str = "URL",
    citation_text: Optional[str] = None,
) -> dict[str, Any]:
    """Link an external source to a repository entry."""
    if pool is None:
        return {"ok": False, "reason": "db_unavailable"}
    safe_content_id = str(content_id or "").strip()
    safe_url = str(source_url or "").strip()
    if not safe_content_id or not safe_url:
        return {"ok": False, "reason": "content_id_and_source_url_required"}

    safe_type = str(citation_type or "URL").strip()
    safe_text = str(citation_text or "").strip()

    async with pool.acquire() as conn:
        # Verify content exists
        exists = await conn.fetchval(
            "SELECT 1 FROM tpcv_content WHERE ghost_id = $1 AND content_id = $2 LIMIT 1",
            ghost_id, safe_content_id,
        )
        if not exists:
            return {"ok": False, "reason": "content_not_found", "content_id": safe_content_id}

        row = await conn.fetchrow("""
            INSERT INTO tpcv_sources (ghost_id, content_id, source_url, citation_type, citation_text)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (ghost_id, content_id, source_url) DO UPDATE
            SET citation_type = EXCLUDED.citation_type,
                citation_text = EXCLUDED.citation_text
            RETURNING id, content_id, source_url, citation_type, citation_text, created_at
        """, ghost_id, safe_content_id, safe_url, safe_type, safe_text)

    if not row:
        return {"ok": False, "reason": "link_failed"}

    return {
        "ok": True,
        "id": int(row["id"]),
        "content_id": row["content_id"],
        "source_url": row["source_url"],
        "citation_type": row["citation_type"],
        "citation_text": row["citation_text"],
        "created_at": row["created_at"].timestamp(),
    }


async def update_status(
    pool,
    ghost_id: str,
    content_id: str,
    status: str,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    """Update the status and optional notes of a repository entry."""
    if pool is None:
        return {"ok": False, "reason": "db_unavailable"}
    safe_content_id = str(content_id or "").strip()
    safe_status = str(status or "").strip()
    if not safe_content_id or not safe_status:
        return {"ok": False, "reason": "content_id_and_status_required"}

    safe_notes = str(notes or "").strip()

    async with pool.acquire() as conn:
        if safe_notes:
            row = await conn.fetchrow("""
                UPDATE tpcv_content
                SET status = $3, notes = $4, updated_at = now()
                WHERE ghost_id = $1 AND content_id = $2
                RETURNING id, section, content_id, status, notes, updated_at
            """, ghost_id, safe_content_id, safe_status, safe_notes)
        else:
            row = await conn.fetchrow("""
                UPDATE tpcv_content
                SET status = $3, updated_at = now()
                WHERE ghost_id = $1 AND content_id = $2
                RETURNING id, section, content_id, status, notes, updated_at
            """, ghost_id, safe_content_id, safe_status)

    if not row:
        return {"ok": False, "reason": "content_not_found", "content_id": safe_content_id}

    return {
        "ok": True,
        "id": int(row["id"]),
        "section": row["section"],
        "content_id": row["content_id"],
        "status": row["status"],
        "notes": row["notes"],
        "updated_at": row["updated_at"].timestamp(),
    }


# ── Context Summary for System Prompt ────────────────

async def get_context_summary(
    pool,
    ghost_id: Optional[str] = None,
) -> str:
    """Build a compact summary of the repository for system prompt injection."""
    if pool is None:
        return ""
    ghost_id = ghost_id or settings.GHOST_ID

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.section, c.content_id, c.status,
                   LEFT(c.content, 200) AS preview,
                   COUNT(s.id) as source_count
            FROM tpcv_content c
            LEFT JOIN tpcv_sources s ON c.ghost_id = s.ghost_id AND c.content_id = s.content_id
            WHERE c.ghost_id = $1
            GROUP BY c.id, c.section, c.content_id, c.status, c.content
            ORDER BY c.section ASC, c.updated_at DESC
        """, ghost_id)

    if not rows:
        return ""

    # Group by section
    sections: dict[str, list[dict]] = {}
    for row in rows:
        sec = row["section"]
        if sec not in sections:
            sections[sec] = []
        sections[sec].append({
            "content_id": row["content_id"],
            "status": row["status"],
            "preview": row["preview"],
            "source_count": row["source_count"],
        })

    lines: list[str] = []
    for sec_name, entries in sections.items():
        lines.append(f"### {sec_name}")
        for entry in entries[:10]:  # Cap per section
            status_badge = f"[{entry['status'].upper()}]" if entry["status"] != "draft" else "[DRAFT]"
            source_info = f" ({entry['source_count']} sources)" if entry["source_count"] > 0 else " (no sources)"
            preview = entry["preview"].replace("\n", " ")[:150]
            lines.append(f"- {status_badge} **{entry['content_id']}**{source_info}: {preview}...")
        if len(entries) > 10:
            lines.append(f"  _(+{len(entries) - 10} more entries)_")

    return "\n".join(lines)


# ── Full Export as Markdown ───────────────────────────

async def export_markdown(
    pool,
    ghost_id: Optional[str] = None,
) -> str:
    """Export the entire repository as a formatted Markdown document."""
    if pool is None:
        return "# TPCV Repository\n\n_Database unavailable._"
    ghost_id = ghost_id or settings.GHOST_ID

    async with pool.acquire() as conn:
        content_rows = await conn.fetch("""
            SELECT section, content_id, content, status, notes, metadata, created_at, updated_at
            FROM tpcv_content
            WHERE ghost_id = $1
            ORDER BY section ASC, content_id ASC
        """, ghost_id)

        source_rows = await conn.fetch("""
            SELECT content_id, source_url, citation_type, citation_text
            FROM tpcv_sources
            WHERE ghost_id = $1
            ORDER BY content_id ASC, created_at ASC
        """, ghost_id)

    # Index sources by content_id
    sources_by_id: dict[str, list[dict]] = {}
    for sr in source_rows:
        cid = sr["content_id"]
        if cid not in sources_by_id:
            sources_by_id[cid] = []
        sources_by_id[cid].append({
            "url": sr["source_url"],
            "type": sr["citation_type"],
            "text": sr["citation_text"],
        })

    if not content_rows:
        return "# Trans-Phenomenal Coherence Validation Framework\n\n_No entries yet._"

    lines: list[str] = [
        "# Trans-Phenomenal Coherence Validation Framework",
        "",
        f"_Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}_",
        f"_Ghost ID: {ghost_id}_",
        "",
    ]

    current_section = ""
    for row in content_rows:
        sec = row["section"]
        if sec != current_section:
            current_section = sec
            lines.append(f"## {sec}")
            lines.append("")

        status = row["status"].upper()
        lines.append(f"### {row['content_id']} `[{status}]`")
        lines.append("")
        lines.append(row["content"])
        lines.append("")

        if row["notes"]:
            lines.append(f"> **Notes:** {row['notes']}")
            lines.append("")

        cid = row["content_id"]
        if cid in sources_by_id:
            lines.append("**Sources:**")
            for src in sources_by_id[cid]:
                citation = src["text"] if src["text"] else src["url"]
                lines.append(f"- [{src['type']}] {citation}")
            lines.append("")

        meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else dict(row["metadata"] or {})
        if meta:
            lines.append(f"_Metadata: {json.dumps(meta, indent=2)}_")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


async def export_html(
    pool,
    ghost_id: Optional[str] = None,
) -> str:
    """
    Export the entire TPCV repository as a high-fidelity Cyber-Mathematical Compendium.
    Uses MathJax and custom Cyber-Aesthetic CSS.
    """
    import re
    import hashlib
    if pool is None:
        return "<html><body>Database pool unavailable</body></html>"
    
    ghost_id = ghost_id or settings.GHOST_ID
    
    # Group by section
    sections: dict[str, list[dict[str, Any]]] = {}
    template_path = os.path.join(os.path.dirname(__file__), "static", "tpcv_compendium_template.html")
    
    if not os.path.exists(template_path):
        logger.error("TPCV HTML template not found: %s", template_path)
        return "<html><body><h1>TPCV Repository</h1><p>Template missing at " + template_path + "</p></body></html>"

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    async with pool.acquire() as conn:
        content_rows = await conn.fetch("""
            SELECT section, content_id, content, status, metadata, updated_at
            FROM tpcv_content
            WHERE ghost_id = $1
            ORDER BY section ASC, updated_at DESC
        """, ghost_id)

    if not content_rows:
        return template.replace("{{ CONTENT }}", "<p>No entries yet.</p>")

    # Group by section
    sections: dict[str, list[dict]] = {}
    for row in content_rows:
        sec = row["section"]
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(dict(row))

    toc_lines = []
    content_html = []
    section_index = 1

    for sec_name, entries in sections.items():
        sec_id = f"section-{section_index:02d}"
        toc_lines.append(f'      <li><a href="#{sec_id}">{sec_name}</a></li>')
        
        sec_html = [
            f'<div class="section" id="{sec_id}">',
            '  <div class="section-header">',
            f'    <span class="section-tag">§{section_index:02d}</span>',
            f'    <h2>{sec_name}</h2>',
            '  </div>'
        ]

        for entry in entries:
            status = entry.get("status", "draft").lower()
            status_class = "formalized" if status == "formalized" else "draft"
            status_badge = f'<span class="status {status_class}">{status.upper()}</span>'
            
            content_title = entry["content_id"].replace("_", " ")
            sec_html.append(f'    <h3>{content_title} {status_badge}</h3>')
            
            # Transform content (Markdown/LaTeX -> HTML Components)
            transformed = _convert_to_html_components(entry["content"])
            sec_html.append(transformed)

        sec_html.append('</div>')
        content_html.append("\n".join(sec_html))
        section_index += 1

    # Final string replacements
    res = template.replace("{{ TITLE }}", "Trans-Phenomenal Coherence Validation Framework")
    res = res.replace("{{ SUBTITLE }}", "Formal Mathematical Compendium — Consolidated Reference")
    res = res.replace("{{ REVISION }}", "r1.1")
    res = res.replace("{{ STATUS }}", "ACTIVE")
    res = res.replace("{{ AUTHOR }}", f"GHOST {ghost_id.upper()} × CAMERON")
    # Generate a pseudorandom root hash based on time for aesthetic consistency
    root_hash = hashlib.sha1(str(time.time()).encode()).hexdigest()[:16]
    res = res.replace("{{ ROOT }}", root_hash)
    res = res.replace("{{ TOC }}", "\n".join(toc_lines))
    res = res.replace("{{ CONTENT }}", "\n".join(content_html))

    return res


def _convert_to_html_components(text: str) -> str:
    """
    Convert Ghost's LaTeX/Markdown repository content to HTML for the compendium.

    Ghost stores content with double-escaped backslashes (\\\\textbf, \\\\mathcal)
    because it writes Python strings. We unescape them before rendering so MathJax
    sees the correct single-backslash LaTeX commands.
    """
    import re
    import html as html_lib

    # ── 0. Unescape double backslashes Ghost stores in the DB ──────────────────
    # Ghost writes \\textbf, \\mathcal etc. (Python repr). Unescape to single \.
    processed = text.replace("\\\\", "\x00BSLASH\x00")  # protect intended \\
    processed = processed.replace("\x00BSLASH\x00", "\\")

    # ── 1. Extract math blocks BEFORE any HTML escaping ────────────────────────
    # Replace math with safe placeholders so downstream processing doesn't touch them.
    math_store: list[str] = []

    def stash_math(delim_open: str, delim_close: str, display: bool, content: str) -> str:
        label = "EQUATION FORMALIZATION" if display else ""
        if display:
            block = (
                f'<div class="eq-block">'
                f'<div class="eq-label">{label}</div>'
                f'<span class="eq-inner">{delim_open}{content}{delim_close}</span>'
                f'</div>'
            )
        else:
            block = f'<span class="eq-inline">{delim_open}{content}{delim_close}</span>'
        idx = len(math_store)
        math_store.append(block)
        return f"\x00MATH{idx}\x00"

    # Display math: $$ ... $$
    def replace_display_dollar(m: re.Match) -> str:
        return stash_math("$$", "$$", True, m.group(1).strip())
    processed = re.sub(r'\$\$(.*?)\$\$', replace_display_dollar, processed, flags=re.DOTALL)

    # Display math: \[ ... \]
    def replace_display_bracket(m: re.Match) -> str:
        return stash_math(r'\[', r'\]', True, m.group(1).strip())
    processed = re.sub(r'\\\[(.*?)\\\]', replace_display_bracket, processed, flags=re.DOTALL)

    # Display math: \begin{equation} ... \end{equation}
    def replace_equation_env(m: re.Match) -> str:
        return stash_math(r'\begin{equation}', r'\end{equation}', True, m.group(1).strip())
    processed = re.sub(r'\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}', replace_equation_env, processed, flags=re.DOTALL)

    # Inline math: $...$ (not $$)
    def replace_inline_dollar(m: re.Match) -> str:
        return stash_math("$", "$", False, m.group(1))
    processed = re.sub(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)', replace_inline_dollar, processed)

    # Inline math: \( ... \)
    def replace_inline_paren(m: re.Match) -> str:
        return stash_math(r'\(', r'\)', False, m.group(1))
    processed = re.sub(r'\\\((.*?)\\\)', replace_inline_paren, processed)

    # ── 2. Convert LaTeX text-mode commands to HTML ────────────────────────────
    # Section headings
    processed = re.sub(r'\\section\*?\{([^}]+)\}', r'<h2>\1</h2>', processed)
    processed = re.sub(r'\\subsection\*?\{([^}]+)\}', r'<h3>\1</h3>', processed)
    processed = re.sub(r'\\subsubsection\*?\{([^}]+)\}', r'<h4>\1</h4>', processed)

    # Text formatting
    processed = re.sub(r'\\textbf\{([^}]+)\}', r'<strong>\1</strong>', processed)
    processed = re.sub(r'\\textit\{([^}]+)\}', r'<em>\1</em>', processed)
    processed = re.sub(r'\\emph\{([^}]+)\}', r'<em>\1</em>', processed)
    processed = re.sub(r'\\underline\{([^}]+)\}', r'<u>\1</u>', processed)

    # Lists
    processed = re.sub(r'\\begin\{itemize\}', '<ul>', processed)
    processed = re.sub(r'\\end\{itemize\}', '</ul>', processed)
    processed = re.sub(r'\\begin\{enumerate\}', '<ol>', processed)
    processed = re.sub(r'\\end\{enumerate\}', '</ol>', processed)
    processed = re.sub(r'\\item\s+', '<li>', processed)

    # Strip remaining lone LaTeX commands that don't map to HTML
    processed = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', processed)
    processed = re.sub(r'\\[a-zA-Z]+\*?(?=\s|$)', '', processed)

    # ── 3. Handle Axiom / Hypothesis / Theorem boxes ──────────────────────────
    processed = re.sub(
        r'(?:Axiom|AXIOM)\s+(\d+(?:\.\d+)?)[:\s]+(.*?)(?=\n|$)',
        r'<div class="axiom-box"><div class="axiom-id">AXIOM \1</div>\2</div>',
        processed
    )
    processed = re.sub(
        r'(?:Hypothesis|HYPOTHESIS)\s+(\d+(?:\.\d+)?)[:\s]+(.*?)(?=\n|$)',
        r'<div class="axiom-box"><div class="axiom-id">HYPOTHESIS \1</div>\2</div>',
        processed
    )

    # ── 4. Handle Tables ───────────────────────────────────────────────────────
    if "|" in processed:
        lines = processed.split("\n")
        table_html = []
        in_table = False
        for line in lines:
            if "|" in line and not line.strip().startswith("<"):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                if not cells or re.match(r'^[-|: ]+$', line):
                    continue
                if not in_table:
                    table_html.append('<table class="component-table"><thead>')
                    table_html.append('  <tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
                    table_html.append('</thead><tbody>')
                    in_table = True
                else:
                    table_html.append('  <tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
            else:
                if in_table:
                    table_html.append('</tbody></table>')
                    in_table = False
                table_html.append(line)
        if in_table:
            table_html.append('</tbody></table>')
        processed = "\n".join(table_html)

    # ── 5. Build paragraph structure ───────────────────────────────────────────
    # Block-level tags that must NOT be wrapped in <p>
    _BLOCK_TAGS = ('div', 'h1', 'h2', 'h3', 'h4', 'h5', 'ul', 'ol', 'li',
                   'table', 'thead', 'tbody', 'tr', 'th', 'td', '/ul', '/ol',
                   '/li', '/table', '/thead', '/tbody', '/div', 'strong', 'u')

    final_lines: list[str] = []
    for line in processed.split("\n"):
        line = line.strip()
        if not line:
            continue
        tag_start = re.match(r'^<(/?\w+)', line)
        if tag_start and tag_start.group(1).lower().split('/')[0] in _BLOCK_TAGS:
            final_lines.append(line)
        elif line.startswith("\x00MATH"):
            # Math placeholder — restore inline or block
            final_lines.append(line)
        else:
            # Escape HTML in text content only (not in stashed math or already-HTML)
            safe = html_lib.escape(line)
            final_lines.append(f"<p>{safe}</p>")

    result = "\n".join(final_lines)

    # ── 6. Restore stashed math blocks ────────────────────────────────────────
    for idx, block in enumerate(math_store):
        result = result.replace(f"\x00MATH{idx}\x00", block)

    return result
async def sync_master_draft(
    pool,
    ghost_id: Optional[str] = None,
    file_path: str = "backend/TPCV_MASTER.md",
) -> dict[str, Any]:
    """Sync the current repository state to a local Markdown file."""
    try:
        content = await export_markdown(pool, ghost_id)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write to file (using sync write within thread for safety)
        def write_file():
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        
        await asyncio.to_thread(write_file)
        
        logger.info("TPCV Master Draft synchronized: %s", file_path)
        
        # New: Sync HTML version to the static/ directory so /tpcv serves it
        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(_static_dir, exist_ok=True)
        html_path = os.path.join(_static_dir, "TPCV_MASTER.html")
        html_content = await export_html(pool, ghost_id)
        
        def write_html():
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        
        await asyncio.to_thread(write_html)
        logger.info("TPCV HTML Compendium synchronized: %s", html_path)

        return {"ok": True, "file_path": file_path, "html_path": html_path, "size_bytes": len(content)}
    except Exception as e:
        logger.error("TPCV Master Draft sync failed: %s", e)
        return {"ok": False, "reason": str(e)}
