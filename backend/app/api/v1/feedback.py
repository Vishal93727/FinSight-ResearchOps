"""Prediction-to-realised outcome feedback, strategy monitoring and drift workflows."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from finsight.core.security import require_roles
from finsight.documents.models import ModelEvaluation
from finsight.experiments.models import Experiment, ExperimentRun
from finsight.execution.models import PaperAccount
from finsight.feedback.models import PredictionOutcome, StrategyPerformanceSnapshot, DriftAssessment, ResearchSuggestion
from finsight.feedback.monitoring import summarize_outcomes, summarize_strategy_returns
from finsight.feedback.drift import assess_feature_drift
from finsight.governance.models import ModelVersion
from finsight.identity.models import User
from finsight.infrastructure.database.session import get_db
from finsight.market_data.models import DataSnapshot
from app.schemas.phase5 import (OutcomeCreate, OutcomeResponse, StrategyPerformanceCreate,
    StrategyRunEvaluationCreate, DriftCheckCreate, SuggestionDecision, SuggestionResponse)
from finsight.core.config import get_settings
from app.services.audit import record_audit

router = APIRouter(prefix="/feedback", tags=["outcome feedback and monitoring"])
_READER_ROLES = ("ADMIN", "RISK_REVIEWER", "QUANT_RESEARCHER", "PORTFOLIO_ANALYST", "RESEARCH_ANALYST", "READ_ONLY_VIEWER")
_WRITER_ROLES = ("ADMIN", "QUANT_RESEARCHER", "PORTFOLIO_ANALYST")


def _scoped(statement, model, user: User):
    roles = {role.key for role in user.roles}
    if not roles.intersection({"ADMIN", "RISK_REVIEWER"}):
        statement = statement.where(model.created_by == user.id)
    return statement


def _check_fk(db: Session, model, identifier: str | None, label: str) -> None:
    if identifier and db.get(model, identifier) is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")


def _validate_outcome_lineage(db: Session, payload: OutcomeCreate, user: User) -> None:
    """Enforce owner boundaries and ensure linked model/run lineage is coherent."""
    is_admin = any(role.key == "ADMIN" for role in user.roles)
    model_version = None
    if payload.model_version_id:
        model_version = db.get(ModelVersion, payload.model_version_id)
        if model_version is None:
            raise HTTPException(status_code=404, detail="Model version not found")
        if model_version.created_by != user.id and not is_admin:
            raise HTTPException(status_code=404, detail="Model version not found")

    if payload.experiment_run_id:
        run = db.get(ExperimentRun, payload.experiment_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Experiment run not found")
        experiment = db.get(Experiment, run.experiment_id)
        if experiment is None or (experiment.created_by != user.id and not is_admin):
            raise HTTPException(status_code=404, detail="Experiment run not found")
        if run.status != "SUCCEEDED":
            raise HTTPException(status_code=409, detail="Only a succeeded experiment run can be linked to a realised outcome")
        if model_version is not None:
            if (model_version.dataset_snapshot_id != experiment.dataset_snapshot_id
                    or model_version.feature_set_version_id != experiment.feature_set_version_id):
                raise HTTPException(status_code=409,
                    detail="Model version data/feature lineage does not match the linked experiment run")

    if payload.paper_account_id:
        account = db.get(PaperAccount, payload.paper_account_id)
        if account is None or (account.created_by != user.id and not is_admin):
            raise HTTPException(status_code=404, detail="Paper account not found")


@router.post("/outcomes", response_model=OutcomeResponse, status_code=status.HTTP_201_CREATED)
def create_outcome(payload: OutcomeCreate, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(*_WRITER_ROLES))):
    if payload.idempotency_key:
        previous = db.scalar(select(PredictionOutcome).where(
            PredictionOutcome.created_by == user.id,
            PredictionOutcome.idempotency_key == payload.idempotency_key,
        ))
        if previous:
            comparable = payload.model_dump(exclude={"idempotency_key"})
            stored = {key: getattr(previous, key) for key in comparable}
            if stored != comparable:
                raise HTTPException(status_code=409, detail="Idempotency key was used for a different outcome")
            return previous
    _validate_outcome_lineage(db, payload, user)
    row = PredictionOutcome(**payload.model_dump(), created_by=user.id)
    db.add(row)
    try:
        db.flush()
        record_audit(db, actor=user, action="feedback.outcome_recorded", resource_type="prediction_outcome",
            resource_id=row.id, request_id=getattr(request.state, "request_id", None),
            details={"symbol": row.instrument_symbol, "model_version_id": row.model_version_id,
                     "experiment_run_id": row.experiment_run_id, "paper_account_id": row.paper_account_id})
        db.commit(); db.refresh(row)
        return row
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Outcome conflicts with an existing idempotency key") from exc


@router.get("/outcomes", response_model=list[OutcomeResponse])
def list_outcomes(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                  user: User = Depends(require_roles(*_READER_ROLES))):
    stmt = _scoped(select(PredictionOutcome), PredictionOutcome, user)
    return list(db.scalars(stmt.order_by(PredictionOutcome.realised_date.desc()).limit(limit)).all())


@router.get("/summary")
def feedback_summary(db: Session = Depends(get_db), user: User = Depends(require_roles(*_READER_ROLES))):
    outcomes = list(db.scalars(_scoped(select(PredictionOutcome), PredictionOutcome, user)
        .order_by(PredictionOutcome.realised_date.desc()).limit(5000)).all())
    strategies = list(db.scalars(_scoped(select(StrategyPerformanceSnapshot), StrategyPerformanceSnapshot, user)
        .order_by(StrategyPerformanceSnapshot.created_at.desc()).limit(50)).all())
    assessments = list(db.scalars(_scoped(select(DriftAssessment), DriftAssessment, user)
        .order_by(DriftAssessment.created_at.desc()).limit(100)).all())
    suggestions = list(db.scalars(_scoped(select(ResearchSuggestion), ResearchSuggestion, user)
        .order_by(ResearchSuggestion.created_at.desc()).limit(100)).all())
    outcome_metrics = summarize_outcomes(
        [row.predicted_return for row in outcomes], [row.realised_return for row in outcomes]
    ) if outcomes else {"sample_count": 0, "mae": None, "rmse": None, "mean_bias": None,
                        "directional_accuracy": None, "directional_sample_count": 0}
    return {
        "outcome_metrics": outcome_metrics,
        "outcome_count": len(outcomes),
        "latest_outcomes": [{"id": row.id, "symbol": row.instrument_symbol,
            "forecast_date": row.forecast_date.isoformat(), "realised_date": row.realised_date.isoformat(),
            "predicted": row.predicted_return, "realised": row.realised_return,
            "error": row.predicted_return - row.realised_return, "benchmark": row.benchmark_return,
            "model_version_id": row.model_version_id, "experiment_run_id": row.experiment_run_id}
            for row in outcomes[:12]],
        "strategy_snapshots": [{"id": row.id, "strategy_key": row.strategy_key,
            "period_start": row.period_start.isoformat(), "period_end": row.period_end.isoformat(),
            "metrics": row.metrics} for row in strategies[:12]],
        "drift": {"total": len(assessments), "open": sum(row.overall_status == "DRIFT" for row in assessments),
            "latest": [{"id": row.id, "status": row.overall_status, "summary": row.summary,
                        "created_at": row.created_at.isoformat()} for row in assessments[:10]]},
        "suggestions": [{"id": row.id, "title": row.title, "rationale": row.rationale,
            "suggested_action": row.suggested_action, "source_type": row.source_type,
            "status": row.status, "created_at": row.created_at.isoformat()} for row in suggestions[:10]],
        "proposed_suggestions": sum(row.status == "PROPOSED" for row in suggestions),
    }


@router.post("/strategies/evaluate", status_code=status.HTTP_201_CREATED)
def evaluate_strategy(payload: StrategyPerformanceCreate, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(require_roles(*_WRITER_ROLES))):
    try:
        metrics = summarize_strategy_returns(payload.returns, payload.benchmark_returns)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = StrategyPerformanceSnapshot(strategy_key=payload.strategy_key,
        period_start=payload.period_start, period_end=payload.period_end, metrics=metrics,
        source_reference=payload.source_reference, created_by=user.id)
    db.add(row); db.flush()
    record_audit(db, actor=user, action="feedback.strategy_performance_evaluated",
        resource_type="strategy_performance_snapshot", resource_id=row.id,
        request_id=getattr(request.state, "request_id", None), details={"strategy_key": row.strategy_key})
    db.commit(); db.refresh(row)
    return {"id": row.id, "strategy_key": row.strategy_key, "period_start": row.period_start,
        "period_end": row.period_end, "metrics": row.metrics, "created_at": row.created_at}


@router.post("/strategies/evaluate-run", status_code=status.HTTP_201_CREATED)
def evaluate_completed_run(payload: StrategyRunEvaluationCreate, request: Request,
                           db: Session = Depends(get_db),
                           user: User = Depends(require_roles(*_WRITER_ROLES))):
    """Derive monitoring metrics from a succeeded, hash-verified Phase 2 equity curve."""
    run = db.get(ExperimentRun, payload.experiment_run_id)
    if run is None or run.status != "SUCCEEDED":
        raise HTTPException(status_code=404, detail="Succeeded experiment run not found")
    experiment = db.get(Experiment, run.experiment_id)
    if experiment is None:
        raise HTTPException(status_code=409, detail="Experiment lineage is unavailable")
    is_admin = any(role.key == "ADMIN" for role in user.roles)
    if experiment.created_by != user.id and not is_admin:
        raise HTTPException(status_code=404, detail="Succeeded experiment run not found")

    artifacts = run.artifacts or {}
    raw_path = artifacts.get("equity_curve_path")
    expected_hash = artifacts.get("equity_curve_sha256")
    if not raw_path or not expected_hash:
        raise HTTPException(status_code=409,
            detail="Run has no integrity-pinned equity curve; rerun it with the current worker version")
    storage_root = Path(get_settings().data_storage_path).resolve()
    equity_path = Path(raw_path).resolve()
    if storage_root != equity_path and storage_root not in equity_path.parents:
        raise HTTPException(status_code=404, detail="Experiment artifact not found")
    if not equity_path.is_file():
        raise HTTPException(status_code=404, detail="Experiment equity-curve artifact not found")
    digest = hashlib.sha256()
    with equity_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_hash:
        raise HTTPException(status_code=409, detail="Equity-curve artifact integrity check failed")

    source_reference = f"experiment_run:{run.id};equity_sha256:{expected_hash}"
    existing = db.scalar(select(StrategyPerformanceSnapshot).where(
        StrategyPerformanceSnapshot.created_by == user.id,
        StrategyPerformanceSnapshot.source_reference == source_reference,
    ))
    if existing is not None:
        return {"id": existing.id, "strategy_key": existing.strategy_key,
            "period_start": existing.period_start, "period_end": existing.period_end,
            "metrics": existing.metrics, "source_reference": existing.source_reference,
            "created_at": existing.created_at}

    try:
        import pandas as pd
        frame = pd.read_parquet(equity_path)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Parquet support is unavailable in this API runtime") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Equity-curve artifact could not be read") from exc
    required_columns = {"date", "strategy_return"}
    if not required_columns.issubset(frame.columns) or not 2 <= len(frame) <= 100_000:
        raise HTTPException(status_code=422, detail="Equity curve must contain 2 to 100,000 dated return rows")
    try:
        dates = pd.to_datetime(frame["date"], errors="raise", utc=True)
        returns = pd.to_numeric(frame["strategy_return"], errors="raise").astype(float).tolist()
        benchmark = (pd.to_numeric(frame["benchmark_return"], errors="raise").astype(float).tolist()
                     if "benchmark_return" in frame.columns else None)
        metrics = summarize_strategy_returns(returns, benchmark)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Equity curve contains invalid date/return values") from exc
    if dates.isna().any() or dates.duplicated().any():
        raise HTTPException(status_code=422, detail="Equity-curve dates must be valid and unique")
    baseline = str((experiment.configuration or {}).get("baseline", "baseline"))
    strategy_key = f"{experiment.instrument_symbol.upper()}:{baseline}"[:120]
    row = StrategyPerformanceSnapshot(
        strategy_key=strategy_key, period_start=dates.min().to_pydatetime(),
        period_end=dates.max().to_pydatetime(), metrics=metrics,
        source_reference=source_reference,
        created_by=user.id,
    )
    db.add(row); db.flush()
    record_audit(db, actor=user, action="feedback.strategy_run_evaluated",
        resource_type="strategy_performance_snapshot", resource_id=row.id,
        request_id=getattr(request.state, "request_id", None),
        details={"experiment_run_id": run.id, "strategy_key": strategy_key})
    db.commit(); db.refresh(row)
    return {"id": row.id, "strategy_key": row.strategy_key, "period_start": row.period_start,
        "period_end": row.period_end, "metrics": row.metrics, "source_reference": row.source_reference,
        "created_at": row.created_at}


@router.get("/strategies")
def list_strategies(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*_READER_ROLES))):
    stmt = _scoped(select(StrategyPerformanceSnapshot), StrategyPerformanceSnapshot, user)
    rows = db.scalars(stmt.order_by(StrategyPerformanceSnapshot.created_at.desc()).limit(limit)).all()
    return [{"id": row.id, "strategy_key": row.strategy_key, "period_start": row.period_start,
        "period_end": row.period_end, "metrics": row.metrics, "source_reference": row.source_reference,
        "created_at": row.created_at} for row in rows]


@router.post("/drift/check", status_code=status.HTTP_201_CREATED)
def check_drift(payload: DriftCheckCreate, request: Request, db: Session = Depends(get_db),
                user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER", "RISK_REVIEWER"))):
    is_admin = any(role.key == "ADMIN" for role in user.roles)
    model_version = None
    if payload.model_version_id:
        model_version = db.get(ModelVersion, payload.model_version_id)
        if model_version is None or (model_version.created_by != user.id and not is_admin):
            raise HTTPException(status_code=404, detail="Model version not found")
    reference_snapshot = None
    current_snapshot = None
    if payload.reference_snapshot_id:
        reference_snapshot = db.get(DataSnapshot, payload.reference_snapshot_id)
        if reference_snapshot is None or (reference_snapshot.created_by != user.id and not is_admin):
            raise HTTPException(status_code=404, detail="Reference snapshot not found")
    if payload.current_snapshot_id:
        current_snapshot = db.get(DataSnapshot, payload.current_snapshot_id)
        if current_snapshot is None or (current_snapshot.created_by != user.id and not is_admin):
            raise HTTPException(status_code=404, detail="Current snapshot not found")
    for label, snapshot in (("Reference", reference_snapshot), ("Current", current_snapshot)):
        if snapshot is not None and snapshot.status != "READY":
            raise HTTPException(status_code=409, detail=f"{label} snapshot is not READY")
    model_training_snapshot = db.get(DataSnapshot, model_version.dataset_snapshot_id) if model_version else None
    if model_version is not None and reference_snapshot is not None:
        if model_version.dataset_snapshot_id != reference_snapshot.id:
            raise HTTPException(status_code=409,
                detail="Reference snapshot must match the model version training snapshot")
    comparison_reference = reference_snapshot or model_training_snapshot
    if comparison_reference is not None and current_snapshot is not None:
        if comparison_reference.instrument_symbol.upper() != current_snapshot.instrument_symbol.upper():
            raise HTTPException(status_code=409,
                detail="Reference and current snapshots must belong to the same instrument")
    try:
        result = assess_feature_drift(payload.reference_features, payload.current_features)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = DriftAssessment(model_version_id=payload.model_version_id,
        reference_snapshot_id=payload.reference_snapshot_id, current_snapshot_id=payload.current_snapshot_id,
        overall_status=result["overall_status"], feature_results=result["features"],
        summary=result["summary"], created_by=user.id)
    db.add(row); db.flush()
    record_audit(db, actor=user, action="feedback.drift_assessed", resource_type="drift_assessment",
        resource_id=row.id, request_id=getattr(request.state, "request_id", None),
        details={"status": row.overall_status, "summary": row.summary})
    db.commit(); db.refresh(row)
    return {"id": row.id, "overall_status": row.overall_status, "feature_results": row.feature_results,
        "summary": row.summary, "created_at": row.created_at}


@router.get("/drift-assessments")
def list_drift_assessments(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                           user: User = Depends(require_roles(*_READER_ROLES))):
    stmt = _scoped(select(DriftAssessment), DriftAssessment, user)
    rows = db.scalars(stmt.order_by(DriftAssessment.created_at.desc()).limit(limit)).all()
    return [{"id": row.id, "overall_status": row.overall_status, "feature_results": row.feature_results,
        "summary": row.summary, "created_at": row.created_at} for row in rows]


@router.post("/suggestions/generate")
def generate_suggestions(request: Request, db: Session = Depends(get_db),
                         user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER", "RISK_REVIEWER"))):
    outcomes = list(db.scalars(_scoped(select(PredictionOutcome), PredictionOutcome, user)
        .order_by(PredictionOutcome.realised_date.desc()).limit(500)).all())
    drift = list(db.scalars(_scoped(select(DriftAssessment).where(DriftAssessment.overall_status == "DRIFT"), DriftAssessment, user)
        .order_by(DriftAssessment.created_at.desc()).limit(100)).all())
    strategies = list(db.scalars(_scoped(select(StrategyPerformanceSnapshot), StrategyPerformanceSnapshot, user)
        .order_by(StrategyPerformanceSnapshot.created_at.desc()).limit(20)).all())
    proposals: list[dict] = []
    if drift:
        proposals.append({"title": "Investigate feature-distribution drift",
            "rationale": "One or more monitored features crossed the configured PSI screening threshold.",
            "suggested_action": "Validate source data, feature definitions and point-in-time integrity; then run a fresh chronological evaluation. Do not auto-promote or auto-retrain.",
            "source_type": "DRIFT_ASSESSMENT", "source_id": drift[0].id})
    if len(outcomes) >= 10:
        metrics = summarize_outcomes([row.predicted_return for row in outcomes], [row.realised_return for row in outcomes])
        if abs(metrics["mean_bias"]) > max(metrics["mae"] * 0.25, 1e-9):
            proposals.append({"title": "Review forecast bias calibration",
                "rationale": "Recent realised outcomes show a material signed prediction error.",
                "suggested_action": "Break down error by instrument, horizon and model version, then evaluate calibration on a time-separated holdout.",
                "source_type": "OUTCOME_FEEDBACK", "source_id": None})
    if strategies:
        metrics = strategies[0].metrics
        sharpe = metrics.get("annualized_sharpe")
        if isinstance(sharpe, (int, float)) and sharpe < 0:
            proposals.append({"title": "Review strategy performance degradation",
                "rationale": "The latest monitoring period has a negative annualised Sharpe diagnostic.",
                "suggested_action": "Recheck transaction costs, benchmark alignment, turnover and out-of-sample window selection.",
                "source_type": "STRATEGY_PERFORMANCE", "source_id": strategies[0].id})
    if not proposals:
        proposals.append({"title": "Expand chronological evaluation coverage",
            "rationale": "No material feedback alert was found in the latest stored monitoring data.",
            "suggested_action": "Run a new walk-forward evaluation with a pinned snapshot, benchmark and feature-set version.",
            "source_type": "MONITORING_SUMMARY", "source_id": None})
    created = []
    for proposal in proposals:
        key = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()
        existing = db.scalar(select(ResearchSuggestion).where(
            ResearchSuggestion.created_by == user.id, ResearchSuggestion.dedupe_key == key))
        if existing:
            created.append(existing); continue
        row = ResearchSuggestion(**proposal, status="PROPOSED", dedupe_key=key, created_by=user.id)
        db.add(row); db.flush(); created.append(row)
    record_audit(db, actor=user, action="feedback.research_suggestions_generated",
        resource_type="research_suggestion_batch", request_id=getattr(request.state, "request_id", None),
        details={"count": len(created)})
    db.commit()
    return [{"id": row.id, "title": row.title, "rationale": row.rationale,
        "suggested_action": row.suggested_action, "source_type": row.source_type,
        "source_id": row.source_id, "status": row.status} for row in created]


@router.get("/suggestions", response_model=list[SuggestionResponse])
def list_suggestions(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                     user: User = Depends(require_roles(*_READER_ROLES))):
    stmt = _scoped(select(ResearchSuggestion), ResearchSuggestion, user)
    return list(db.scalars(stmt.order_by(ResearchSuggestion.created_at.desc()).limit(limit)).all())


@router.post("/suggestions/{suggestion_id}/decision", response_model=SuggestionResponse)
def decide_suggestion(suggestion_id: str, payload: SuggestionDecision, request: Request,
                      db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER"))):
    row = db.get(ResearchSuggestion, suggestion_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Research suggestion not found")
    if row.created_by != user.id and not any(role.key == "ADMIN" for role in user.roles):
        raise HTTPException(status_code=404, detail="Research suggestion not found")
    if row.status != "PROPOSED":
        raise HTTPException(status_code=409, detail="Only proposed suggestions can be decided")
    row.status = payload.status; row.decision_comment = payload.comment.strip()
    row.decided_by = user.id; row.decided_at = datetime.now(UTC)
    record_audit(db, actor=user, action=f"feedback.suggestion_{payload.status.lower()}",
        resource_type="research_suggestion", resource_id=row.id,
        request_id=getattr(request.state, "request_id", None), details={"comment": row.decision_comment})
    db.commit(); db.refresh(row)
    return row
