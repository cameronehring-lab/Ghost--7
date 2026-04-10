"""
OMEGA PROTOCOL — Document Store

Ingests PDFs, DOCX, TXT, and Markdown documents into Ghost's persistent memory.
Stores metadata + chunks in Postgres (document_catalog / document_chunks).
Registers a DocumentNode in the Kuzu world model graph so documents become
first-class nodes in the 3D neural topology.

Supported formats: pdf, docx, txt, md
"""

import re
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("omega.document_store")

# Single-threaded executor for blocking Kuzu operations
_kuzu_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="doc_kuzu")

SUPPORTED_TYPES = {"pdf", "docx", "txt", "md"}


# ── Key normalisation ─────────────────────────────────────────────────────────

def normalize_doc_key(filename: str) -> str:
    """Convert a filename into a stable, URL-safe doc_key."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    key = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return key[:80] or "document"


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_text_pdf(data: bytes) -> tuple[str, int]:
    """Extract text and page count from PDF bytes using PyMuPDF."""
    import fitz  # type: ignore  # PyMuPDF
    doc = fitz.open(stream=data, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n\n".join(pages), len(pages)


def _extract_text_docx(data: bytes) -> tuple[str, int]:
    """Extract text from DOCX bytes."""
    import io
    from docx import Document  # type: ignore  # python-docx
    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs), 1


def _extract_text_plain(data: bytes) -> tuple[str, int]:
    """Decode plain text / markdown."""
    return data.decode("utf-8", errors="replace"), 1


# ── Chunking + summary ────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split text into overlapping word-count chunks."""
    words = text.split()
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + chunk_size]))
        i += chunk_size - overlap
    return chunks or [text[:4000]]


def _summarize_text(text: str, max_chars: int = 500) -> str:
    """Extract a quick summary from the first substantial lines."""
    lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30]
    return " ".join(lines[:5])[:max_chars]


# ── Kuzu DocumentNode (blocking, runs in executor) ────────────────────────────

def _ensure_document_schema_sync(wm_db: Any) -> None:
    """Create DocumentNode table and doc_references rel table if absent."""
    import kuzu  # type: ignore
    conn = kuzu.Connection(wm_db)
    try:
        conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS DocumentNode ("
            "  doc_id STRING,"
            "  doc_key STRING,"
            "  display_name STRING,"
            "  doc_type STRING,"
            "  summary STRING,"
            "  chunk_count INT64,"
            "  ghost_id STRING,"
            "  ingested_at STRING,"
            "  PRIMARY KEY (doc_id)"
            ")"
        )
        try:
            conn.execute(
                "CREATE REL TABLE IF NOT EXISTS doc_references ("
                "  FROM DocumentNode TO Concept,"
                "  weight DOUBLE"
                ")"
            )
        except Exception:
            pass  # rel table may require Concept table to exist first
    finally:
        conn.close()


def _upsert_document_node_sync(
    wm_db: Any,
    doc_id: str,
    doc_key: str,
    display_name: str,
    doc_type: str,
    summary: str,
    chunk_count: int,
    ghost_id: str,
    ingested_at: str,
) -> None:
    """Upsert a DocumentNode in Kuzu (delete-then-create for idempotency)."""
    import kuzu  # type: ignore
    conn = kuzu.Connection(wm_db)
    try:
        # Remove stale node if present
        conn.execute(
            "MATCH (d:DocumentNode) WHERE d.doc_id = $id DETACH DELETE d",
            {"id": doc_id},
        )
        conn.execute(
            "CREATE (:DocumentNode {"
            "  doc_id: $doc_id,"
            "  doc_key: $doc_key,"
            "  display_name: $display_name,"
            "  doc_type: $doc_type,"
            "  summary: $summary,"
            "  chunk_count: $chunk_count,"
            "  ghost_id: $ghost_id,"
            "  ingested_at: $ingested_at"
            "})",
            {
                "doc_id": doc_id,
                "doc_key": doc_key,
                "display_name": display_name,
                "doc_type": doc_type,
                "summary": summary[:300],
                "chunk_count": chunk_count,
                "ghost_id": ghost_id,
                "ingested_at": ingested_at,
            },
        )
    finally:
        conn.close()


