"""Typed runtime configuration for FinSight ResearchOps."""
from functools import lru_cache
from typing import Literal
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Secret values are supplied through environment variables."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")
    app_name: str = "FinSight ResearchOps API"
    api_version: str = "0.1.0"
    app_env: str = "local"
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    database_url: str = "sqlite:///./finsight_dev.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "local-development-secret-change-before-deployment-2026"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    allow_self_registration: bool = True
    sec_edgar_user_agent: str = "FinSightResearchOps contact@example.com"
    data_storage_path: str = "./data"
    max_ingestion_rows: int = Field(default=100_000, ge=1, le=1_000_000)
    experiment_tracking_backend: Literal["local", "mlflow"] = "local"
    mlflow_tracking_uri: str | None = None
    max_document_upload_bytes: int = Field(default=15 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    document_chunk_size: int = Field(default=420, ge=50, le=2000)
    document_chunk_overlap: int = Field(default=60, ge=0, le=500)
    document_embedding_dimensions: int = Field(default=384, ge=64, le=4096)
    document_embedding_provider: Literal["feature_hash_v1", "sentence_transformers"] = "feature_hash_v1"
    document_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    document_vector_backend: Literal["json", "pgvector"] = "json"
    document_reranker: Literal["none", "cross_encoder"] = "none"
    document_reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    research_workflow_engine: Literal["deterministic", "langgraph"] = "deterministic"
    research_synthesis_provider: Literal["extractive", "multi_analyst", "langchain_openai"] = "extractive"
    research_llm_model: str = "gpt-4.1-mini"
    max_document_chunks: int = Field(default=10_000, ge=1, le=50_000)
    max_ml_evaluation_rows: int = Field(default=100_000, ge=100, le=1_000_000)
    otel_service_name: str = "finsight-researchops-api"
    otel_exporter_otlp_endpoint: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env.lower() in {"production", "prod"}:
            weak_tokens = ("replace", "example", "change-me", "change-before")
            if len(self.jwt_secret) < 32 or any(token in self.jwt_secret.lower() for token in weak_tokens):
                raise ValueError("JWT_SECRET must be a strong, unique secret in production")
            if self.debug:
                raise ValueError("DEBUG must be false in production")
        if self.document_vector_backend == "pgvector" and self.document_embedding_dimensions != 384:
            raise ValueError("The current pgvector migration supports exactly 384 embedding dimensions")
        if self.document_reranker == "cross_encoder" and not self.document_reranker_model.strip():
            raise ValueError("DOCUMENT_RERANKER_MODEL is required when cross-encoder reranking is enabled")
        if self.experiment_tracking_backend == "mlflow" and not self.mlflow_tracking_uri:
            raise ValueError("MLFLOW_TRACKING_URI is required for the MLflow tracking backend")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings for this process."""
    return Settings()
