from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.channels.payments_web import router as payments_router
from app.channels.web_chat import router as web_chat_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Hospital Automation API")

# Local dev only: the Vite frontend runs on a different port. Tightened
# before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(web_chat_router)
app.include_router(payments_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "env": settings.app_env,
        "ollama_model": settings.ollama_model,
    }
