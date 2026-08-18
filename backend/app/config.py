from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database (absolute path so behavior doesn't depend on cwd)
    database_url: str = f"sqlite:///{(REPO_ROOT / 'hospital.db').as_posix()}"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_fallback_model: str = "llama3.1:8b-instruct-q4_K_M"

    # Auth
    jwt_secret: str = "change-me-to-a-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    # Payments
    mock_payments: bool = True
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # WhatsApp gateway
    whatsapp_webhook_secret: str = "change-me"
    whatsapp_gateway_url: str = "http://localhost:3001"

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    storage_dir: str = "./storage"

    @property
    def reports_dir(self) -> Path:
        path = REPO_ROOT / "storage" / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
