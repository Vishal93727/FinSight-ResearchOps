# FinSight ResearchOps — Security Baseline

## Phase-one controls implemented

- Passwords are hashed with Python's scrypt KDF and per-password random salts; plaintext passwords are never persisted.
- API access uses expiring signed bearer tokens. Production configuration rejects a weak/default JWT secret and debug mode.
- Every protected endpoint verifies the active user against the database.
- Role-based dependencies enforce server-side permissions.
- Self-registration can only assign the Research Analyst role. Administrator creation is a local CLI operation.
- File snapshots are content-addressed and stored outside the source tree by default.
- Request IDs are attached to responses and copied into audit records.
- Error responses do not expose stack traces or credentials.
- CORS origins are configurable.
- Experiment creation requires an approved hypothesis, a READY immutable data snapshot and a feature set derived from that same snapshot.
- Experiment run submissions validate `Idempotency-Key` and enforce a per-experiment unique index; queue failures remain visible and can be retried with the same key.

## Required deployment actions

1. Copy `.env.example` to `.env` and replace every placeholder.
2. Generate a long random `JWT_SECRET` and a strong database password.
3. Replace `SEC_EDGAR_USER_AGENT` with a monitored contact address before SEC requests.
4. Do not commit `.env`, private datasets, model artifacts, credentials or API keys.
5. Terminate TLS at a trusted reverse proxy for any network-exposed deployment.
6. Restrict PostgreSQL and Redis to private network access; the Compose ports bind to loopback for local use.
7. Use a managed secret store and rotate credentials in deployed environments.
8. Add rate limits, upload size limits, job quotas and concurrency limits before public deployment.

## Role policy

The API currently limits instrument writes to ADMIN/QUANT_RESEARCHER, market ingestions to ADMIN/RESEARCH_ANALYST/QUANT_RESEARCHER, and audit inspection to ADMIN/RISK_REVIEWER. Future model promotion, risk-limit changes and execution permissions must require separate controls and human approval.

## AI safety boundary (future Phase 3)

Uploaded documents and filing text are untrusted input. Agents will have narrow read-only tools, explicit contracts, bounded tool calls and persistent checkpoints. No arbitrary LLM-generated Python execution, unrestricted filesystem/database access, risk configuration changes, model promotion or order submission is permitted.

## Known limitations

- This is an evolving portfolio application, not a certified or regulated financial service.
- Refresh-token rotation, email verification, MFA, account recovery and deployed secret-manager integration are not implemented in Phase 1.
- The local development UI retains the access token in component memory; production session handling requires a separately reviewed design.
- Security scanning and penetration testing remain Phase 5 acceptance work.
