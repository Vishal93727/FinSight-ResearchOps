# Phase 3 Operations — Document Intelligence & Advanced ML

This guide covers the Phase 3 runtime paths. It deliberately distinguishes local/offline defaults from optional services and pretrained models.

## 1. Default local/offline setup

The default configuration uses the deterministic 384-dimensional feature-hash embedder, JSON embedding storage, extractive synthesis, deterministic workflow execution, and no cross-encoder. It does not require an LLM key or a model download.

```bash
cp .env.example .env
# Set a unique POSTGRES_PASSWORD, a strong JWT_SECRET, and a real SEC_EDGAR_USER_AGENT.
docker compose up --build -d
```

The API container applies `alembic upgrade head` before serving requests. Start/inspect workers with:

```bash
docker compose ps
docker compose logs -f api worker redis postgres
```

The worker image includes the base `ml,pdf` extras by default. The `Research Intelligence` page submits document ingestion, evidence-grounded research questions and supervised-ML work as durable jobs. Use **Refresh** to inspect queued/running/completed/failed status. When the broker could not accept a job, the status is `QUEUE_FAILED`; the owner or an ADMIN can use the Retry action, which re-dispatches the same stored job ID.

## 2. PostgreSQL pgvector indexing

The PostgreSQL service in Compose uses `pgvector/pgvector:pg16`. Migration `0006_phase3_evidence_vector_checkpoints` enables the `vector` extension and creates:

- `document_chunks.embedding_vector vector(384)`
- A partial cosine HNSW index (`ix_document_chunks_embedding_hnsw`)

Set these values in `.env` before launching/rebuilding the API and worker:

```dotenv
DOCUMENT_VECTOR_BACKEND=pgvector
DOCUMENT_EMBEDDING_DIMENSIONS=384
DOCUMENT_EMBEDDING_PROVIDER=feature_hash_v1
DOCUMENT_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

The `feature_hash_v1` provider's actual model identifier is `signed_unigram_bigram_hash_v1`; the model setting above is used only by the SentenceTransformer provider. If using learned embeddings, change the provider to `sentence_transformers` and keep the 384-dimensional `all-MiniLM-L6-v2` model. **Re-ingest documents whenever the embedding provider or model changes.** The system blocks queries across incompatible embedding spaces.

After applying migrations, copy existing JSON vectors to pgvector:

```bash
docker compose exec api sh -lc 'PYTHONPATH=src:backend python scripts/backfill_pgvector_embeddings.py --batch-size 250'
```

Check completeness:

```sql
SELECT COUNT(*) AS missing_vectors
FROM document_chunks
WHERE embedding_vector IS NULL;
```

A READY document with missing vectors causes the pgvector query path to fail closed and instructs the operator to backfill. It does not silently switch to a different vector backend. SQLite always uses JSON vectors; the pgvector script refuses non-PostgreSQL databases.

## 3. Optional learned embeddings and reranking

To load the SentenceTransformer embedding model and optional cross-encoder reranker, build with:

```dotenv
PYTHON_EXTRAS=ml,pdf,semantic
DOCUMENT_EMBEDDING_PROVIDER=sentence_transformers
DOCUMENT_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
DOCUMENT_RERANKER=cross_encoder
DOCUMENT_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

Then rebuild API/worker images and ensure model weights are available in the runtime model cache. Model names are stored with the document and report provenance. A changed embedding model requires document re-ingestion; changing only the reranker does not change stored vectors.

## 4. Optional LangGraph and LLM synthesis

```dotenv
PYTHON_EXTRAS=ml,pdf,semantic,research-ai
RESEARCH_WORKFLOW_ENGINE=langgraph
RESEARCH_SYNTHESIS_PROVIDER=langchain_openai
RESEARCH_LLM_MODEL=gpt-4.1-mini
OPENAI_API_KEY=<supply-through-secret-manager-or-runtime-environment>
```

Do not commit API keys or model credentials. The optional LLM receives evidence as untrusted data and is not allowed to approve reports, alter risk controls or submit orders. Every factual sentence still passes citation linkage and lexical/numeric screening, and an independent ADMIN/RISK_REVIEWER approval remains required.

`research_workflow_checkpoints` persists bounded node snapshots containing the query, exact evidence chunk IDs, answer/citation state and claim checks. When a report fails after a committed checkpoint, its author or an ADMIN can call `POST /api/v1/research/reports/{report_id}/resume`. The resume path reuses the exact recorded chunk IDs, verifies source documents are still READY and checks chunk/answer hashes before continuing the remaining nodes. It does not perform fresh retrieval or change the original evidence set. The optional LangGraph adapter still uses the same FinSight checkpoint records; this is explicit workflow-node resume, not LangGraph time-travel or an unbounded graph replay.

## 5. Optional FinBERT sentiment

To enable the `ProsusAI/finbert` provider:

```dotenv
PYTHON_EXTRAS=ml,pdf,finbert
```

Rebuild the image and ensure model weights can be downloaded/cached before selecting FinBERT in the Research Intelligence UI. The lexicon baseline remains the default. The FinBERT adapter returns positive/negative/neutral probabilities and explicit model provenance, but no domain calibration claim is made until a labeled financial-text corpus has been evaluated.

## 6. Queued API routes and retry semantics

- `POST /api/v1/documents/upload/jobs` — bounded upload staging, SHA-256 manifest, `documents.ingest` job, idempotency key.
- `POST /api/v1/ml/evaluations/jobs` — queue a snapshot/feature-pinned supervised model evaluation.
- `POST /api/v1/research/ask/jobs` — queue an evidence-grounded research workflow with an idempotency key; successful jobs expose `report_id` in the job result and persist per-node checkpoints.
- `GET /api/v1/jobs` and `GET /api/v1/jobs/{id}` — owner-scoped inspection; ADMIN can inspect all jobs.
- `POST /api/v1/jobs/{id}/retry` — owner/ADMIN re-dispatch only when the job is `QUEUE_FAILED`.

A queue-dispatch retry does not create a duplicate job. Worker processing is idempotent for completed document, research and ML jobs; research job redelivery recovers the report by its deterministic job/report ID instead of drafting a duplicate. On worker exceptions, the session is rolled back before a FAILED status is committed, preventing partial ORM writes from being committed alongside the failure marker. Domain failures (`FAILED`) are not exposed as successful queue retries; inspect the worker logs and fix the underlying cause before any operator-driven recovery.

## 7. Verification checklist

Offline checks available without external services:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH=src:backend pytest -ra
python -m compileall -q backend src apps migrations
DATABASE_URL=sqlite:///./finsight_phase3_check.db PYTHONPATH=src:backend alembic upgrade head
```

With Docker and model dependencies available, also verify:

1. `alembic upgrade head` against PostgreSQL and inspect the pgvector HNSW index.
2. Upload a new document with pgvector mode and confirm its embedding vector is populated.
3. Backfill prior JSON vectors and run `/research/ask` through pgvector retrieval.
4. Dispatch a document job and an ML evaluation job through Redis/Celery; inspect results and queue-failure retry.
5. Run a SentenceTransformer/cross-encoder/LangGraph/LLM/FinBERT request with cached weights/credentials.
6. Run `cd apps/web && npm ci && npm run build` and exercise the Research Intelligence UI in a browser.

The current sandbox did not have Docker, PostgreSQL, Redis, Celery, PyArrow, Psycopg, Node dependencies or optional model weights/credentials available, so those live checks are not reported as passed.
