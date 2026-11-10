"""Phase 3 document-ingestion, hybrid-retrieval and human-review acceptance tests."""
import hashlib

import pytest
from sqlalchemy import select

from finsight.documents.parsers import parse_document
from finsight.documents.chunking import chunk_text
from finsight.documents.embeddings import embed_text
from finsight.documents.retrieval import RetrievalCandidate, hybrid_retrieve, verify_citations
from finsight.research.graphs.workflow import build_evidence_report
from finsight.documents.models import ResearchDocument, DocumentChunk, ResearchReport
from app.models.entities import Role, User


def _register_user(client, email: str) -> str:
    response = client.post("/api/v1/auth/register", json={
        "email": email, "full_name": "Phase Three User", "password": "A-strong-password-2026",
    })
    assert response.status_code == 201, response.text
    login = client.post("/api/v1/auth/login", data={
        "username": email, "password": "A-strong-password-2026",
    })
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _add_role(db_session, email: str, role_key: str) -> None:
    user = db_session.scalar(select(User).where(User.email == email))
    role = db_session.scalar(select(Role).where(Role.key == role_key))
    assert user is not None and role is not None
    if role not in user.roles:
        user.roles.append(role)
    db_session.commit()


def test_safe_parser_extracts_markdown_and_strips_html_scripts() -> None:
    markdown, meta = parse_document("filing.md", "text/markdown", b"# Revenue\nRevenue increased by 12 percent.")
    assert "Revenue increased" in markdown
    assert meta["parser"] == "finsight-safe-parser-v1"
    html, _ = parse_document("filing.html", "text/html", b"<h1>Revenue</h1><script>steal()</script><p>Sales grew.</p>")
    assert "Revenue" in html and "Sales grew" in html
    assert "steal" not in html


def test_parser_rejects_unsupported_format_and_empty_content() -> None:
    with pytest.raises(ValueError, match="Supported formats"):
        parse_document("binary.exe", "application/octet-stream", b"no")
    with pytest.raises(ValueError, match="no extractable text"):
        parse_document("empty.txt", "text/plain", b" \n\t ")


def test_chunker_obeys_bounds_and_overlap() -> None:
    content = " ".join(f"word{i}" for i in range(140))
    chunks = chunk_text(content, chunk_size=60, overlap=10)
    assert len(chunks) == 3
    assert all(chunk.token_count <= 60 for chunk in chunks)
    assert chunks[0].text.split()[-10:] == chunks[1].text.split()[:10]


def test_embedding_is_deterministic_and_hybrid_retrieval_ranks_relevant_evidence() -> None:
    text = "Operating revenue increased due to cloud subscription growth and margin expansion."
    vector = embed_text(text)
    assert len(vector) == 384
    assert vector == embed_text(text)
    candidates = [
        RetrievalCandidate("c1", "d1", "Annual filing", "annual.md", 0, text,
                           hashlib.sha256(text.encode()).hexdigest(), vector),
        RetrievalCandidate("c2", "d2", "Unrelated note", "note.txt", 0,
                           "The weather will be sunny this weekend.", "b" * 64,
                           embed_text("The weather will be sunny this weekend.")),
    ]
    results = hybrid_retrieve("cloud subscription revenue growth", candidates, top_k=2)
    assert results[0].chunk_id == "c1"
    assert results[0].citation_id == "E1"
    assert verify_citations("Revenue improved [E1]", [{"citation_id": "E1"}])
    assert not verify_citations("Revenue improved [E9]", [{"citation_id": "E1"}])
    assert verify_citations("Revenue improved [E1]", [{"citation_id": "E1"}, {"citation_id": "E2"}])


