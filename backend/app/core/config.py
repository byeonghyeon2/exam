from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "Certification Exam App"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False
    database_url: str = "sqlite:///./cert_exam.db"
    database_host: str = ""
    database_port: int = 3306
    database_name: str = ""
    database_user: str = ""
    database_password: str = ""
    frontend_origin: str = "http://localhost:5173"
    cors_allow_local_network: bool = True
    proxy_trusted_ips: str = "127.0.0.1"
    admin_access_key: str = ""
    auth_required: bool = True
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""
    auth_session_days: int = Field(30, ge=1, le=365)
    auth_cookie_secure: bool = False
    question_rate_limit_requests: int = Field(60, ge=1, le=10000)
    question_rate_limit_window_seconds: int = Field(60, ge=1, le=3600)
    openai_api_key: str = ""
    openai_model: str = ""
    openai_verification_model: str = ""
    openai_explanation_model: str = ""
    openai_max_retries: int = Field(3, ge=0, le=10)
    openai_timeout_seconds: float = Field(60, gt=0)
    log_level: str = "INFO"
    timezone: str = "Asia/Seoul"

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        """Prefer explicit DB fields so credentials do not need duplicating in DATABASE_URL."""
        if all((self.database_host, self.database_name, self.database_user, self.database_password)):
            user = quote_plus(self.database_user)
            password = quote_plus(self.database_password)
            self.database_url = (
                f"mysql+pymysql://{user}:{password}@{self.database_host}:"
                f"{self.database_port}/{self.database_name}?charset=utf8mb4"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
