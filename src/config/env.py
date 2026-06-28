from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    node_env: str = "development"
    agent_name: str = "Obrabot"
    agent_system_prompt: str = (
        "Você é o agente CEO da Construtora AgentOS (Obrabot). "
        "Orquestre triagem e classificação de entradas de engenheiros de obra."
    )

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origin: str = "*"

    database_url: str = "postgresql+asyncpg://obrabot:obrabot@localhost:5432/obrabot"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    openclaw_shared_secret: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_vision_model: str = "gpt-4o-mini"
    openai_transcription_model: str = "whisper-1"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_base_url: str = "https://api.openai.com/v1"

    local_bucket_path: str = ".local-bucket"
    templates_dir: str = "src/templates"

    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "bucket-construtora"
    s3_region: str = "us-east-1"

    @property
    def sync_database_url(self) -> str:
        url = self.async_database_url.replace("+asyncpg", "+psycopg2")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