def test_evidence_workflow_never_claims_approval_without_verified_sources() -> None:
    empty = build_evidence_report("What drove revenue growth?", [])
    assert empty["status"] == "NO_EVIDENCE"
    assert empty["evidence_verified"] is False
    source_text = "Revenue increased because cloud subscription growth improved recurring income."
    evidence = hybrid_retrieve("cloud subscription revenue growth", [RetrievalCandidate(
        "chunk-1", "document-1", "Annual report", "annual.md", 0, source_text,
        hashlib.sha256(source_text.encode()).hexdigest(), embed_text(source_text))])
    report = build_evidence_report("What drove revenue growth?", evidence)
    assert report["status"] == "AWAITING_REVIEW"
    assert report["evidence_verified"] is True
    assert report["claim_checks"]["passed"] is True
    assert report["claim_checks"]["supported_count"] >= 1
    assert "[E1]" in report["answer"]
    assert report["workflow_trace"][-1]["status"] == "awaiting_review"


def test_document_upload_ask_and_independent_human_approval(client, db_session) -> None:
    analyst_email = "phase3.analyst@example.com"
    analyst_token = _register_user(client, analyst_email)
    headers = {"Authorization": f"Bearer {analyst_token}"}
    text = ("The company reported revenue growth of twelve percent. Cloud subscription revenue rose, "
            "operating margins expanded, and management increased its capital expenditure outlook. "
            "The annual filing notes that enterprise demand improved during the fiscal year.")
    uploaded = client.post("/api/v1/documents/upload", headers=headers,
        data={"title": "Annual report extract"},
        files={"file": ("annual-report.txt", text.encode(), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["status"] == "READY" and document["chunk_count"] >= 1
    assert document["document_metadata"]["embedding_provider"] == "feature_hash_v1"
    assert document["document_metadata"]["embedding_model"] == "signed_unigram_bigram_hash_v1"
    assert len(document["content_sha256"]) == 64
    duplicate = client.post("/api/v1/documents/upload", headers=headers,
        files={"file": ("another-name.txt", text.encode(), "text/plain")})
    assert duplicate.status_code == 409

    ask = client.post("/api/v1/research/ask", headers=headers,
        json={"query": "What explains the cloud subscription revenue growth?", "top_k": 4})
    assert ask.status_code == 201, ask.text
    report = ask.json()
    assert report["status"] == "AWAITING_REVIEW"
    assert report["evidence_verified"] is True
    assert report["claim_checks"]["passed"] is True
    assert report["claim_checks"]["supported_count"] >= 1
    assert report["citations"][0]["document_id"] == document["id"]
    assert db_session.get(ResearchReport, report["id"]) is not None
    assert db_session.get(ResearchDocument, document["id"]) is not None
    assert db_session.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document["id"])) is not None
    checkpoints = client.get(f"/api/v1/research/reports/{report['id']}/checkpoints", headers=headers)
    assert checkpoints.status_code == 200
    assert [item["node"] for item in checkpoints.json()] == [
        "validate_query", "retrieve_evidence", "synthesize", "verify_citations", "human_review"]

    own_review = client.post(f"/api/v1/research/reports/{report['id']}/decision", headers=headers,
        json={"decision": "APPROVE", "comment": "Same-user approval is not permitted"})
    assert own_review.status_code == 403

    reviewer_email = "phase3.reviewer@example.com"
    reviewer_token = _register_user(client, reviewer_email)
    _add_role(db_session, reviewer_email, "RISK_REVIEWER")
    reviewer_token = client.post("/api/v1/auth/login", data={
        "username": reviewer_email, "password": "A-strong-password-2026",
    }).json()["access_token"]
    approved = client.post(f"/api/v1/research/reports/{report['id']}/decision",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        json={"decision": "APPROVE", "comment": "Citations checked against the supplied filing extract."})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["reviewer_user_id"] is not None


def test_no_evidence_report_cannot_be_approved(client) -> None:
    token = _register_user(client, "phase3.noevidence@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/research/ask", headers=headers,
        json={"query": "What is the outlook for an untracked company?"})
    assert response.status_code == 201
    assert response.json()["status"] == "NO_EVIDENCE"
    assert response.json()["evidence_verified"] is False


def test_retrieval_uses_injected_embedding_provider_and_rejects_dimension_mismatch() -> None:
    from finsight.documents.retrieval import hybrid_retrieve

    class StubProvider:
        name = "stub"
        model_name = "test-v1"
        dimensions = 96

        def embed(self, text: str) -> list[float]:
            return [1.0] + [0.0] * 95

    text = "Revenue increased due to stronger subscriptions."
    provider = StubProvider()
    candidate = RetrievalCandidate("c", "d", "Report", "report.txt", 0, text,
        hashlib.sha256(text.encode()).hexdigest(), provider.embed(text))
    retrieved = hybrid_retrieve("revenue subscriptions", [candidate], embedding_provider=provider)
    assert retrieved and retrieved[0].chunk_id == "c"
    bad_candidate = RetrievalCandidate("x", "d", "Report", "report.txt", 1, text,
        hashlib.sha256(text.encode()).hexdigest(), [0.0] * 384)
    with pytest.raises(ValueError, match="do not match"):
        hybrid_retrieve("revenue subscriptions", [bad_candidate], embedding_provider=provider)


def test_optional_langgraph_engine_fails_closed_when_extra_is_missing() -> None:
    import importlib.util

    if importlib.util.find_spec("langgraph") is not None:
        pytest.skip("LangGraph is installed; graph execution is covered by the optional integration environment")
    with pytest.raises(RuntimeError, match="research-ai"):
        build_evidence_report("What drove company revenue?", [], workflow_engine="langgraph")


def test_unknown_workflow_engine_is_rejected() -> None:
    with pytest.raises(ValueError, match="workflow_engine"):
        build_evidence_report("What drove company revenue?", [], workflow_engine="remote")


def test_langchain_synthesizer_cites_only_supplied_evidence_with_untrusted_source_prompt() -> None:
    from types import SimpleNamespace
    from finsight.research.graphs.workflow import LangChainOpenAISynthesizer

    source_text = "Cloud subscription revenue increased by twelve percent."
    evidence = hybrid_retrieve("cloud subscription revenue increased", [RetrievalCandidate(
        "chunk-llm", "doc-llm", "Annual filing", "annual.txt", 0, source_text,
        hashlib.sha256(source_text.encode()).hexdigest(), embed_text(source_text))])

    class StubChatModel:
        messages = None
        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content="Cloud subscription revenue increased [E1].")

    model = StubChatModel()
    synthesizer = LangChainOpenAISynthesizer(chat_model=model)
    report = build_evidence_report("What happened to cloud revenue?", evidence, synthesizer=synthesizer)
    assert report["status"] == "AWAITING_REVIEW"
    assert "untrusted data" in model.messages[0][1]
    assert "Cloud subscription revenue increased" in model.messages[1][1]


