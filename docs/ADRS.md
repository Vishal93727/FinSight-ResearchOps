# Architecture Decision Records

## ADR-001 — Modular monolith for the initial application

**Status:** Accepted  
**Decision:** Keep domain logic in one Python package with a separate API process and independently run Celery workers.  
**Reason:** Clear module boundaries and background execution without premature microservice complexity.

## ADR-002 — PostgreSQL as the source of truth

**Status:** Accepted  
**Decision:** Persist identities, instruments, provider metadata, data snapshot manifests, SEC ingestion records, jobs and audit events in PostgreSQL. Use object/file storage for large immutable data artifacts.  
**Reason:** Relational integrity and traceable business records; artifact bytes are not stored in relational columns.

## ADR-003 — Immutable data snapshots

**Status:** Accepted  
**Decision:** Every ingested OHLCV dataset is validated, serialized as a content-addressed Parquet artifact, hashed with SHA-256 and linked to a manifest. SEC submissions fetches are appended as immutable ingestion records.  
**Reason:** A backtest or model run must be attributable to the exact data that was available at the time.

## ADR-004 — Provider adapter boundary

**Status:** Accepted  
**Decision:** SEC EDGAR and future market-data/LLM/broker integrations are accessed behind narrow adapters. User-supplied OHLCV is explicitly labeled `manual_upload`. Provider configuration stored in PostgreSQL must never contain API secrets.  
**Reason:** Provider changes should not leak into domain logic or compromise credential handling.

## ADR-005 — Backend-enforced RBAC

**Status:** Accepted  
**Decision:** Backend dependencies enforce role permissions. Self-registration grants only the Research Analyst role; an administrator is provisioned using a local CLI command after migration.  
**Reason:** Client-side visibility is not an authorization control.

## ADR-006 — Paper-only execution boundary

**Status:** Accepted  
**Decision:** The first release has no real-money trading route. Later paper execution uses deterministic risk checks, idempotent order requests, human approval and an application kill switch.  
**Reason:** The product is an engineering portfolio project for research and simulation, not an investment adviser or brokerage platform.

## ADR-007 — LLMs cannot control risk or execution

**Status:** Accepted  
**Decision:** Future research agents can retrieve evidence and draft proposals but cannot modify deterministic risk limits, promote a model or place an order.  
**Reason:** Keep AI output advisory and auditable; safety-critical controls remain ordinary tested code and human-reviewed workflows.
