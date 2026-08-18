from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Hospital Automation API")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "ollama_model": settings.ollama_model,
    }