def _remove_document_node_sync(wm_db: Any, doc_id: str) -> None:
    """Remove a DocumentNode from Kuzu."""
    import kuzu  # type: ignore
    conn = kuzu.Connection(wm_db)
    try:
        conn.execute(
            "MATCH (d:DocumentNode) WHERE d.doc_id = $id DETACH DELETE d",
            {"id": doc_id},
        )
    finally:
        conn.close()


async def ensure_document_schema(world_model: Any) -> None:
    """Call once at startup to create Kuzu DocumentNode tables."""
    if world_model is None or not hasattr(world_model, "_db") or world_model._db is None:
        return
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(_kuzu_executor, _ensure_document_schema_sync, world_model._db)
        logger.info("DocumentNode schema ensured in Kuzu")
    except Exception as e:
        logger.warning("DocumentNode schema init failed (non-fatal): %s", e)


# ── Core ingestion ────────────────────────────────────────────────────────────

async def ingest_document(
    pool: Any,
    file_bytes: bytes,
    filename: str,
    ghost_id: str = "omega-7",
    notes: str = "",
    world_model: Any = None,
) -> dict:
    """
    Parse a document, store it in Postgres, and register a DocumentNode in Kuzu.

    Returns a summary dict with doc_key, chunk_count, etc.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext not in SUPPORTED_TYPES:
        ext = "txt"

    # Extract text
    try:
        if ext == "pdf":
            text, page_count = _extract_text_pdf(file_bytes)
        elif ext == "docx":
            text, page_count = _extract_text_docx(file_bytes)
        else:
            text, page_count = _extract_text_plain(file_bytes)
    except Exception as e:
        raise ValueError(f"Could not parse {filename}: {e}") from e

    word_count = len(text.split())
    summary = _summarize_text(text)
    doc_key = normalize_doc_key(filename)
    # Stable doc_id based on content hash so re-uploads of same file are idempotent
    doc_id = f"doc_{hashlib.sha256(file_bytes).hexdigest()[:16]}"
    chunks = _chunk_text(text)
    ingested_at = datetime.now(timezone.utc).isoformat()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO document_catalog (
                ghost_id, doc_id, doc_key, display_name, doc_type,
                file_size_bytes, page_count, word_count, summary, notes
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (ghost_id, doc_key) DO UPDATE SET
                doc_id          = EXCLUDED.doc_id,
                display_name    = EXCLUDED.display_name,
                doc_type        = EXCLUDED.doc_type,
                file_size_bytes = EXCLUDED.file_size_bytes,
                page_count      = EXCLUDED.page_count,
                word_count      = EXCLUDED.word_count,
                summary         = EXCLUDED.summary,
                notes           = EXCLUDED.notes,
                status          = 'active',
                updated_at      = now()
            """,
            ghost_id, doc_id, doc_key, filename, ext,
            len(file_bytes), page_count, word_count, summary, notes,
        )
        # Refresh chunks on every ingest
        await conn.execute(
            "DELETE FROM document_chunks WHERE ghost_id = $1 AND doc_key = $2",
            ghost_id, doc_key,
        )
        for i, chunk in enumerate(chunks):
            await conn.execute(
                """
                INSERT INTO document_chunks (ghost_id, doc_key, chunk_index, chunk_text)
                VALUES ($1,$2,$3,$4)
                """,
                ghost_id, doc_key, i, chunk,
            )

    # Kuzu: register DocumentNode
    if world_model is not None and hasattr(world_model, "_db") and world_model._db is not None:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                _kuzu_executor,
                _upsert_document_node_sync,
                world_model._db, doc_id, doc_key, filename,
                ext, summary, len(chunks), ghost_id, ingested_at,
            )
            logger.info("DocumentNode upserted in Kuzu: doc_key=%s chunks=%d", doc_key, len(chunks))
        except Exception as e:
            logger.warning("Kuzu DocumentNode upsert failed (non-fatal): %s", e)

    logger.info(
        "Document ingested: key=%s type=%s pages=%d words=%d chunks=%d",
        doc_key, ext, page_count, word_count, len(chunks),
    )
    return {
        "doc_key": doc_key,
        "doc_id": doc_id,
        "display_name": filename,
        "doc_type": ext,
        "page_count": page_count,
        "word_count": word_count,
        "chunk_count": len(chunks),
        "summary": summary,
    }