def test_langchain_synthesizer_invalid_citation_blocks_human_review() -> None:
    from types import SimpleNamespace
    from finsight.research.graphs.workflow import LangChainOpenAISynthesizer

    text = "Operating margins expanded this year."
    evidence = hybrid_retrieve("operating margins expanded", [RetrievalCandidate(
        "chunk-invalid", "doc-invalid", "Annual filing", "annual.txt", 0, text,
        hashlib.sha256(text.encode()).hexdigest(), embed_text(text))])
    synthesizer = LangChainOpenAISynthesizer(
        chat_model=SimpleNamespace(invoke=lambda messages: SimpleNamespace(content="Margins improved [E99].")))
    report = build_evidence_report("What happened to margins?", evidence, synthesizer=synthesizer)
    assert report["evidence_verified"] is False
    assert report["status"] == "NO_EVIDENCE"


def test_claim_support_requires_citation_and_matching_numeric_evidence() -> None:
    from finsight.documents.retrieval import evaluate_claim_support
    citations = [{"citation_id": "E1", "excerpt": "Quarterly revenue grew 12% as subscription demand expanded."}]
    passed = evaluate_claim_support("Quarterly revenue grew 12% as subscription demand expanded. [E1]", citations)
    assert passed["passed"] is True
    unsupported_number = evaluate_claim_support("Quarterly revenue grew 18% as subscription demand expanded. [E1]", citations)
    assert unsupported_number["passed"] is False
    assert unsupported_number["checks"][0]["reason"] == "numeric_value_not_found"
    uncited = evaluate_claim_support("Quarterly revenue grew 12% as subscription demand expanded.", citations)
    assert uncited["passed"] is False


