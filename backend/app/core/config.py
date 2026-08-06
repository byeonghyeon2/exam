from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: str = "development"
    app_name: str = "Certification Exam App"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    database_url: str = "sqlite:///./cert_exam.db"
    frontend_origin: str = "http://localhost:5173"
    admin_access_key: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_verification_model: str = ""
    openai_explanation_model: str = ""
    openai_max_retries: int = Field(3, ge=0, le=10)
    openai_timeout_seconds: float = Field(60, gt=0)
    log_level: str = "INFO"
    timezone: str = "Asia/Seoul"


@lru_cache
def get_settings() -> Settings:
    return Settings()