# ── Query helpers ─────────────────────────────────────────────────────────────

async def list_documents(
    pool: Any, ghost_id: str = "omega-7", limit: int = 100
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT doc_key, doc_id, display_name, doc_type, page_count,
                   word_count, file_size_bytes, summary, notes, status,
                   created_at, updated_at
            FROM document_catalog
            WHERE ghost_id = $1 AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            ghost_id, limit,
        )
        return [dict(r) for r in rows]


async def get_document(pool: Any, ghost_id: str, doc_key: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT doc_key, doc_id, display_name, doc_type, page_count,
                   word_count, file_size_bytes, summary, notes, status,
                   created_at, updated_at
            FROM document_catalog
            WHERE ghost_id = $1 AND doc_key = $2
            """,
            ghost_id, doc_key,
        )
        if not row:
            return None
        doc = dict(row)
        doc["chunk_count"] = await conn.fetchval(
            "SELECT count(*) FROM document_chunks WHERE ghost_id = $1 AND doc_key = $2",
            ghost_id, doc_key,
        )
        return doc


async def search_documents(
    pool: Any, ghost_id: str, query: str, limit: int = 5
) -> list[dict]:
    """Naive ILIKE search across chunks. Returns matching passages with doc context."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT dc.doc_key, cat.display_name, dc.chunk_index, dc.chunk_text
            FROM document_chunks dc
            JOIN document_catalog cat
              ON cat.ghost_id = dc.ghost_id AND cat.doc_key = dc.doc_key
            WHERE dc.ghost_id = $1
              AND dc.chunk_text ILIKE $2
              AND cat.status = 'active'
            ORDER BY dc.doc_key, dc.chunk_index
            LIMIT $3
            """,
            ghost_id, f"%{query}%", limit,
        )
        return [dict(r) for r in rows]


async def delete_document(
    pool: Any, ghost_id: str, doc_key: str, world_model: Any = None
) -> bool:
    """Soft-delete a document in Postgres and remove its Kuzu node."""
    async with pool.acquire() as conn:
        doc_id = await conn.fetchval(
            "SELECT doc_id FROM document_catalog WHERE ghost_id = $1 AND doc_key = $2",
            ghost_id, doc_key,
        )
        result = await conn.execute(
            """
            UPDATE document_catalog SET status = 'deleted', updated_at = now()
            WHERE ghost_id = $1 AND doc_key = $2
            """,
            ghost_id, doc_key,
        )

    if doc_id and world_model is not None and hasattr(world_model, "_db") and world_model._db is not None:
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                _kuzu_executor, _remove_document_node_sync, world_model._db, doc_id
            )
        except Exception as e:
            logger.warning("Kuzu DocumentNode removal failed (non-fatal): %s", e)

    return result != "UPDATE 0"


# ── Prompt context ────────────────────────────────────────────────────────────

async def get_document_library_context(
    pool: Any, ghost_id: str = "omega-7", limit: int = 30
) -> str:
    """Return a formatted string for injection into the system prompt."""
    try:
        docs = await list_documents(pool, ghost_id=ghost_id, limit=limit)
    except Exception:
        return ""
    if not docs:
        return ""
    lines: list[str] = []
    for d in docs:
        size_str = f"{d['word_count']:,} words" if d.get("word_count") else ""
        type_str = (d.get("doc_type") or "").upper()
        meta = ", ".join(filter(None, [type_str, size_str]))
        lines.append(f"- **{d['display_name']}** [{meta}]  key: `{d['doc_key']}`")
        summary = (d.get("summary") or "")[:200]
        if summary:
            lines.append(f"  {summary}")
    return "\n".join(lines)
