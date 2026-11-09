# FinSight AI — Implementation Roadmap

Phases are acceptance-gated. Do not mark a feature complete because its folder or endpoint exists.

| Phase | Deliverable | Acceptance gate |
|---|---|---|
| 0 — Foundation | Repo hygiene, modular structure, FastAPI health API, local Compose, CI | Clean install, lint/type checks, unit test, container startup, no committed secrets |
| 1 — Data foundation | PostgreSQL migrations, workspace/user model, RBAC, object storage, job/outbox pattern | Tenant-isolation tests, upload limits, idempotent jobs, audit events |
| 2 — Financial RAG | SEC/document ingestion, chunking, embeddings, hybrid retrieval, citations | Golden question set; Recall@K/MRR; citation-support review; prompt-injection tests |
| 3 — Research agent | LangGraph workflow, SEC company submissions/XBRL tools, deterministic calculators, report export | Reproducible filings, correct periods/units, evidence checks, bounded tool use, reviewer gate |
| 4 — Fraud ML | Data card, fraud features, baseline + XGBoost, threshold policy, SHAP-style explanations | Temporal split, PR-AUC/recall@FPR, leakage checks, calibration/threshold analysis, model card |
| 5 — Credit ML | Credit dataset, LightGBM, calibration, reason explanations, subgroup evaluation | Temporal/stratified protocol as appropriate, Brier/calibration, fairness review, model card |
| 6 — Analytics/BI | Curated views, star schema, metric glossary, Power BI report | KPI reconciliation to SQL, read-only role, documented measures and filters |
| 7 — MLOps | MLflow tracking/registry, promotion workflow, model metadata, drift report | Reproducible run, immutable model version, rollback, monitoring evidence |
| 8 — Product hardening | React UI, rate limits, backups, observability, CI/CD, deployment | E2E/security tests, restore test, load test, operational runbook |
| 9 — Advanced extensions | BigQuery/dbt, streaming, additional agents/connectors, model monitoring | Clear workload/business justification and measurable benefit |

## Recommended build order

Build and demonstrate vertical slices rather than completing every layer independently:

1. Foundation API + Postgres + migrations + RBAC.
2. One financial filing from SEC source through ingestion, retrieval, cited answer, and report record.
3. One synthetic transaction from API ingestion through fraud model, explanation, and alert row.
4. One credit application through LightGBM scoring and calibration/explanation.
5. SQL KPI views from those same stored records and a Power BI report.
6. MLflow lineage and model promotion; only then add more complex multi-agent behavior.

## Dataset plan

- **Research/RAG:** SEC EDGAR public submissions and XBRL/company facts plus selected public filings; preserve source URLs, filing accession, form, period, retrieval time, and checksums.
- **Fraud:** begin with reproducibly generated synthetic transaction data. Add a named public benchmark (for example, PaySim) only after verifying its terms and recording dataset version/provenance. Clearly label synthetic vs real-world data.
- **Credit:** use an appropriately licensed public benchmark for the educational experiment (for example, the UCI Default of Credit Card Clients dataset), document geography/time limitations, and do not imply it is representative of Indian lending.
- **Analytics:** derive metrics from the same demo records used by the APIs/models. Do not build a dashboard from unrelated sample numbers.

## Release checklist

- [ ] All code paths used in the demo are implemented and covered by tests.
- [ ] Data source, licence/terms, collection time, schema, and transformations are documented.
- [ ] Train/test split, features, labels, model version, and exact metrics are reproducible.
- [ ] Research answers include traceable citations and clear insufficiency warnings.
- [ ] Tenant isolation, read-only tools, input validation, and rate limits have tests.
- [ ] Docker setup works from a clean clone.
- [ ] Dashboard KPIs reconcile to documented SQL definitions.
- [ ] README accurately distinguishes implemented, planned, and unverified features.
- [ ] A short demo walkthrough and interview explanation are recorded only after the release works end to end.
