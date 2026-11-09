"""Enabled market and filing provider catalogue."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.core.security import get_current_user
from finsight.infrastructure.database.session import get_db
from finsight.market_data.models import DataProvider
from finsight.identity.models import User
from app.schemas.catalogue import ProviderResponse

router = APIRouter(prefix="/providers", tags=["data providers"])


@router.get("", response_model=list[ProviderResponse])
def list_providers(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[DataProvider]:
    return list(
        db.scalars(select(DataProvider).where(DataProvider.is_enabled.is_(True)).order_by(DataProvider.key)).all()
    )
