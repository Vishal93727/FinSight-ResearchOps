"""Password hashing, JWT creation and role-based access helpers."""
import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from finsight.core.config import get_settings
from finsight.infrastructure.database.session import get_db
from finsight.identity.models import Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters")
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt${}${}".format(base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(derived).decode())


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_text, digest_text = password_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": user.id, "roles": [role.key for role in user.roles], "iat": now,
               "exp": now + timedelta(minutes=settings.access_token_minutes), "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required",
                                 headers={"WWW-Authenticate": "Bearer"})
    if not token:
        raise unauthorized
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if payload.get("type") != "access" or not user_id:
            raise unauthorized
    except jwt.PyJWTError as exc:
        raise unauthorized from exc
    user = db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if user is None:
        raise unauthorized
    return user


def require_roles(*allowed_roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if not {role.key for role in user.roles}.intersection(allowed_roles):
            raise HTTPException(status_code=403, detail="Insufficient role permissions")
        return user
    return dependency


def ensure_role(db: Session, role_key: str) -> Role:
    role = db.scalar(select(Role).where(Role.key == role_key))
    if role is None:
        role = Role(key=role_key, name=role_key.replace("_", " ").title())
        db.add(role)
        db.flush()
    return role
