"""Versioned HTTP API route registry."""

from fastapi import APIRouter

from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.data import router as data_router
from app.api.v1.documents import router as documents_router
from app.api.v1.ai_research import router as ai_research_router
from app.api.v1.ml import router as ml_router
from app.api.v1.health import router as health_router
from app.api.v1.instruments import router as instruments_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.providers import router as providers_router
from app.api.v1.research import router as research_router
from app.api.v1.users import router as users_router
from app.api.v1.governance import router as governance_router
from app.api.v1.execution import router as execution_router
from app.api.v1.rl import router as rl_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.operations import router as operations_router

api_router = APIRouter()
for route in (
    health_router,
    auth_router,
    instruments_router,
    providers_router,
    data_router,
    audit_router,
    users_router,
    jobs_router,
    research_router,
    documents_router,
    ai_research_router,
    ml_router,
    governance_router,
    execution_router,
    rl_router,
    feedback_router,
    operations_router,
):
    api_router.include_router(route)
