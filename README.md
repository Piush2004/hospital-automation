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
| WhatsApp | Baileys gateway (unofficial) → FastAPI webhook |
| Voice | faster-whisper (STT) + Ollama (LLM) + Piper (TTS), browser mic/speaker widget |
| Payments | Mock checkout by default, or Razorpay Test Mode (`MOCK_PAYMENTS=false`) |
| Reports | reportlab → PDF under `./storage/reports/`, delivered only after in-chat consent |
| Auth | JWT, roles: patient, doctor, front_desk, admin |

## Known limitations (by design, not bugs)

- **WhatsApp gateway** uses Baileys, an unofficial WhatsApp Web protocol
  library. This is **ToS-grey-area** and can get a phone number banned.
  It's fine for local prototyping only — use a throwaway/test number, not
  your primary one. Swap to the official Meta WhatsApp Cloud API (free
  tier, ~1000 conversations/mo, needs business verification) before any
  real deployment.
- **Voice** is a browser-based mic/speaker widget, not a real phone call —
  there is no free way to place/receive actual PSTN calls. A clean seam
  is left to plug in Twilio/Exotel later (that costs money). STT/TTS
  default to CPU inference (`base` Whisper model, `int8`) for reliability
  without CUDA version-matching headaches — bump `STT_DEVICE=cuda` in
  `.env` if you've got a working ctranslate2 CUDA setup and want it
  faster.
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
.venv/Scripts/uvicorn app.main:app --reload --ws-max-size 20971520
```

`--ws-max-size` raises the default 1MB websocket frame limit — the voice
channel's spoken replies (uncompressed WAV) can exceed it on longer
responses. Harmless to include even if you're not using voice.

Then open the frontend chat widget (Phase 4+):

```bash
cd frontend
npm install
npm run dev
```

### 5. Try the payments + reports loop

With the backend running (step 4), either click through the web chat
widget, or run the scripted transcript:

```bash
# from backend/
.venv/Scripts/python ../scripts/demo_walkthrough.py
```

This books an appointment, pays for it (mock checkout, no setup needed),
then simulates a doctor completing the visit and the patient consenting
to receive their report — all non-interactively. To do the "doctor"
step yourself instead:

```bash
.venv/Scripts/python -m app.doctor_cli
```

### 6. WhatsApp gateway (Phase 7)

**Read the ToS caveat under "Known limitations" above before doing this
against a real phone number.** Use a throwaway/test WhatsApp account, not
your primary one.

```bash
cd whatsapp-gateway
npm install
cp .env.example .env       # defaults match backend/.env's WHATSAPP_* keys
npm start
```

Scan the printed QR code with WhatsApp (**Settings → Linked Devices →
Link a Device**) on the phone you're pairing. Session credentials are
cached in `whatsapp-gateway/auth_info/` (gitignored) so you only need to
scan once. Once connected, message that WhatsApp number from any other
phone — the reply comes from the same orchestrator the web chat uses.

### 7. Voice channel

One-time: download a Piper voice model (default is `en_US-lessac-medium`,
~60MB — matches `TTS_VOICE` in `.env`):

```bash
# from backend/
.venv/Scripts/python -m piper.download_voices --download-dir ../storage/voices en_US-lessac-medium
```

faster-whisper's STT model downloads automatically on first use (cached
under `~/.cache/huggingface`) — no separate step needed. With the backend
running (step 4, **with `--ws-max-size` set**) and the frontend running
(step 4's second half), open the app and switch to the **Voice** tab,
enter a phone number, click **Start voice call**, then hold the mic
button to talk. First use will prompt for microphone permission.

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
      cli_repl.py             <- text REPL for exercising the orchestrator directly
      doctor_cli.py            <- crude internal tool: complete a visit, attach notes
      models/                <- SQLAlchemy models
      services/              <- DB access, business logic, PDF gen, payment providers, STT/TTS
      agents/                <- LangGraph orchestrator + specialist agents (incl. voice_agent.py)
      channels/               <- web_chat, whatsapp_webhook, payments_web, reports_web, voice_ws
      llm/                    <- ollama_client.py
    alembic/
    tests/
  whatsapp-gateway/            <- Node + Baileys unofficial WhatsApp bridge
  frontend/                    <- React + Vite widget (text chat + voice call modes)
  storage/
    reports/                  <- generated PDFs (gitignored)
    voices/                   <- downloaded Piper voice models (gitignored)
  scripts/
    seed_demo_data.py
    demo_walkthrough.py       <- scripted book->pay->complete->consent->deliver transcript
    stress_test.py            <- concurrent-load + race-condition smoke test
```
