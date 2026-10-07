from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    postgres_user: str = "reflight"
    postgres_password: str = "changeme"
    postgres_db: str = "reflight"
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    rabbitmq_default_user: str = "reflight"
    rabbitmq_default_pass: str = "changeme"
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672

    redis_host: str = "localhost"
    redis_port: int = 6379

    minio_root_user: str = "reflight"
    minio_root_password: str = "changeme123"
    minio_host: str = "localhost"
    minio_port: int = 9000
    minio_bucket: str = "reflight"
    minio_secure: bool = False

    api_static_key: str = "dev-local-key-change-me"
    api_port: int = 8000

    partners_host: str = "localhost"
    partners_port: int = 8100

    rabbitmq_mgmt_host: str = "localhost"
    rabbitmq_mgmt_port: int = 15672
    prometheus_host: str = "localhost"
    prometheus_port: int = 9090

    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "reflight"

    # ---- managed-provider overrides -------------------------------------
    # Compose builds these URLs from the parts above. Hosted providers
    # (Render, Neon, CloudAMQP, Upstash...) hand you one connection string
    # instead -- often with a non-default vhost or a required TLS scheme --
    # so a full URL, when present, always wins over the parts.
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")
    rabbitmq_url_override: str | None = Field(default=None, alias="RABBITMQ_URL")
    redis_url_override: str | None = Field(default=None, alias="REDIS_URL")

    # Leave unset to talk to real AWS S3; set it to point at MinIO or R2.
    s3_endpoint_url: str | None = None

    # ---- single-instance hosted demo --------------------------------------
    # ALL_IN_ONE runs api + partners + relay + planner + worker in one
    # process (see cli.py), for hosts like Render's free tier.
    all_in_one: bool = False
    # Comma-separated origins allowed to call the API from a browser.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Full partners base URL; overrides partners_host/port when set.
    partners_url_override: str | None = Field(default=None, alias="PARTNERS_URL")
    # When set, scenario JSON is stored on local disk here instead of S3/MinIO.
    storage_dir: str | None = None
    # When set, the API also serves the built dashboard from this directory.
    dashboard_dist: str | None = None

    @property
    def partners_base_url(self) -> str:
        if self.partners_url_override:
            return self.partners_url_override.rstrip("/")
        return f"http://{self.partners_host}:{self.partners_port}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            url = self.database_url_override
            # Providers hand out postgres:// or postgresql://; SQLAlchemy 2
            # needs the driver named explicitly.
            for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
                if url.startswith(prefix):
                    return "postgresql+psycopg://" + url[len(prefix) :]
            return url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def rabbitmq_url(self) -> str:
        # %2F is the default vhost "/" URL-encoded. Managed brokers usually
        # give each account its own vhost, which is why the override matters.
        if self.rabbitmq_url_override:
            return self.rabbitmq_url_override
        return (
            f"amqp://{self.rabbitmq_default_user}:{self.rabbitmq_default_pass}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/%2F"
        )

    @property
    def minio_endpoint(self) -> str:
        scheme = "https" if self.minio_secure else "http"
        return f"{scheme}://{self.minio_host}:{self.minio_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