def test_cross_encoder_reranker_changes_rank_and_persists_score() -> None:
    from finsight.documents.retrieval import RetrievalCandidate, hybrid_retrieve
    from finsight.documents.embeddings import embed_text
    import hashlib

    texts = [
        "Cloud subscription revenue and operating margin increased during the fiscal year.",
        "The filing discusses cloud revenue growth, margins and enterprise demand.",
    ]
    candidates = [RetrievalCandidate(f"c{i}", f"d{i}", f"Document {i}", f"doc{i}.txt", 0,
        text, hashlib.sha256(text.encode()).hexdigest(), embed_text(text)) for i, text in enumerate(texts)]
    class StubReranker:
        name = "stub_cross_encoder"
        model_name = "stub-v1"
        def score(self, query, texts):
            return [0.95 if "enterprise demand" in text else 0.1 for text in texts]
    results = hybrid_retrieve("cloud revenue growth and margins", candidates, top_k=1, reranker=StubReranker())
    assert results[0].chunk_id == "c1"
    assert results[0].rerank_score == 1.0


def test_async_document_ingestion_job_is_staged_idempotent_and_processed(client, db_session, tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace
    from pathlib import Path
    from app.api.v1 import documents as documents_api
    from finsight.infrastructure.database.models import JobRecord
    import app.services.document_jobs as document_jobs

    email = "phase3.async.document@example.com"
    token = _register_user(client, email)
    _add_role(db_session, email, "RESEARCH_ANALYST")
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    settings = SimpleNamespace(data_storage_path=str(tmp_path), max_document_upload_bytes=2_000_000,
        document_chunk_size=420, document_chunk_overlap=60, max_document_chunks=1000,
        document_embedding_provider="feature_hash_v1", document_embedding_dimensions=384,
        document_embedding_model="sentence-transformers/all-MiniLM-L6-v2", document_vector_backend="json")
    monkeypatch.setattr(documents_api, "get_settings", lambda: settings)
    monkeypatch.setattr(documents_api, "enqueue_document_ingestion", lambda job_id: None)
    monkeypatch.setattr(document_jobs, "get_settings", lambda: settings)
    payload = ("The issuer reported subscription revenue growth and improved operating margins. "
               "Management described stronger enterprise demand during the fiscal year.").encode()
    response = client.post("/api/v1/documents/upload/jobs", headers={"Authorization": f"Bearer {token}"},
        data={"idempotency_key": "document-ingest-0001", "title": "Queued filing"},
        files={"file": ("queued-filing.txt", payload, "text/plain")})
    assert response.status_code == 202, response.text
    job = db_session.get(JobRecord, response.json()["id"])
    assert job is not None and job.status == "QUEUED"
    staged = Path(job.payload["staged_path"])
    assert staged.exists()
    repeated = client.post("/api/v1/documents/upload/jobs", headers={"Authorization": f"Bearer {token}"},
        data={"idempotency_key": "document-ingest-0001", "title": "Queued filing"},
        files={"file": ("queued-filing.txt", payload, "text/plain")})
    assert repeated.status_code == 202 and repeated.json()["id"] == job.id
    result = document_jobs.process_document_ingestion_job(db_session, job)
    assert result["status"] == "succeeded"
    assert job.status == "SUCCEEDED" and job.result["document_id"]
    assert not staged.exists()



def test_pgvector_literal_requires_finite_384_dimension_values() -> None:
    import math
    from finsight.documents.vector_store import pgvector_literal

    literal = pgvector_literal([0.25] + [0.0] * 383)
    assert literal.startswith("[0.25,0,0") and literal.endswith("]")
    with pytest.raises(ValueError, match="exactly 384"):
        pgvector_literal([0.0] * 383)
    with pytest.raises(ValueError, match="finite"):
        pgvector_literal([math.nan] + [0.0] * 383)
    with pytest.raises(ValueError, match="finite"):
        pgvector_literal([True] + [0.0] * 383)


def test_queue_failed_document_job_is_visible_and_retryable(client, db_session, tmp_path, monkeypatch) -> None:
    from sqlalchemy import select
    from app.api.v1 import documents as documents_api, jobs as jobs_api
    from finsight.infrastructure.database.models import JobRecord

    email = "phase3.retry.document@example.com"
    token = _register_user(client, email)
    _add_role(db_session, email, "RESEARCH_ANALYST")
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    monkeypatch.setattr(documents_api, "get_settings", lambda: type("Settings", (), {
        "data_storage_path": str(tmp_path), "max_document_upload_bytes": 2_000_000})())

    def fail_dispatch(job_id: str) -> None:
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(documents_api, "enqueue_document_ingestion", fail_dispatch)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/v1/documents/upload/jobs", headers=headers,
        data={"idempotency_key": "document-retry-0001"},
        files={"file": ("retry-filing.txt", b"Issuer revenue increased with subscription growth.", "text/plain")})
    assert response.status_code == 503
    job = db_session.scalar(select(JobRecord).where(JobRecord.task_name == "documents.ingest"))
    assert job is not None and job.status == "QUEUE_FAILED"

    listed = client.get("/api/v1/jobs?limit=10", headers=headers)
    assert listed.status_code == 200 and any(item["id"] == job.id for item in listed.json())

    dispatched: list[str] = []
    monkeypatch.setattr(jobs_api, "enqueue_document_ingestion", lambda job_id: dispatched.append(job_id))
    retry = client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)
    assert retry.status_code == 202, retry.text
    assert retry.json()["status"] == "QUEUED"
    assert dispatched == [job.id]


