"""应用配置：从项目根目录的 .env 读取，字段名与 .env 保持一致。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
STATIC_DIR = BACKEND_DIR / "app" / "static"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_secret_key: str = "dev-secret"

    db_backend: str = "sqlite"
    db_sqlite_path: str = "./runtime/app.db"
    db_sqlite_busy_timeout_ms: int = 5000
    db_postgres_dsn: str = ""
    db_postgres_pool_size: int = 5
    db_postgres_max_overflow: int = 10

    retrieval_backend: str = "snapshot"
    retrieval_cache_dir: str = "./runtime/index-cache"
    retrieval_max_index_bytes: int = 8_000_000

    worker_concurrency: int = 1
    checkpoint_backend: str = "sqlite"  # sqlite | postgres
    checkpoint_sqlite_path: str = "./runtime/checkpoints.db"
    checkpoint_postgres_dsn: str = ""  # 留空则复用 DB_POSTGRES_DSN

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-flash"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""

    max_upload_bytes: int = 20 * 1024 * 1024

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key.strip())

    @property
    def runtime_dir(self) -> Path:
        return self.resolve_path("./runtime")

    def resolve_path(self, value: str) -> Path:
        """相对路径统一按项目根解析，避免受启动目录影响。"""
        p = Path(value)
        return p if p.is_absolute() else (PROJECT_DIR / p).resolve()

    @property
    def sqlite_path(self) -> Path:
        return self.resolve_path(self.db_sqlite_path)

    @property
    def checkpoint_dsn(self) -> str:
        """PostgreSQL 检查点使用的 libpq DSN（去掉 SQLAlchemy 的 +asyncpg 后缀）。"""
        dsn = (self.checkpoint_postgres_dsn or self.db_postgres_dsn).strip()
        return dsn.replace("postgresql+asyncpg://", "postgresql://")

    def ensure_runtime(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        STATIC_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
