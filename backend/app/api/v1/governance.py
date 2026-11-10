"""Model registry, deterministic model risk review and independent human approvals."""
from pathlib import Path
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.core.security import require_roles
from finsight.documents.models import ModelEvaluation
from finsight.governance.models import ModelVersion, ModelRiskReview, ModelGovernanceDecision, RLPolicyEvaluation
from finsight.identity.models import User
from finsight.infrastructure.database.session import get_db
from finsight.risk.governance import evaluate_model_candidate
from app.schemas.phase4 import ModelVersionCreate, ModelVersionResponse, GovernanceDecisionCreate
from app.services.audit import record_audit

router = APIRouter(prefix="/governance", tags=["model governance"])


def _hash_artifact(path: str | None) -> str | None:
    if not path:
        return None
    base = Path(get_settings().data_storage_path).resolve()
    candidate = (base / path).resolve()
    if base not in candidate.parents and candidate != base:
        raise HTTPException(status_code=422, detail="Model artifact path is outside the configured artifact directory")
    if not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.get("/models", response_model=list[ModelVersionResponse])
def list_model_versions(db: Session = Depends(get_db), user: User = Depends(require_roles(
        "ADMIN", "RISK_REVIEWER", "QUANT_RESEARCHER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    return db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(500)).all()


@router.post("/models", response_model=ModelVersionResponse, status_code=status.HTTP_201_CREATED)
def register_model_version(payload: ModelVersionCreate, request: Request, db: Session = Depends(get_db),
                           user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    if payload.source_evaluation_id:
        source = db.get(ModelEvaluation, payload.source_evaluation_id)
        if source is None or source.status != "SUCCEEDED":
            raise HTTPException(status_code=422, detail="A successful supervised evaluation is required")
        metrics = dict(source.metrics or {})
        config = dict(source.configuration or {})
        out_of_sample = config.get("split_method") == "chronological_no_shuffle" and int(metrics.get("test_rows", 0)) > 0
        if not out_of_sample:
            raise HTTPException(status_code=422, detail="Model registration requires a chronological out-of-sample evaluation")
        artifact_uri = source.artifact_path
        artifact_hash = _hash_artifact(artifact_uri)
        family = source.model_family
        snapshot_id, feature_id = source.dataset_snapshot_id, source.feature_set_version_id
        source_eval_id, source_rl_id = source.id, None
    else:
        source = db.get(RLPolicyEvaluation, payload.source_rl_evaluation_id)
        if source is None or source.status != "SUCCEEDED" or not source.out_of_sample:
            raise HTTPException(status_code=422, detail="A successful out-of-sample PPO/SAC evaluation is required")
        metrics = dict(source.metrics or {})
        config = dict(source.configuration or {})
        artifact_uri = source.artifact_uri
        computed_hash = _hash_artifact(artifact_uri)
        artifact_hash = computed_hash if computed_hash and (not source.artifact_sha256 or source.artifact_sha256 == computed_hash) else None
        family = f"rl_{source.algorithm.lower()}"
        snapshot_id, feature_id = source.dataset_snapshot_id, source.feature_set_version_id
        source_eval_id, source_rl_id = None, source.id
    if artifact_uri and artifact_hash is None:
        # Keep a missing artifact visible as a blocking risk finding, not a false claim of integrity.
        metrics["artifact_integrity"] = "MISSING"
    else:
        metrics["artifact_integrity"] = "VERIFIED" if artifact_hash else "NOT_PROVIDED"
    risk = evaluate_model_candidate(metrics, out_of_sample=out_of_sample)
    version = ModelVersion(model_key=payload.model_key, version=payload.version, model_family=family,
        source_evaluation_id=source_eval_id, source_rl_evaluation_id=source_rl_id,
        artifact_uri=artifact_uri, artifact_sha256=artifact_hash, dataset_snapshot_id=snapshot_id,
        feature_set_version_id=feature_id, metrics=metrics, configuration=config,
        risk_decision=risk["decision"], state="CANDIDATE", created_by=user.id)
    db.add(version)
    try:
        db.flush()
        db.add(ModelRiskReview(model_version_id=version.id, decision=risk["decision"],
            policy_version=risk["policy_version"], limits=risk["limits"],
            observed_metrics=risk["observed_metrics"], breaches=risk["breaches"],
            warnings=risk["warnings"], deterministic=True))
        record_audit(db, actor=user, action="governance.model_registered", resource_type="model_version",
            resource_id=version.id, request_id=getattr(request.state, "request_id", None),
            details={"model_key": payload.model_key, "version": payload.version, "risk_decision": risk["decision"]})
        db.commit()
        db.refresh(version)
        return version
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This model key and version already exist") from exc


@router.get("/models/{model_version_id}/risk-review")
def get_model_risk_review(model_version_id: str, db: Session = Depends(get_db),
                          user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER", "QUANT_RESEARCHER", "READ_ONLY_VIEWER"))):
    version = db.get(ModelVersion, model_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    review = db.scalar(select(ModelRiskReview).where(ModelRiskReview.model_version_id == version.id))
    if review is None:
        raise HTTPException(status_code=404, detail="Risk review not found")
    return {"decision": review.decision, "policy_version": review.policy_version,
        "limits": review.limits, "observed_metrics": review.observed_metrics,
        "breaches": review.breaches, "warnings": review.warnings,
        "deterministic": review.deterministic, "override_allowed": False}


@router.get("/models/{model_version_id}/decisions")
def list_governance_decisions(model_version_id: str, db: Session = Depends(get_db),
                              user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER", "QUANT_RESEARCHER", "READ_ONLY_VIEWER"))):
    if db.get(ModelVersion, model_version_id) is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    decisions = db.scalars(select(ModelGovernanceDecision).where(
        ModelGovernanceDecision.model_version_id == model_version_id).order_by(ModelGovernanceDecision.created_at.asc())).all()
    return [{"id": item.id, "decision": item.decision, "reviewer_user_id": item.reviewer_user_id,
             "comment": item.comment, "created_at": item.created_at} for item in decisions]


@router.post("/models/{model_version_id}/decision", response_model=ModelVersionResponse)
def decide_model_version(model_version_id: str, payload: GovernanceDecisionCreate, request: Request,
                         db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER"))):
    version = db.get(ModelVersion, model_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    if version.created_by == user.id:
        raise HTTPException(status_code=403, detail="Model authors cannot approve their own model")
    if version.state != "CANDIDATE":
        raise HTTPException(status_code=409, detail="Only candidate models can receive a governance decision")
    if payload.decision == "APPROVE" and version.risk_decision != "PASS":
        raise HTTPException(status_code=409, detail="Deterministic model risk review must PASS before approval")
    version.state = "APPROVED" if payload.decision == "APPROVE" else "REJECTED"
    db.add(ModelGovernanceDecision(model_version_id=version.id, reviewer_user_id=user.id,
        decision=payload.decision, comment=payload.comment.strip()))
    record_audit(db, actor=user, action=f"governance.model_{payload.decision.lower()}",
        resource_type="model_version", resource_id=version.id,
        request_id=getattr(request.state, "request_id", None), details={"comment": payload.comment.strip()})
    db.commit()
    db.refresh(version)
    return version


@router.post("/models/{model_version_id}/promote", response_model=ModelVersionResponse)
def promote_model_version(model_version_id: str, request: Request, db: Session = Depends(get_db),
                          user: User = Depends(require_roles("ADMIN"))):
    version = db.get(ModelVersion, model_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    if version.state != "APPROVED" or version.risk_decision != "PASS":
        raise HTTPException(status_code=409, detail="Promotion requires independent approval and deterministic risk PASS")
    prior = db.scalars(select(ModelVersion).where(ModelVersion.model_key == version.model_key,
        ModelVersion.state == "PROMOTED").with_for_update()).all()
    for old in prior:
        old.state = "SUPERSEDED"
    version.state = "PROMOTED"
    record_audit(db, actor=user, action="governance.model_promoted", resource_type="model_version",
        resource_id=version.id, request_id=getattr(request.state, "request_id", None),
        details={"model_key": version.model_key, "version": version.version})
    db.commit()
    db.refresh(version)
    return version


@router.post("/models/{model_version_id}/rollback", response_model=ModelVersionResponse)
def rollback_model_version(model_version_id: str, request: Request, db: Session = Depends(get_db),
                           user: User = Depends(require_roles("ADMIN"))):
    version = db.get(ModelVersion, model_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    decision = db.scalar(select(ModelGovernanceDecision).where(
        ModelGovernanceDecision.model_version_id == version.id).order_by(ModelGovernanceDecision.created_at.desc()))
    if version.state != "SUPERSEDED" or version.risk_decision != "PASS" or decision is None or decision.decision != "APPROVE":
        raise HTTPException(status_code=409, detail="Rollback target must be a previously approved, risk-passing version")
    current = db.scalars(select(ModelVersion).where(ModelVersion.model_key == version.model_key,
        ModelVersion.state == "PROMOTED").with_for_update()).all()
    for item in current:
        item.state = "ROLLED_BACK"
    version.state = "PROMOTED"
    record_audit(db, actor=user, action="governance.model_rollback", resource_type="model_version",
        resource_id=version.id, request_id=getattr(request.state, "request_id", None),
        details={"model_key": version.model_key, "version": version.version})
    db.commit()
    db.refresh(version)
    return version
