"""Registration, login and authenticated identity endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from finsight.core.config import get_settings
from finsight.core.security import create_access_token, ensure_role, get_current_user, hash_password, verify_password
from finsight.infrastructure.database.session import get_db
from finsight.identity.models import User
from finsight.identity.contracts import RegisterRequest, TokenResponse, UserResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, db: Session = Depends(get_db)
) -> User:
    settings = get_settings()
    if not settings.allow_self_registration:
        raise HTTPException(status_code=403, detail="Self-registration is disabled")
    normalized_email = str(payload.email).lower()
    if db.scalar(select(User).where(User.email == normalized_email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    try:
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = User(email=normalized_email, full_name=payload.full_name.strip(), password_hash=password_hash)
    user.roles.append(ensure_role(db, "RESEARCH_ANALYST"))
    db.add(user)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="identity.user_registered",
        resource_type="user",
        resource_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user)
    record_audit(
        db,
        actor=user,
        action="identity.login_succeeded",
        resource_type="user",
        resource_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    db.commit()
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().access_token_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
