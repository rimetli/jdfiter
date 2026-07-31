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
    cors_origins: list[str] = ["http://localhost:5173"]

    mysql_host: str
    mysql_port: int = 3306
    mysql_database: str
    mysql_username: str
    mysql_password: SecretStr
    mysql_ssl: bool = False
    mysql_ssl_ca: str | None = None

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
