"""Identity, authentication and user-administration API contracts."""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from finsight.core.schemas import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=10, max_length=128)


class UserResponse(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool
    created_at: datetime
    roles: list["RoleResponse"]


class RoleResponse(ORMModel):
    key: str
    name: str
    description: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RoleAssignmentRequest(BaseModel):
    role_keys: list[str] = Field(min_length=1, max_length=6)


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


UserResponse.model_rebuild()
