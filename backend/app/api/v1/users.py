"""Administrator-only user and role management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from finsight.core.security import require_roles
from finsight.infrastructure.database.session import get_db
from finsight.identity.models import Role, User
from finsight.identity.contracts import UserResponse
from finsight.identity.contracts import RoleAssignmentRequest, UserListResponse
from app.services.audit import record_audit

router = APIRouter(prefix="/users", tags=["user administration"])


@router.get("", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("ADMIN")),
) -> UserListResponse:
    users = list(db.scalars(select(User).options(selectinload(User.roles)).order_by(User.created_at.desc())).all())
    return UserListResponse(users=[UserResponse.model_validate(user) for user in users], total=len(users))


@router.patch("/{user_id}/roles", response_model=UserResponse)
def replace_user_roles(
    user_id: str,
    payload: RoleAssignmentRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("ADMIN")),
) -> User:
    target = db.scalar(select(User).options(selectinload(User.roles)).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    keys = list(dict.fromkeys(key.strip().upper() for key in payload.role_keys))
    roles = list(db.scalars(select(Role).where(Role.key.in_(keys))).all())
    if len(roles) != len(keys):
        known = {role.key for role in roles}
        raise HTTPException(status_code=422, detail=f"Unknown role keys: {', '.join(sorted(set(keys) - known))}")
    if target.id == admin.id and "ADMIN" not in keys:
        raise HTTPException(status_code=409, detail="Administrators cannot remove their own ADMIN role")
    target.roles = roles
    record_audit(
        db,
        actor=admin,
        action="identity.user_roles_replaced",
        resource_type="user",
        resource_id=target.id,
        request_id=getattr(request.state, "request_id", None),
        details={"role_keys": keys},
    )
    db.commit()
    db.refresh(target)
    return target
