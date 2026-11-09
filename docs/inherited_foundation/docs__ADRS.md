# Architecture Decision Records

## ADR-001 — Modular monolith before microservices

**Status:** Accepted  
**Decision:** Build domain modules in one deployable FastAPI application and scale background workers separately.  
**Why:** The portfolio team is small, domain boundaries are still evolving, and one deployment simplifies local development and integration tests.  
**Consequences:** Enforce module boundaries in code; split only after evidence of independent scale, security, release cadence, or ownership requirements.

## ADR-002 — PostgreSQL as the initial system of record

**Status:** Accepted  
**Decision:** Use PostgreSQL for identity, metadata, operational finance demo records, risk results, audit, and reporting views; add pgvector for embeddings.  
**Why:** It gives one transactional boundary and avoids operating multiple databases prematurely. pgvector supports exact and approximate nearest-neighbour search; index choice should follow recall/latency measurement.  
**Consequences:** Use migrations, tenant scoping, query profiling, and separate schemas. BigQuery is an optional future warehouse, not an initial dependency.

## ADR-003 — SEC EDGAR as the first research connector

**Status:** Accepted  
**Decision:** Start financial research with SEC public submissions and XBRL company-facts APIs for supported public issuers.  
**Why:** The SEC exposes public JSON data for submissions and extracted XBRL facts without API keys.  
**Consequences:** Send a descriptive User-Agent, cache results, fetch only needed documents, respect the SEC's fair-access policy (currently no more than 10 requests/second), retain source metadata, and handle issuer-specific reporting/tag differences.

## ADR-004 — No autonomous financial actions

**Status:** Accepted  
**Decision:** Research agents and risk models can read and recommend; they cannot execute trades, transfer funds, approve credit, or mutate customer accounts.  
**Why:** LLM and model outputs are probabilistic and can be manipulated or wrong; consequential financial actions require domain authorization and human governance beyond this portfolio scope.  
**Consequences:** Read-only tools by default, application-side authorization, reviewer gates, audit records, and clear decision-support disclaimers.

## ADR-005 — Separate fraud and credit models

**Status:** Accepted  
**Decision:** Keep fraud and credit-risk pipelines, model cards, labels, metrics, features, thresholds, and release policies independent.  
**Why:** Different target events, time horizons, business costs, evaluation metrics, and fairness concerns.  
**Consequences:** Shared feature utilities may exist, but no shared target or unqualified model promotion.

## ADR-006 — Analytics views before a warehouse

**Status:** Accepted  
**Decision:** Start Power BI from curated PostgreSQL read-only views. Add BigQuery/dbt when source volume, query isolation, or analytical scale justifies it.  
**Why:** One reliable source of truth is easier to reconcile in the first release.  
**Consequences:** Define metric semantics and a star schema early; do not expose mutable OLTP tables directly to general BI users.
