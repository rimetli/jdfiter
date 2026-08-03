from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "AI Resume Screening"
    app_secret: SecretStr
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    mysql_host: str
    mysql_port: int = 3306
    mysql_database: str
    mysql_username: str
    mysql_password: SecretStr
    mysql_ssl: bool = False
    mysql_ssl_ca: str | None = None

    llm_provider: str
    llm_base_url: str | None = None
    llm_api_key: SecretStr
    llm_model: str
    resume_llm_enabled: bool = False
    resume_vision_enabled: bool = True
    resume_vision_model: str | None = None
    resume_vision_max_pages: int = 5
    resume_vision_dpi: int = 160
    local_storage_path: str = "storage"
    task_max_attempts: int = 3
    task_lease_seconds: int = 300
    task_heartbeat_seconds: int = 30
    task_retry_base_seconds: int = 15
    task_retry_max_seconds: int = 300

    @property
    def effective_llm_base_url(self) -> str:
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.llm_provider.startswith(("http://", "https://")):
            return self.llm_provider.rstrip("/")
        if self.llm_provider == "openai":
            return "https://api.openai.com/v1"
        raise ValueError("请配置LLM_BASE_URL，或在LLM_PROVIDER中填写兼容接口地址")

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="mysql+asyncmy",
            username=self.mysql_username,
            password=self.mysql_password.get_secret_value(),
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
