# GitHub reference repository catalogue

These repositories are **isolated learning/reference sources**, not code to merge wholesale. Inspect the current README, licence, dependencies, data rights, security posture, and compatibility before reusing any file. Preserve upstream attribution and licence notices.

## Primary implementation references

| Repository | Intended study area | Default branch | GitHub API licence status |
|---|---|---:|---|
| [niharmaddina/quant-strategy-framework](https://github.com/niharmaddina/quant-strategy-framework) | Backtesting, indicators, frozen universes, regression tests | `main` | MIT verified |
| [MustafaBeratYavas/rl-based-algorithmic-trading-and-portfolio-management](https://github.com/MustafaBeratYavas/rl-based-algorithmic-trading-and-portfolio-management) | Gymnasium, PPO/SAC, portfolio evaluation, Docker/testing | `main` | MIT verified |
| [Harshithaaramesh/financial-research-agent](https://github.com/Harshithaaramesh/financial-research-agent) | LangGraph analyst workflow, SEC ingestion, RAG | `main` | MIT verified |
| [mustafagoktugibolar/stock-agent-system](https://github.com/mustafagoktugibolar/stock-agent-system) | Analyst/trading separation, paper execution, portfolio state | `main` | No licence returned by repository metadata; verify before reuse |

## Additional focused references

| Repository | Intended study area | Default branch | GitHub API licence status |
|---|---|---:|---|
| [Speaking-Data-NK/banking-fraud-risk-ml](https://github.com/Speaking-Data-NK/banking-fraud-risk-ml) | Selected MLOps patterns only; fraud/credit are outside the FinSight core product | `main` | MIT verified |
| [AISHDM/stock-market-prediction](https://github.com/AISHDM/stock-market-prediction) | XGBoost, LSTM and sentiment fusion | `main` | Not returned; verify before reuse |
| [maksimprivalov/RLTradingAgent](https://github.com/maksimprivalov/RLTradingAgent) | Small PPO/Gymnasium reference | `main` | No licence verified; do not copy until checked |
| [joel-cdev/machine-learning-alpha-model](https://github.com/joel-cdev/machine-learning-alpha-model) | RF/XGBoost/LSTM and Streamlit experiment patterns | `main` | Not returned; verify before reuse |

## Large architecture/research references

| Repository | Intended study area | Default branch | GitHub API licence status | Download note |
|---|---|---:|---|---|
| [microsoft/qlib](https://github.com/microsoft/qlib) | Quant research concepts and model catalog | `main` | MIT verified | Medium |
| [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent) | Automated research and experimentation ideas | `main` | MIT verified | Large |
| [AI4Finance-Foundation/FinRL-Trading](https://github.com/AI4Finance-Foundation/FinRL-Trading) | FinRL-X modular portfolio allocation | `master` | Apache-2.0 verified | Very large |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | Financial agent and deterministic-analysis patterns | `master` | Apache-2.0 verified | Large |
| [AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) | Financial NLP/model concepts; inspect model-weight terms separately | `master` | MIT verified | Large |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | Multi-agent analyst organization | `main` | Apache-2.0 verified | Medium |
| [openbq-org/OpenBB](https://github.com/openbq-org/OpenBB) | Financial data-provider integration concepts | `develop` | GitHub API reports `NOASSERTION`; inspect repository licence and current stewardship before reuse | Extremely large (~2.4M KB GitHub size metadata at inspection) |

## User's existing DocuMind RAG repository

[Vishal93727/documind-agentic-rag](https://github.com/Vishal93727/documind-agentic-rag) is an optional candidate for evaluating document ingestion/RAG components. It is not a required dependency and its repository origin/licence/dependency compatibility must be verified before incorporating anything into FinSight.

## Safe reuse rules

1. Keep every upstream clone in `references/cloned/<repo-name>/`.
2. Never copy an entire repository into the FinSight application without a file-by-file review.
3. Do not install all upstream dependencies into the FinSight environment.
4. Record the exact upstream URL, commit SHA, copied paths, licence, and modifications in `docs/SOURCES_AND_ATTRIBUTION.md` before reuse.
5. Do not copy secrets, datasets with unclear rights, model weights with incompatible terms, or untrusted generated scripts.
6. Keep FinSight's domain layer and Research-to-Outcome Ledger independently designed.

## Clone count snapshot (2026-11-02)

The clone script contains **16 repository entries**. The current workspace has **0 actual Git clones** under `references/cloned/`. Running `bash scripts/clone_references.sh --all` attempts 15 repositories and skips OpenBB; `bash scripts/clone_references.sh --all-including-openbb` attempts all 16. A catalogue entry or clone script is not evidence that source code has been downloaded.

## Supplied source archives (2026-11-07)

Five of the catalogued repositories were supplied as ZIP archives (no `.git` data, so no commit SHA): Quant Strategy Framework, RL Portfolio Management, Financial Research Agent, Stock Agent System and Banking Fraud and Credit Risk ML. They are not Git clones and were not placed under `references/cloned/`. Licence and reuse decisions for each are in `docs/SOURCES_AND_ATTRIBUTION.md`; four are MIT and Stock Agent System has no licence file, so it stays architecture-only.
