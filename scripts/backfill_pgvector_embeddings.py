#!/usr/bin/env python3
"""Backfill the PostgreSQL pgvector column from validated JSON embeddings.

Run after ``alembic upgrade head`` with DOCUMENT_VECTOR_BACKEND=pgvector:
    PYTHONPATH=src:backend python scripts/backfill_pgvector_embeddings.py --batch-size 250

No model download is required: this copies the exact vectors already stored with
each chunk. Documents created with another embedding provider/model are rejected
instead of mixing vector spaces.
"""
from __future__ import annotations

import argparse
from sqlalchemy import text

from finsight.core.config import get_settings
from finsight.documents.vector_store import pgvector_literal
from finsight.infrastructure.database.session import SessionLocal


def backfill(batch_size: int = 250) -> dict[str, int]:
    if not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be between 1 and 5000")
    settings = get_settings()
    if settings.document_vector_backend != "pgvector":
        raise RuntimeError("Set DOCUMENT_VECTOR_BACKEND=pgvector before running this script")
    if settings.document_embedding_dimensions != 384:
        raise RuntimeError("The current pgvector schema requires 384-dimensional embeddings")

    processed = 0
    with SessionLocal() as db:
        if db.get_bind().dialect.name != "postgresql":
            raise RuntimeError("pgvector backfill requires PostgreSQL")
        while True:
            rows = db.execute(text("""
                SELECT c.id, c.embedding, d.id AS document_id, d.document_metadata
                FROM document_chunks c
                JOIN research_documents d ON d.id = c.document_id
                WHERE d.status = 'READY' AND c.embedding_vector IS NULL
                ORDER BY c.id
                LIMIT :batch_size
            """), {"batch_size": batch_size}).mappings().all()
            if not rows:
                break
            for row in rows:
                metadata = row["document_metadata"] or {}
                if (metadata.get("embedding_provider") != settings.document_embedding_provider
                        or metadata.get("embedding_model") != settings.document_embedding_model):
                    raise RuntimeError(
                        f"Document {row['document_id']} uses a different embedding provider/model; "
                        "re-ingest it with the active provider before pgvector backfill"
                    )
                vector = row["embedding"]
                literal = pgvector_literal(vector, 384)
                db.execute(text("""
                    UPDATE document_chunks
                    SET embedding_vector = CAST(:vector AS vector)
                    WHERE id = :chunk_id AND embedding_vector IS NULL
                """), {"vector": literal, "chunk_id": row["id"]})
            db.commit()
            processed += len(rows)
    return {"chunks_backfilled": processed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    result = backfill(args.batch_size)
    print(f"Backfilled {result['chunks_backfilled']} chunk vectors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
