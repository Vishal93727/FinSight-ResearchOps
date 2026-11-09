# FinSight ResearchOps — Recruiter and Engineering Demonstration

## 12–15 minute end-to-end demo

1. **Platform overview (1 min):** Sign in as a Research Analyst; explain the product as a traceable research-to-outcome ledger, not a trading bot.
2. **Data and hypothesis (2 min):** Open Research Workspace, inspect a versioned market snapshot, create an evidence-linked hypothesis and submit it for review.
3. **Reproducible experiment (2 min):** Open Experiment Lab, select the pinned snapshot and immutable feature-set version, configure chronological train/validation/test windows, queue a baseline run and explain the config fingerprint/idempotency key.
4. **Backtest and risk (2 min):** Compare strategy runs with the benchmark and transaction costs. Explain next-bar execution, walk-forward windows and deterministic review.
5. **Research AI and model governance (2 min):** Demonstrate document citations and report review; inspect a candidate model's artifact hash and independent review before promotion.
6. **Paper execution (1 min):** Create or inspect a paper account, show the order/fill/cash ledger and risk checks. Explicitly point out that no live broker route exists.
7. **Outcome feedback (2 min):** Record forecast/realised observations with model, succeeded experiment-run and paper-account lineage. Import a completed Phase 2 equity curve through `POST /api/v1/feedback/strategies/evaluate-run`; explain path containment and SHA-256 verification. Show MAE/RMSE/bias/directional diagnostics, benchmark-relative strategy metrics, pinned-snapshot PSI/KS drift, generated research suggestions and a human ACCEPTED/DISMISSED decision.
8. **Operations (1–2 min):** Show service/job/model/account counts, Redis versus Celery worker health, stale-job count and recent failure metadata. Open `/metrics`, Prometheus and Grafana; show the API alert rules, worker stale-job dry-run and explicit Admin confirmation before requeue. Explain backup checksum/archive validation, destructive restore confirmation and post-restore smoke checks; show CI/security workflows.

## Engineering questions to be ready for

- **How is reproducibility preserved?** Pinned data snapshot IDs, immutable feature definitions, canonical experiment JSON, SHA-256 fingerprints, seeded experiments and stored evaluation lineage.
- **How do you avoid look-ahead bias?** Chronological windows, point-in-time features, target isolation and next-bar fill conventions; benchmark and feature snapshots remain pinned.
- **Why not let an LLM decide risk?** Deterministic risk policies and human approval are independent of the research assistant. AI suggestions are advisory only.
- **How is model drift detected?** PSI and empirical KS compare reference/current samples; thresholds trigger investigation rather than automatic promotion/retraining.
- **How is the research feedback loop closed?** Prediction outcomes link back to model version, experiment run and paper account where available; summary metrics and suggestions inform a new hypothesis/evaluation.
- **How are workers recovered?** Persisted JobRecord state, stable job IDs, idempotent task handlers, dry-run stale-job listing and explicit Admin dispatch.
- **How are backups protected?** Custom-format PostgreSQL logical dumps, checksum/manifest, restrictive permissions, off-host storage recommendation, explicit restore confirmation and post-restore validation.
- **What remains before production?** Live integration/recovery/load/security validation, TLS/network policy, secret management, object-store backup and calibrated model/provider evaluation.

## Honest demo data policy

Use deterministic synthetic/test fixtures only when clearly labelled. Never present synthetic results as live market performance, never imply simulated paper fills are brokerage fills, and never present model metrics as investment advice or a profitability guarantee.
