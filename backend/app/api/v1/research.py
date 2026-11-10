"""Phase 2 research hypothesis, feature set and experiment specification API."""
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from finsight.core.security import require_roles
from finsight.experiments.registry import configuration_sha256
from finsight.features.models import FeatureSetVersion
from finsight.identity.models import User
from finsight.infrastructure.database.session import get_db
from finsight.market_data.models import DataSnapshot
from finsight.research.hypotheses.models import ResearchHypothesis
from finsight.research.hypotheses.service import create_hypothesis, decide_hypothesis, submit_for_review
from finsight.experiments.models import Experiment, ExperimentRun
from finsight.risk.models import ExperimentRiskReview
from app.schemas.research import (ExperimentCreate, ExperimentResponse, FeatureSetCreate,
    FeatureSetResponse, HypothesisCreate, HypothesisDecision, HypothesisResponse,
    ExperimentRunCreate, ExperimentRunResponse, ExperimentRiskReviewResponse, ExperimentComparisonItem)
from app.services.audit import record_audit
from app.services.experiments import enqueue_experiment_run

router = APIRouter(tags=["research and experiments"])


@router.post("/research/hypotheses", response_model=HypothesisResponse, status_code=status.HTTP_201_CREATED)
def create_research_hypothesis(payload: HypothesisCreate, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER"))):
    hypothesis = create_hypothesis(db, owner_user_id=user.id, payload=payload.model_dump(mode="json"))
    record_audit(db, actor=user, action="research.hypothesis_created", resource_type="research_hypothesis",
                 resource_id=hypothesis.id, request_id=getattr(request.state, "request_id", None),
                 details={"symbol": hypothesis.symbol, "evidence_count": len(hypothesis.evidence)})
    db.commit()
    db.refresh(hypothesis)
    return hypothesis


@router.get("/research/hypotheses", response_model=list[HypothesisResponse])
def list_research_hypotheses(db: Session = Depends(get_db), user: User = Depends(require_roles(
    "ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    return list(db.scalars(select(ResearchHypothesis).order_by(ResearchHypothesis.created_at.desc())).all())


@router.post("/research/hypotheses/{hypothesis_id}/submit-review", response_model=HypothesisResponse)
def submit_research_hypothesis_for_review(hypothesis_id: str, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RESEARCH_ANALYST", "QUANT_RESEARCHER"))):
    hypothesis = db.get(ResearchHypothesis, hypothesis_id)
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    if hypothesis.owner_user_id != user.id and "ADMIN" not in {role.key for role in user.roles}:
        raise HTTPException(status_code=403, detail="Only the owner or an administrator can submit this hypothesis")
    try:
        hypothesis = submit_for_review(db, hypothesis_id=hypothesis_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit(db, actor=user, action="research.hypothesis_submitted_for_review", resource_type="research_hypothesis",
        resource_id=hypothesis.id, request_id=getattr(request.state, "request_id", None),
        details={"version": hypothesis.version})
    db.commit()
    db.refresh(hypothesis)
    return hypothesis


@router.post("/research/hypotheses/{hypothesis_id}/decision", response_model=HypothesisResponse)
def decide_research_hypothesis(hypothesis_id: str, payload: HypothesisDecision, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "RISK_REVIEWER"))):
    try:
        hypothesis = decide_hypothesis(db, hypothesis_id=hypothesis_id, decision=payload.decision, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    record_audit(db, actor=user, action="research.hypothesis_decided", resource_type="research_hypothesis",
                 resource_id=hypothesis.id, request_id=getattr(request.state, "request_id", None),
                 details={"decision": payload.decision, "version": hypothesis.version})
    db.commit()
    db.refresh(hypothesis)
    return hypothesis


@router.post("/features/versions", response_model=FeatureSetResponse, status_code=status.HTTP_201_CREATED)
def create_feature_set(payload: FeatureSetCreate, request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    snapshot = db.scalar(select(DataSnapshot).where(DataSnapshot.id == payload.source_snapshot_id, DataSnapshot.status == "READY"))
    if snapshot is None:
        raise HTTPException(status_code=422, detail="A READY source snapshot is required")
    current = db.scalar(select(FeatureSetVersion).where(FeatureSetVersion.feature_key == payload.feature_key)
                        .order_by(FeatureSetVersion.version.desc()))
    version = 1 if current is None else current.version + 1
    digest = configuration_sha256(payload.definition)
    feature_set = FeatureSetVersion(feature_key=payload.feature_key, version=version,
        description=payload.description, definition=payload.definition, source_snapshot_id=snapshot.id,
        definition_sha256=digest, created_by=user.id)
    db.add(feature_set)
    db.flush()
    record_audit(db, actor=user, action="features.version_created", resource_type="feature_set_version",
        resource_id=feature_set.id, request_id=getattr(request.state, "request_id", None),
        details={"feature_key": feature_set.feature_key, "version": version, "definition_sha256": digest})
    db.commit()
    db.refresh(feature_set)
    return feature_set


@router.get("/features/versions", response_model=list[FeatureSetResponse])
def list_feature_sets(db: Session = Depends(get_db), user: User = Depends(require_roles(
    "ADMIN", "QUANT_RESEARCHER", "RESEARCH_ANALYST", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    return list(db.scalars(select(FeatureSetVersion).order_by(FeatureSetVersion.feature_key, FeatureSetVersion.version.desc())).all())


@router.post("/experiments", response_model=ExperimentResponse, status_code=status.HTTP_201_CREATED)
def create_experiment(payload: ExperimentCreate, request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    hypothesis = db.scalar(select(ResearchHypothesis).where(ResearchHypothesis.id == payload.hypothesis_id))
    if hypothesis is None:
        raise HTTPException(status_code=404, detail="Hypothesis not found")
    if hypothesis.status != "APPROVED":
        raise HTTPException(status_code=409, detail="Experiments can only be created from an approved hypothesis")
    snapshot = db.scalar(select(DataSnapshot).where(DataSnapshot.id == payload.dataset_snapshot_id, DataSnapshot.status == "READY"))
    if snapshot is None:
        raise HTTPException(status_code=422, detail="A READY dataset snapshot is required")
    feature_set = db.scalar(select(FeatureSetVersion).where(FeatureSetVersion.id == payload.feature_set_version_id))
    if feature_set is None:
        raise HTTPException(status_code=404, detail="Feature-set version not found")
    benchmark_snapshot = None
    if payload.benchmark_snapshot_id:
        benchmark_snapshot = db.scalar(select(DataSnapshot).where(
            DataSnapshot.id == payload.benchmark_snapshot_id, DataSnapshot.status == "READY"))
        if benchmark_snapshot is None:
            raise HTTPException(status_code=422, detail="A READY benchmark snapshot is required")
        if benchmark_snapshot.instrument_symbol.upper() != payload.configuration.benchmark_symbol.upper():
            raise HTTPException(status_code=422, detail="Benchmark snapshot symbol must match benchmark_symbol")
        if benchmark_snapshot.start_date > payload.configuration.test_start or benchmark_snapshot.end_date < payload.configuration.test_end:
            raise HTTPException(status_code=422, detail="Benchmark snapshot must cover the full test window")
    if feature_set.source_snapshot_id != snapshot.id:
        raise HTTPException(status_code=422, detail="Feature set must be derived from the selected dataset snapshot")
    if payload.configuration.train_start < snapshot.start_date or payload.configuration.test_end > snapshot.end_date:
        raise HTTPException(status_code=422, detail="Experiment windows must be fully covered by the dataset snapshot")
    if hypothesis.symbol != snapshot.instrument_symbol:
        raise HTTPException(status_code=422, detail="Hypothesis and dataset instrument symbols must match")
    configuration = payload.configuration.model_dump(mode="json")
    digest = configuration_sha256(configuration)
    experiment = Experiment(name=payload.name, hypothesis_id=hypothesis.id,
        instrument_symbol=hypothesis.symbol, dataset_snapshot_id=snapshot.id,
        feature_set_version_id=feature_set.id,
        benchmark_snapshot_id=benchmark_snapshot.id if benchmark_snapshot else None,
        configuration=configuration, configuration_sha256=digest, status="DRAFT", created_by=user.id)
    db.add(experiment)
    db.flush()
    record_audit(db, actor=user, action="experiments.specification_created", resource_type="experiment",
        resource_id=experiment.id, request_id=getattr(request.state, "request_id", None),
        details={"configuration_sha256": digest, "dataset_snapshot_id": snapshot.id,
                 "benchmark_snapshot_id": benchmark_snapshot.id if benchmark_snapshot else None})
    db.commit()
    db.refresh(experiment)
    return experiment


@router.get("/experiments", response_model=list[ExperimentResponse])
def list_experiments(db: Session = Depends(get_db), user: User = Depends(require_roles(
    "ADMIN", "QUANT_RESEARCHER", "RESEARCH_ANALYST", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    return list(db.scalars(select(Experiment).order_by(Experiment.created_at.desc())).all())


@router.post("/experiments/{experiment_id}/runs", response_model=ExperimentRunResponse,
             status_code=status.HTTP_202_ACCEPTED)
def submit_experiment_run(experiment_id: str, payload: ExperimentRunCreate, request: Request,
    db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128 or any(ord(ch) < 33 or ord(ch) > 126 for ch in idempotency_key):
            raise HTTPException(status_code=400, detail="Idempotency-Key must be 1-128 printable ASCII characters")
        existing = db.scalar(select(ExperimentRun).where(
            ExperimentRun.experiment_id == experiment_id,
            ExperimentRun.idempotency_key == idempotency_key,
        ))
        if existing is not None and existing.status != "QUEUE_FAILED":
            return existing
        if existing is not None:
            run = existing
            run.status = "QUEUED"
            run.error_message = None
            run.completed_at = None
        else:
            run = None
    else:
        run = None

    if run is None:
        last_number = db.scalar(select(func.max(ExperimentRun.run_number)).where(
            ExperimentRun.experiment_id == experiment_id
        )) or 0
        run = ExperimentRun(
            experiment_id=experiment_id,
            run_number=int(last_number) + 1,
            status="QUEUED",
            random_seed=payload.random_seed if payload.random_seed is not None else int(experiment.configuration.get("random_seed", 42)),
            idempotency_key=idempotency_key,
        )
        db.add(run)
    try:
        db.flush()
    except IntegrityError as exc:
        # A concurrent request may have won the same idempotency key or run number.
        db.rollback()
        if idempotency_key:
            winner = db.scalar(select(ExperimentRun).where(
                ExperimentRun.experiment_id == experiment_id,
                ExperimentRun.idempotency_key == idempotency_key,
            ))
            if winner is not None:
                return winner
        raise HTTPException(
            status_code=409,
            detail="A concurrent run submission conflicted; retry with the same Idempotency-Key",
        ) from exc
    record_audit(db, actor=user, action="experiments.run_queued", resource_type="experiment_run",
        resource_id=run.id, request_id=getattr(request.state, "request_id", None),
        details={"experiment_id": experiment_id, "run_number": run.run_number,
                  "idempotency_key_present": idempotency_key is not None})
    db.commit()
    db.refresh(run)
    try:
        enqueue_experiment_run(run.id)
    except Exception as exc:
        run.status = "QUEUE_FAILED"
        run.error_message = "Background queue is unavailable; retry after checking Redis and worker status"
        run.completed_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(status_code=503, detail=run.error_message) from exc
    return run


@router.get("/experiments/{experiment_id}/runs", response_model=list[ExperimentRunResponse])
def list_experiment_runs(experiment_id: str, db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER", "RESEARCH_ANALYST", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    if db.get(Experiment, experiment_id) is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return list(db.scalars(select(ExperimentRun).where(ExperimentRun.experiment_id == experiment_id)
                           .order_by(ExperimentRun.run_number.desc())).all())


@router.get("/experiments/{experiment_id}/runs/comparison", response_model=list[ExperimentComparisonItem])
def compare_experiment_runs(experiment_id: str, db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER", "RESEARCH_ANALYST", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    """Compare successful runs of one immutable experiment specification."""
    if db.get(Experiment, experiment_id) is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    runs = list(db.scalars(select(ExperimentRun).where(
        ExperimentRun.experiment_id == experiment_id
    ).order_by(ExperimentRun.run_number.asc())).all())
    output = []
    for run in runs:
        risk = db.scalar(select(ExperimentRiskReview).where(ExperimentRiskReview.run_id == run.id))
        metrics = run.metrics or {}
        output.append({
            "run_id": run.id, "run_number": run.run_number, "status": run.status,
            "total_return": metrics.get("total_return"),
            "annualized_return": metrics.get("annualized_return"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "annualized_volatility": metrics.get("annualized_volatility"),
            "benchmark_total_return": metrics.get("benchmark_total_return"),
            "information_ratio": metrics.get("information_ratio"),
            "risk_decision": risk.decision if risk else None,
        })
    return output


@router.get("/experiments/{experiment_id}/runs/{run_id}/risk-review", response_model=ExperimentRiskReviewResponse)
def get_experiment_run_risk_review(experiment_id: str, run_id: str, db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER", "RESEARCH_ANALYST", "RISK_REVIEWER", "PORTFOLIO_ANALYST", "READ_ONLY_VIEWER"))):
    run = db.scalar(select(ExperimentRun).where(
        ExperimentRun.id == run_id, ExperimentRun.experiment_id == experiment_id))
    if run is None:
        raise HTTPException(status_code=404, detail="Experiment run not found")
    review = db.scalar(select(ExperimentRiskReview).where(ExperimentRiskReview.run_id == run_id))
    if review is None:
        raise HTTPException(status_code=404, detail="Risk review is not available until the run completes")
    return review
