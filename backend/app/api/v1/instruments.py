"""Instrument catalogue endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.core.security import get_current_user, require_roles
from finsight.infrastructure.database.session import get_db
from finsight.market_data.models import Instrument
from finsight.identity.models import User
from app.schemas.catalogue import InstrumentCreate, InstrumentResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentResponse])
def list_instruments(
    active_only: bool = True, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[Instrument]:
    query = select(Instrument).order_by(Instrument.symbol)
    if active_only:
        query = query.where(Instrument.is_active.is_(True))
    return list(db.scalars(query).all())


@router.post("", response_model=InstrumentResponse, status_code=status.HTTP_201_CREATED)
def create_instrument(
    payload: InstrumentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "QUANT_RESEARCHER")),
) -> Instrument:
    symbol = payload.symbol.upper()
    if db.scalar(select(Instrument).where(Instrument.symbol == symbol)):
        raise HTTPException(status_code=409, detail="Instrument already exists")
    instrument = Instrument(**payload.model_dump(exclude={"symbol"}), symbol=symbol)
    db.add(instrument)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="catalogue.instrument_created",
        resource_type="instrument",
        resource_id=instrument.id,
        request_id=getattr(request.state, "request_id", None),
        details={"symbol": instrument.symbol},
    )
    db.commit()
    db.refresh(instrument)
    return instrument
