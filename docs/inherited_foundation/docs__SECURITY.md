# FinSight AI — Security and Responsible-Use Model

## 1. Data classification

| Class | Example | Handling |
|---|---|---|
| Public | SEC filing text, public XBRL facts | Store provenance and retrieval timestamps; obey source access policy |
| Internal demo | Synthetic transactions, model features, demo reports | Tenant/workspace scoped; do not label as customer data |
| Sensitive | Account identifiers, personal/financial data if ever introduced | Excluded from portfolio demo; if introduced later, require explicit purpose, access controls, encryption, retention, and legal review |
| Secrets | API keys, passwords, tokens, signing keys | Secret manager/environment only; never logs, prompts, source files, or Git |

Use public and synthetic data only for the portfolio build. Do not upload real bank/customer data.

## 2. Authentication and authorization

- Use a standard OIDC provider or a reviewed OAuth2/OIDC implementation; do not invent password hashing or token signing.
- Enforce role and resource authorization in backend services, not only in React components.
- Initial roles: `admin`, `analyst`, `risk_reviewer`, `auditor`, `read_only_bi`.
- Every tenant-owned query includes the tenant/workspace predicate. Prefer database constraints and row-level policies as defense in depth.
- Verify authorization before retrieving vector chunks, source documents, research traces, alerts, model outputs, or exports.
- Use short-lived access tokens, secure refresh-token handling, and session revocation.

## 3. File and API boundary

- Enforce upload size, extension, MIME/content signature, decompression limits, and parser timeouts.
- Store uploads outside the web root with opaque object keys; never trust original filenames as paths.
- Scan files where a supported scanner is available. Quarantine parser failures and suspicious files.
- Validate all request schemas; apply per-user rate limits, request-size limits, deadlines, and pagination caps.
- Avoid returning stack traces, SQL errors, secret values, local paths, or internal model prompts to API consumers.
- Use parameterized SQL. The analytics agent, if added, can query only approved read-only views with a row limit, statement timeout, and SQL validation.

## 4. Agent and RAG threat model

Treat user prompts, SEC filings, PDFs, web pages, tool outputs, and retrieved chunks as untrusted data. In particular:

- Indirect prompt injection may be embedded in retrieved source content. It must never grant the source document permission to call tools or override system policy.
- The model must not receive credentials, unrestricted filesystem access, shell access, arbitrary SQL write access, payment APIs, trading APIs, or customer mutation tools.
- Tool permissions are checked by application code for every call; model intent is not authorization.
- Use explicit tool allowlists, typed arguments, bounded loops, maximum tool calls, token/time budgets, and output validation.
- Validate model-generated JSON against Pydantic schemas before it reaches downstream code.
- Citations must refer to stored source IDs and exact chunks; never let the LLM invent URLs or source metadata.
- Provide a clear abstention/insufficient-evidence path. A fluent response is not proof.
- Human approval is required before exporting/sharing high-impact reports or taking future consequential actions.

## 5. Financial model safeguards

- Fraud and credit models return scores and explanations; they do not automatically block transactions, reject applications, or make customer-impacting decisions.
- Features must be point-in-time correct. Exclude post-outcome fields, leakage, labels, and fields unavailable at decision time.
- Preserve training dataset fingerprint, feature code/version, split definition, parameters, metrics, artifact hash, and model version.
- Evaluate minority-class performance and error costs. Do not optimize for accuracy alone.
- Review calibration, drift, stability, subgroup performance, and proxy features; explain limits of SHAP/feature attribution.
- Keep an approval/reviewer record for any simulated policy action.

## 6. Audit, logging, and retention

Audit events should capture actor, tenant, action, resource ID, timestamp, request/job/run ID, result, and policy decision. Do not log secrets, full access tokens, raw uploaded files, or unnecessary PII. Apply retention limits and support deletion of user-scoped demo artifacts.

## 7. Supply chain and deployment

- Pin dependencies and update them deliberately; generate an SBOM and scan container/dependency vulnerabilities before public release.
- Use non-root containers, minimal images, read-only filesystems where practical, and separate service credentials.
- Restrict database network access; expose only required ports.
- Encrypt transport and storage in hosted deployments; rotate secrets and back up databases/object storage.
- Run tests for cross-tenant access, prompt injection, malformed uploads, SQL injection, output injection, rate-limit abuse, and token/cost exhaustion.

## 8. Compliance boundary

This design is not a claim of compliance with RBI, DPDP, GLBA, PCI DSS, or any other legal/regulatory regime. Before using real customer data or operating a financial decision system, obtain qualified security, privacy, legal, and compliance review for the actual deployment jurisdiction and use case.
