from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = ""

    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000

    LIGHTRAG_WORKING_DIR: str = "data/lightrag"
    RAG_QUERY_MODE: str = "hybrid"

    AGENT_RECURSION_LIMIT: int = 12
    HITL_ENABLED: bool = False
    APPROVAL_TOOLS: str = "ping_host,http_probe"

    LLM_TIMEOUT: int = 60
    TOOL_TIMEOUT: int = 3
    UPLOAD_MAX_MB: int = 20

    GRAPH_STORAGE: str = "NetworkXStorage"
    VECTOR_STORAGE: str = "NanoVectorDBStorage"


@lru_cache
def get_settings() -> Settings:
    return Settings()