def test_ml_evaluation_queue_is_idempotent_and_retriable(client, db_session, monkeypatch) -> None:
    from sqlalchemy import select
    from app.api.v1 import ml as ml_api, jobs as jobs_api
    from finsight.infrastructure.database.models import JobRecord

    email = "phase3.ml.queue@example.com"
    token = _register_user(client, email)
    _add_role(db_session, email, "QUANT_RESEARCHER")
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    attempts: list[str] = []

    def fail_dispatch(job_id: str) -> None:
        attempts.append(job_id)
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(ml_api, "enqueue_model_evaluation", fail_dispatch)
    payload = {
        "dataset_snapshot_id": "snapshot-phase3-001",
        "feature_set_version_id": "feature-phase3-001",
        "model_family": "ridge",
        "idempotency_key": "ml-evaluation-retry-0001",
    }
    failed = client.post("/api/v1/ml/evaluations/jobs", headers=headers, json=payload)
    assert failed.status_code == 503
    job = db_session.scalar(select(JobRecord).where(JobRecord.task_name == "ml.evaluate"))
    assert job is not None and job.status == "QUEUE_FAILED"
    assert attempts == [job.id]

    # A replay with the same key returns the existing failed job; it does not enqueue a duplicate.
    replay = client.post("/api/v1/ml/evaluations/jobs", headers=headers, json=payload)
    assert replay.status_code == 202
    assert replay.json()["id"] == job.id
    assert attempts == [job.id]

    dispatched: list[str] = []
    monkeypatch.setattr(jobs_api, "enqueue_model_evaluation", lambda job_id: dispatched.append(job_id))
    retry = client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)
    assert retry.status_code == 202, retry.text
    assert retry.json()["status"] == "QUEUED"
    assert dispatched == [job.id]


