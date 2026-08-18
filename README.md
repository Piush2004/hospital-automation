# Hospital Automation

A local-first, zero-cost multi-agent hospital automation system: appointment
booking, doctor assignment/triage, an AI voice assistant, chat support,
medical report generation/delivery, and payment handling — coordinated by
one orchestrator agent (LangGraph supervisor pattern).

**Everything runs on your machine for free.** The only "AI brain" is a
locally-hosted [Ollama](https://ollama.com) model. No paid APIs are called
by the running app (Payments and WhatsApp use free sandbox/prototyping modes
— see caveats below).

See `CLAUDE.md` for the full architecture, build-phase plan, and current
progress status.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI |
| DB | SQLite via SQLAlchemy + Alembic |
| LLM runtime | Ollama (`qwen2.5:7b-instruct-q4_K_M`, fallback `llama3.1:8b-instruct-q4_K_M`) |
| Agent orchestration | LangGraph (self-hosted, no LangSmith/cloud) |
| Web chat | FastAPI WebSocket + React (Vite) widget |
| WhatsApp (Phase 7) | Baileys gateway (unofficial) → FastAPI webhook |
| Voice (Phase 8) | faster-whisper + Ollama + Piper TTS, browser mic/speaker widget |
| Payments | Razorpay Test Mode / `MOCK_PAYMENTS=true` |
| Reports | reportlab → PDF under `./storage/reports/` |
| Auth | JWT, roles: patient, doctor, front_desk, admin |

## Known limitations (by design, not bugs)

- **WhatsApp gateway (Phase 7)** uses Baileys, an unofficial WhatsApp Web
  protocol library. This is **ToS-grey-area** and can get a phone number
  banned. It's fine for local prototyping only. Swap to the official Meta
  WhatsApp Cloud API (free tier, ~1000 conversations/mo, needs business
  verification) before any real deployment.
- **Voice (Phase 8)** is a browser-based mic/speaker widget, not a real
  phone call — there is no free way to place/receive actual PSTN calls.
  A clean seam is left to plug in Twilio/Exotel later (that costs money).
- **Payments** run in Razorpay Test Mode / mock mode. No real money ever
  moves through this app as shipped.
- **Emergency fast-path** is a prioritized alert in the admin dashboard,
  not a real integration with emergency services.

## Prerequisites

- Python 3.11 (this repo's `backend/.venv` is pinned to 3.11 via `uv`,
  since the LangGraph/SQLAlchemy ecosystem is not yet reliable on very new
  Python releases)
- [Ollama](https://ollama.com) installed and running locally
- Node.js 18+ (for the frontend chat widget, Phase 4+, and the WhatsApp
  gateway, Phase 7)
- (Optional) Docker + docker-compose for one-command spin-up

## Local dev (no Docker)

### 1. Pull a local model

```bash
ollama pull qwen2.5:7b-instruct-q4_K_M
# or, if VRAM/bandwidth constrained, whatever you already have, e.g.:
# ollama pull qwen2.5:3b-instruct
```

Set `OLLAMA_MODEL` in `.env` to match whatever you actually pulled.

### 2. Backend setup

```bash
cd backend
uv venv --python 3.11 .venv          # one-time
uv pip install -r requirements.txt --python .venv
cp ../.env.example ../.env            # then edit as needed
```

Run migrations and seed demo data:

```bash
# from backend/
.venv/Scripts/alembic upgrade head        # Windows
# .venv/bin/alembic upgrade head           # macOS/Linux
python ../scripts/seed_demo_data.py
```

### 3. Try the orchestrator from the CLI (Phase 2+)

```bash
.venv/Scripts/python -m app.cli_repl
```

### 4. Run the API + web chat (Phase 4+)

```bash
.venv/Scripts/uvicorn app.main:app --reload
```

Then open the frontend chat widget (Phase 4+):

```bash
cd frontend
npm install
npm run dev
```

## Docker (optional)

```bash
docker compose up --build
```

## Repo layout

```
hospital-automation/
  CLAUDE.md                  <- architecture, phase plan, live progress log
  README.md
  .env.example
  docker-compose.yml
  backend/
    app/
      main.py
      models/                <- SQLAlchemy models
      services/              <- DB access, business logic, PDF gen, mock payments
      agents/                <- LangGraph orchestrator + specialist agents
      channels/               <- web_chat (Phase 4), whatsapp_webhook (Phase 7), voice_ws (Phase 8)
      llm/                    <- ollama_client.py
    alembic/
    tests/
  whatsapp-gateway/            <- Node + Baileys, Phase 7 only
  frontend/                    <- React + Vite: chat widget + admin dashboard
  scripts/
    seed_demo_data.py
```
