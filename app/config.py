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

    # LightRAG 官方控制台（/webui + /lightrag-api）。带删文档/改图谱的写接口，
    # 且未配 AUTH_ACCOUNTS、LIGHTRAG_API_KEY 时不鉴权，所以默认关闭。
    LIGHTRAG_CONSOLE: bool = False

    AGENT_RECURSION_LIMIT: int = 24
    HITL_ENABLED: bool = False
    APPROVAL_TOOLS: str = "ping_host,http_probe"

    LLM_TIMEOUT: int = 150
    TOOL_TIMEOUT: int = 3
    UPLOAD_MAX_MB: int = 20

    GRAPH_STORAGE: str = "NetworkXStorage"
    VECTOR_STORAGE: str = "NanoVectorDBStorage"


@lru_cache
def get_settings() -> Settings:
    return Settings()