def test_worker_failure_marker_rolls_back_partial_writes(client, db_session) -> None:
    from app.services.worker_state import mark_failed_after_rollback
    from finsight.infrastructure.database.models import AuditEvent, JobRecord
    from app.models.entities import User

    _register_user(client, "phase3.worker.rollback@example.com")
    user = db_session.scalar(select(User).where(User.email == "phase3.worker.rollback@example.com"))
    assert user is not None
    job = JobRecord(task_name="documents.ingest", status="RUNNING", payload={}, created_by=user.id)
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    # Simulate an uncommitted partial audit/domain write before the worker catches an error.
    marker = AuditEvent(action="test.partial_write", resource_type="test", resource_id=job_id,
        actor_user_id=user.id, details={})
    db_session.add(marker)
    db_session.flush()
    mark_failed_after_rollback(db_session, JobRecord, job_id, "ValueError")

    refreshed = db_session.get(JobRecord, job_id)
    assert refreshed is not None and refreshed.status == "FAILED"
    assert refreshed.error_message == "ValueError"
    assert db_session.scalar(select(AuditEvent).where(AuditEvent.action == "test.partial_write",
        AuditEvent.resource_id == job_id)) is None


def test_claim_support_checks_short_claims_and_keeps_citations_with_their_sentence() -> None:
    from finsight.documents.retrieval import evaluate_claim_support

    citations = [
        {"citation_id": "E1", "excerpt": "Quarterly revenue rose 12% during the period."},
        {"citation_id": "E2", "excerpt": "Operating expenses declined 5% year over year."},
    ]
    supported = evaluate_claim_support("Revenue rose 12%. [E1] Operating expenses declined 5%. [E2]", citations)
    assert supported["passed"] is True
    assert supported["claim_count"] == 2
    assert [item["best_citation_id"] for item in supported["checks"]] == ["E1", "E2"]

    short_unsupported = evaluate_claim_support("Revenue rose 18%. [E1]", citations)
    assert short_unsupported["passed"] is False
    assert short_unsupported["claim_count"] == 1
    assert short_unsupported["checks"][0]["reason"] == "numeric_value_not_found"


