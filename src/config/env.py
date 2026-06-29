from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv_ids(value: str) -> frozenset[str]:
    if not value.strip():
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def _parse_csv_ints(value: str) -> list[int]:
    if not value.strip():
        return []
    return [int(part.strip()) for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    node_env: str = "development"
    agent_name: str = "Obrabot"
    agent_system_prompt: str = (
        "Você é o agente CEO da Construtora AgentOS (Obrabot). "
        "Orquestre triagem e classificação de entradas de engenheiros de obra."
    )

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origin: str = "*"
    obrabot_api_key: str = ""

    database_url: str = "postgresql+asyncpg://obrabot:obrabot@localhost:5432/obrabot"
    redis_url: str = "redis://localhost:6379/0"
    rq_job_timeout_seconds: int = 900
    rq_retry_max: int = 3
    rq_retry_intervals_seconds: str = "30,120,300"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def rq_retry_intervals(self) -> list[int]:
        return _parse_csv_ints(self.rq_retry_intervals_seconds)

    openclaw_shared_secret: str = ""
    openclaw_require_hmac: bool = False
    openclaw_max_clock_skew_seconds: int = 300
    webhook_max_body_bytes: int = 10_485_760

    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    telegram_reply_enabled: bool = False
    telegram_allowed_chat_ids: str = ""
    telegram_allowed_user_ids: str = ""
    telegram_allowed_thread_ids: str = ""

    enable_telegram_file_download: bool = True
    max_image_bytes: int = 10_485_760
    max_audio_bytes: int = 26_214_400
    max_document_bytes: int = 52_428_800

    rate_limit_enabled: bool = True
    rate_limit_user_per_minute: int = 30
    rate_limit_chat_per_minute: int = 120
    rate_limit_window_seconds: int = 60

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
    def is_production(self) -> bool:
        return self.app_env.lower() == "production" or self.node_env.lower() == "production"

    @property
    def allowed_chat_ids(self) -> frozenset[str]:
        return _parse_csv_ids(self.telegram_allowed_chat_ids)

    @property
    def allowed_user_ids(self) -> frozenset[str]:
        return _parse_csv_ids(self.telegram_allowed_user_ids)

    @property
    def allowed_thread_ids(self) -> frozenset[str]:
        return _parse_csv_ids(self.telegram_allowed_thread_ids)

    @property
    def sync_database_url(self) -> str:
        url = self.async_database_url.replace("+asyncpg", "+psycopg2")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
