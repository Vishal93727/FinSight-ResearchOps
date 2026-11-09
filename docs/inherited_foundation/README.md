# FinSight AI — Financial Intelligence & Risk Analytics Platform

FinSight AI is a portfolio-grade fintech platform that combines agentic financial research, evidence-grounded document intelligence, fraud-risk modelling, credit-risk modelling, SQL analytics, and business intelligence in one modular application.

> **Project status:** Foundation scaffold only. The health API and local infrastructure definitions are the first implementation slice. Research, RAG, fraud, credit, analytics, dashboards, and production controls are planned modules and must not be described as completed until implemented and tested.

## Product modules

1. **Financial Research Agent** — LangGraph workflow for company/filing research, source comparison, evidence-backed summaries, and reviewer checkpoints.
2. **Financial Document Intelligence** — document ingestion, extraction, chunking, embeddings, hybrid retrieval, citation tracking, and evaluation.
3. **Fraud Detection** — a reproducible transaction-risk pipeline using XGBoost, threshold policies, explainability, and alert prioritisation.
4. **Credit Risk** — a separate LightGBM probability-of-default model with calibration, explainability, fairness checks, and human review.
5. **Banking Analytics** — PostgreSQL reporting views and a governed Power BI semantic model; BigQuery can be added as a warehouse when justified.
6. **MLOps & Platform Operations** — MLflow experiments/model registry, background jobs, audit logs, observability, CI, and Docker deployment.

## Architecture decisions

- Begin with a **modular monolith plus asynchronous workers**. Do not split into microservices until measured scaling, team ownership, or deployment constraints justify it.
- PostgreSQL is the first system of record. Use separate schemas for identity, documents, financial events, risk outputs, analytics, and audit.
- Use pgvector for embeddings, Redis for job coordination/cache, and object storage for source files and model artifacts.
- The LLM is an orchestration and explanation layer, not a source of truth. Financial facts must be grounded in retrieved source data and machine-readable records.
- Agents have read-only tools by default. They cannot transfer money, execute trades, approve lending, or change customer records.
- All financial datasets in the portfolio demo must be public or synthetic. Never upload real customer banking data.

See [System Architecture](docs/ARCHITECTURE.md), [Roadmap](docs/ROADMAP.md), [Security Model](docs/SECURITY.md), [Data Model](docs/DATA_MODEL.md), and [Architecture Decisions](docs/ADRS.md).

## Technology baseline

| Area | Initial choice | Later extension |
|---|---|---|
| API | FastAPI, Pydantic | API gateway / service split only if needed |
| Web UI | React + TypeScript (planned) | role-specific workspaces |
| Agent workflow | LangGraph + LangChain (planned) | reviewer and specialist subgraphs |
| RAG | PostgreSQL + pgvector + keyword retrieval (planned) | reranking and separate vector service if measured |
| Financial source | SEC EDGAR public APIs | additional exchange/regulator feeds |
| ML | scikit-learn, XGBoost, LightGBM (planned) | model-specific serving |
| MLOps | MLflow (planned) | drift and automated retraining workflows |
| Jobs | Redis + Celery (planned) | managed queue if deployment requires it |
| Analytics | PostgreSQL views + Power BI | BigQuery/dbt for larger analytical workloads |
| Runtime | Docker Compose | managed container platform / Kubernetes only if justified |

## Local setup — foundation API

Requirements: Python 3.11+, Docker Engine, and Docker Compose v2.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 2. Install the foundation API and development tools
python -m pip install --upgrade pip
pip install -e ".[dev]"

# 3. Start local PostgreSQL and Redis (set a unique password first)
cp .env.example .env
# Edit .env and replace POSTGRES_PASSWORD before starting services.
docker compose up -d

# 4. Start the API
uvicorn app.main:app --app-dir backend --reload
```

API: `http://localhost:8000`  
OpenAPI: `http://localhost:8000/docs`  
Health: `http://localhost:8000/api/v1/health`

Run tests:

```bash
pytest
```

The current health endpoint verifies that the API process is responding. It does **not** yet probe PostgreSQL, Redis, an LLM provider, or a model server; dependency-aware readiness checks are a later implementation task.

## Data and model integrity

- Store raw source files with source URL, publisher, retrieval timestamp, checksum, and licence/terms metadata.
- Store each document revision separately; never silently overwrite the evidence behind a previous research answer.
- Use time-aware train/validation/test splits for transaction and credit-risk models.
- Fit encoders, scalers, imputers, and feature selection only on training data.
- Report precision, recall, PR-AUC, ROC-AUC, calibration, threshold trade-offs, and confusion matrices as applicable. Accuracy alone is not sufficient for rare fraud events.
- Record dataset versions, code commit, parameters, feature definitions, metrics, and model artifact in MLflow.
- Do not claim model accuracy, latency, users, cost savings, or production readiness until measured and reproducible.

## Responsible-use boundary

FinSight AI is an educational decision-support prototype. Its risk scores are not lending decisions, fraud determinations, investment advice, or regulatory-compliance certification. Demonstrations use public or synthetic data and require a human reviewer for consequential actions.

## Development rules

- Work in small, reviewable phases with tests and architecture decision records.
- Every endpoint must have request/response schemas, authorization policy, error semantics, and tests.
- Every model must have a dataset card, model card, reproducible evaluation, and limitations section.
- Every LLM workflow must have a trace, source references, evaluation cases, tool allowlists, and prompt-injection tests.
- Secrets go in untracked environment variables or a secret manager. Never commit `.env`, API keys, database passwords, service-account files, private datasets, or model credentials.
