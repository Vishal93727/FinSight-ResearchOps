# FinSight AI — Initial Data Model

This is a logical model. Physical tables, indexes, constraints, and migrations will be created phase by phase. All tenant-owned entities carry `tenant_id`; use foreign keys and authorization-aware repositories.

## Core identity and operations

| Entity | Important fields | Purpose |
|---|---|---|
| `tenants` | id, name, created_at | Tenant boundary |
| `users` | id, email, auth_subject, status | User identity mapped to OIDC subject |
| `memberships` | tenant_id, user_id, role | Tenant-scoped role assignments |
| `workspaces` | id, tenant_id, name | Logical project/data workspace |
| `audit_events` | actor_id, tenant_id, action, resource_type/id, decision, created_at | Append-only security/business audit |
| `idempotency_keys` | tenant_id, key, request_hash, response_ref, expires_at | Duplicate request protection |
| `outbox_events` | id, aggregate_type/id, event_type, payload_ref, published_at | Reliable DB-to-queue publishing |
| `job_runs` | id, tenant_id, job_type, status, attempts, error_code, started_at, finished_at | Background job lifecycle |

## Document and research data

| Entity | Important fields | Purpose |
|---|---|---|
| `documents` | id, tenant_id, workspace_id, name, status, current_version_id | Stable document identity |
| `document_versions` | id, document_id, object_key, checksum, source_uri, source_type, parser_version, created_at | Immutable source revision |
| `document_chunks` | id, document_version_id, chunk_index, page_no, section_path, text, token_count, embedding, metadata | Searchable evidence chunks |
| `research_runs` | id, tenant_id, actor_id, company_cik, ticker, as_of_date, graph_version, status | One research execution |
| `research_sources` | id, research_run_id, source_type, source_uri, accession_no, filing_date, checksum | Source manifest |
| `research_citations` | id, research_run_id, document_chunk_id/source_id, claim_ref, excerpt_hash | Citation-to-evidence mapping |
| `research_reports` | id, research_run_id, report_version, content_object_key, reviewer_id, approved_at | Persisted report revisions |

## Financial and risk data

| Entity | Important fields | Purpose |
|---|---|---|
| `transactions_demo` | id, tenant_id, event_time, amount, currency, merchant_ref, channel, synthetic_flag, source_record_id | Demo transaction events |
| `fraud_predictions` | id, transaction_id, model_version_id, feature_version, score, threshold_version, predicted_flag, created_at | Fraud scores with lineage |
| `fraud_alerts` | id, prediction_id, status, reviewer_id, outcome_label, reviewed_at | Human review queue |
| `loan_applications_demo` | id, tenant_id, application_time, feature_snapshot_ref, synthetic_flag, label_window | Demo credit application snapshot |
| `credit_predictions` | id, application_id, model_version_id, probability_default, calibration_version, reason_codes, created_at | Credit-risk output |
| `model_versions` | id, model_name, version, framework, artifact_uri, dataset_fingerprint, feature_version, status | Runtime model lineage |
| `threshold_policies` | id, model_name, version, threshold, rationale, approved_by, active_from | Versioned operating point |

## Analytics model (curated layer)

Build facts only when source tables and definitions are stable:

- `fact_transactions`: transaction count/value by event time, merchant, channel, and customer-demo segment.
- `fact_fraud_reviews`: predicted alert, reviewer decision, confirmed label, review time, and model/threshold version.
- `fact_credit_predictions`: score distribution and later-observed labels, using a defined outcome window.
- `fact_research_activity`: runs, duration, source count, citation count, and verification outcome.
- Dimensions: `dim_date`, `dim_merchant`, `dim_channel`, `dim_model`, and explicitly synthetic customer/account dimensions.

## Data integrity rules

1. A document revision is immutable. Re-ingestion creates a new `document_versions` row.
2. Every embedding row identifies the embedding model and dimension used.
3. Every prediction identifies the model version, feature version, threshold/calibration version, and request timestamp.
4. Labels are separated from features and are available only to evaluation/reporting jobs where authorized.
5. Fraud alert status (`OPEN`, `IN_REVIEW`, `CONFIRMED`, `DISMISSED`) is different from model prediction (`score`, `predicted_flag`).
6. A model score is not the same as a business decision.
7. BI views expose only approved columns and use a read-only database role.
