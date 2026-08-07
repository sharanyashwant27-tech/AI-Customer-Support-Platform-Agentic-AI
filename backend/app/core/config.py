"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the AI Customer Support Platform."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "AI Customer Support Platform"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8917
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # Security / JWT
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    oauth2_token_url: str = "/api/v1/auth/token"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "aics"
    postgres_password: str = "aics_secret"
    postgres_db: str = "aics_db"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # RabbitMQ
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "aics"
    rabbitmq_password: str = "aics_secret"
    rabbitmq_vhost: str = "/"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "aics_neo4j_secret"

    # Vector DB
    vector_store: Literal["qdrant", "pinecone", "chroma"] = "qdrant"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "knowledge_base"
    pinecone_api_key: str = ""
    pinecone_index: str = "aics-knowledge"
    chroma_persist_dir: str = "./data/chroma"

    # LLM providers
    default_llm_provider: Literal["openai", "anthropic", "gemini", "llama"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-5"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    llama_base_url: str = "http://localhost:11434/v1"
    llama_model: str = "llama3.1"
    pinecone_environment: str = "us-east-1"

    # Embeddings — OpenAI text embeddings / BGE Large / E5 Large / Sentence Transformers
    default_embedding_provider: Literal[
        "openai", "bge", "e5", "sentence_transformers"
    ] = "openai"
    openai_embedding_model: str = "text-embedding-3-large"
    bge_model_name: str = "BAAI/bge-large-en-v1.5"
    e5_model_name: str = "intfloat/e5-large-v2"
    sentence_transformer_model: str = "sentence-transformers/all-mpnet-base-v2"
    embedding_dimension: int = 3072

    # RAG
    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 5
    confidence_threshold: float = 0.65
    handoff_confidence_threshold: float = 0.45
    clarification_confidence_threshold: float = 0.9

    # Observability
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    enable_metrics: bool = True
    prometheus_metrics_path: str = "/metrics"

    # n8n
    n8n_webhook_base_url: str = "http://localhost:5678/webhook"

    # Channel integrations
    slack_webhook_url: str = ""
    slack_default_channel: str = "#support"
    teams_webhook_url: str = ""
    whatsapp_webhook_url: str = ""
    whatsapp_verify_token: str = "aics-whatsapp-verify"
    email_webhook_url: str = ""
    voice_webhook_url: str = ""
    voice_default_voice: str = "alloy"
    default_language: str = "en"
    enable_auto_translate: bool = True

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.startswith("["):
                import json

                return json.loads(cleaned)
            return [origin.strip() for origin in cleaned.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