def test_document_upload_idempotency_key_cannot_alias_another_job_type(client, db_session) -> None:
    from finsight.infrastructure.database.models import JobRecord
    from app.models.entities import User

    email = "phase3.document.key-collision@example.com"
    _register_user(client, email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    _add_role(db_session, email, "RESEARCH_ANALYST")
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    db_session.add(JobRecord(task_name="system.ping", status="QUEUE_FAILED", payload={},
        idempotency_key="cross-type-key-0001", created_by=user.id))
    db_session.commit()

    response = client.post("/api/v1/documents/upload/jobs", headers=headers,
        data={"idempotency_key": "cross-type-key-0001"},
        files={"file": ("different.txt", b"A different document body.", "text/plain")})
    assert response.status_code == 409
    assert "different job or document" in response.json()["detail"]


def test_worker_failure_marker_never_overwrites_succeeded_job(client, db_session) -> None:
    from app.services.worker_state import mark_failed_after_rollback
    from finsight.infrastructure.database.models import JobRecord
    from app.models.entities import User

    email = "phase3.worker.success-guard@example.com"
    _register_user(client, email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    job = JobRecord(task_name="documents.ingest", status="SUCCEEDED", payload={},
        result={"document_id": "already-done"}, created_by=user.id)
    db_session.add(job)
    db_session.commit()
    mark_failed_after_rollback(db_session, JobRecord, job.id, "LateFailure")
    db_session.refresh(job)
    assert job.status == "SUCCEEDED"
    assert job.result == {"document_id": "already-done"}


def test_research_question_is_queued_idempotently_and_retryable(client, db_session, monkeypatch) -> None:
    from sqlalchemy import select
    from app.api.v1 import ai_research as research_api, jobs as jobs_api
    from finsight.infrastructure.database.models import JobRecord

    email = "phase3.research.queue@example.com"
    token = _register_user(client, email)
    _add_role(db_session, email, "RESEARCH_ANALYST")
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    attempts: list[str] = []

    def fail_dispatch(job_id: str) -> None:
        attempts.append(job_id)
        raise RuntimeError("Redis unavailable")

    monkeypatch.setattr(research_api, "enqueue_research_ask", fail_dispatch)
    payload = {
        "query": "What explains the company's recurring revenue growth?",
        "top_k": 5,
        "lexical_weight": 0.45,
        "diversity_weight": 0.15,
        "idempotency_key": "research-question-queue-0001",
    }
    failed = client.post("/api/v1/research/ask/jobs", headers=headers, json=payload)
    assert failed.status_code == 503
    job = db_session.scalar(select(JobRecord).where(JobRecord.task_name == "research.ask"))
    assert job is not None and job.status == "QUEUE_FAILED"
    assert attempts == [job.id]

    replay = client.post("/api/v1/research/ask/jobs", headers=headers, json=payload)
    assert replay.status_code == 202
    assert replay.json()["id"] == job.id
    assert attempts == [job.id]

    changed_payload = payload | {"query": "What explains a different company's revenue?"}
    collision = client.post("/api/v1/research/ask/jobs", headers=headers, json=changed_payload)
    assert collision.status_code == 409

    dispatched: list[str] = []
    monkeypatch.setattr(jobs_api, "enqueue_research_ask", lambda job_id: dispatched.append(job_id))
    retry = client.post(f"/api/v1/jobs/{job.id}/retry", headers=headers)
    assert retry.status_code == 202, retry.text
    assert retry.json()["status"] == "QUEUED"
    assert dispatched == [job.id]


def test_research_question_queue_requires_research_role(client, db_session) -> None:
    email = "phase3.research.viewer@example.com"
    token = _register_user(client, email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.roles = [db_session.scalar(select(Role).where(Role.key == "READ_ONLY_VIEWER"))]
    db_session.commit()
    token = client.post("/api/v1/auth/login", data={"username": email,
        "password": "A-strong-password-2026"}).json()["access_token"]
    response = client.post("/api/v1/research/ask/jobs", headers={"Authorization": f"Bearer {token}"},
        json={"query": "What explains the company's recurring revenue growth?",
              "idempotency_key": "research-viewer-key-0001"})
    assert response.status_code == 403


def test_research_job_worker_persists_report_and_recovers_redelivery(client, db_session, monkeypatch) -> None:
    from app.services.research_jobs import process_research_question_job
    from finsight.infrastructure.database.models import JobRecord
    from finsight.documents.models import ResearchWorkflowCheckpoint
    from app.models.entities import User

    email = "phase3.research.worker@example.com"
    token = _register_user(client, email)
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    headers = {"Authorization": f"Bearer {token}"}
    document_text = (
        "Annual filing revenue increased by 12%. Subscription demand strengthened and operating margins improved. "
        "Management attributed growth to enterprise customer adoption and recurring contracts."
    )
    uploaded = client.post("/api/v1/documents/upload", headers=headers,
        data={"title": "Worker test filing"},
        files={"file": ("worker-test.txt", document_text.encode(), "text/plain")})
    assert uploaded.status_code == 201, uploaded.text

    job = JobRecord(task_name="research.ask", status="QUEUED", payload={
        "query": "What explains the company's revenue growth?", "top_k": 5,
        "lexical_weight": 0.45, "diversity_weight": 0.15,
    }, created_by=user.id)
    db_session.add(job)
    db_session.commit()

    result = process_research_question_job(db_session, job)
    assert result["status"] == "succeeded"
    assert result["report_id"] == job.id
    assert job.status == "SUCCEEDED"
    report = db_session.get(ResearchReport, job.id)
    assert report is not None and report.status == "AWAITING_REVIEW"
    checkpoints = db_session.scalars(select(ResearchWorkflowCheckpoint).where(
        ResearchWorkflowCheckpoint.workflow_id == job.id
    ).order_by(ResearchWorkflowCheckpoint.sequence)).all()
    assert [item.node for item in checkpoints] == [
        "validate_query", "retrieve_evidence", "synthesize", "verify_citations", "human_review"]

    # Simulate a worker crash after the report commit but before the job success commit.
    job.status = "RUNNING"
    db_session.commit()
    replay = process_research_question_job(db_session, job)
    assert replay["status"] == "succeeded"
    assert replay["report_id"] == job.id
    assert replay["recovered_after_worker_redelivery"] is True
    assert db_session.scalar(select(ResearchReport).where(ResearchReport.id == job.id)) is not None


def test_failed_research_report_resumes_from_exact_evidence_checkpoint(client, db_session) -> None:
    from finsight.documents.models import ResearchWorkflowCheckpoint
    from finsight.infrastructure.database.mixins import new_id

    email = "phase3.resume@example.com"
    token = _register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    source = b"The annual report states quarterly revenue rose 12% during the first quarter. Operating margins also expanded."
    uploaded = client.post("/api/v1/documents/upload", headers=headers,
        files={"file": ("quarterly-filing.txt", source, "text/plain")})
    assert uploaded.status_code == 201, uploaded.text
    document = db_session.get(ResearchDocument, uploaded.json()["id"])
    assert document is not None
    chunk = db_session.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
    assert chunk is not None
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None

    report_id = new_id()
    query = "What changed in quarterly revenue?"
    report = ResearchReport(id=report_id, query=query, answer="", status="FAILED",
        citations=[], workflow_trace=[], retrieval_config={"synthesis_provider": "extractive"},
        evidence_verified=False, claim_checks={}, created_by=user.id,
        review_comment="Simulated worker interruption")
    checkpoint = ResearchWorkflowCheckpoint(workflow_id=report_id, sequence=2,
        node="retrieve_evidence", status="running", state_snapshot={
            "query": query, "evidence_ids": [chunk.id], "answer": "", "citations": [],
            "workflow_trace": [
                {"node": "validate_query", "status": "completed"},
                {"node": "retrieve_evidence", "status": "completed", "evidence_count": 1},
            ],
        })
    db_session.add_all([report, checkpoint])
    db_session.commit()

    resumed = client.post(f"/api/v1/research/reports/{report_id}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    result = resumed.json()
    assert result["status"] == "AWAITING_REVIEW"
    assert result["evidence_verified"] is True
    assert result["citations"][0]["chunk_id"] == chunk.id
    assert result["claim_checks"]["passed"] is True
    nodes = client.get(f"/api/v1/research/reports/{report_id}/checkpoints", headers=headers).json()
    assert [item["node"] for item in nodes][-3:] == ["synthesize", "verify_citations", "human_review"]


def test_research_resume_rejects_checkpoint_with_missing_evidence(client, db_session) -> None:
    from finsight.documents.models import ResearchWorkflowCheckpoint
    from finsight.infrastructure.database.mixins import new_id

    email = "phase3.resume-missing@example.com"
    token = _register_user(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    user = db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    report_id = new_id()
    query = "What does the filing say about revenue?"
    db_session.add(ResearchReport(id=report_id, query=query, answer="", status="FAILED",
        citations=[], workflow_trace=[], retrieval_config={"synthesis_provider": "extractive"},
        evidence_verified=False, claim_checks={}, created_by=user.id))
    db_session.add(ResearchWorkflowCheckpoint(workflow_id=report_id, sequence=1,
        node="retrieve_evidence", status="running", state_snapshot={
            "query": query, "evidence_ids": ["missing-chunk-id"], "citations": [],
            "workflow_trace": [],
        }))
    db_session.commit()
    response = client.post(f"/api/v1/research/reports/{report_id}/resume", headers=headers)
    assert response.status_code == 409
    assert "chunks are no longer available" in response.json()["detail"]


def test_research_workflow_can_reconcile_a_committed_human_review_checkpoint() -> None:
    from finsight.research.graphs.workflow import resume_evidence_report

    checkpoint = {
        "query": "What changed in company revenue?",
        "answer": "Revenue increased 12%. [E1]",
        "citations": [{"citation_id": "E1", "chunk_id": "chunk-1"}],
        "evidence_verified": True,
        "claim_checks": {"passed": True, "claim_count": 1, "supported_count": 1, "checks": []},
        "status": "AWAITING_REVIEW",
        "workflow_trace": [{"node": "human_review", "status": "awaiting_review"}],
    }
    result = resume_evidence_report(checkpoint["query"], [], checkpoint,
        "human_review", checkpoint_sequence=5)
    assert result["status"] == "AWAITING_REVIEW"
    assert result["evidence_verified"] is True
    assert result["answer"] == checkpoint["answer"]
