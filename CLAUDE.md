# Hospital Automation — Project Memory

This file is the persistent memory for this project across Claude Code
sessions. **Read this first in any new session.** Update the "Status" and
"Deviations from plan" sections at the end of every phase, and commit.

---

## STATUS (updated 2026-08-18)

**Phases 0-4 done — this session's target reached.** A real text
conversation (browser chat widget or CLI) can triage a symptom, assign a
doctor, and book a real appointment against the local DB, fully offline.
Phase 5 (payments) is next.

Environment discovered on this machine:
- Python 3.14.5 is the system default, but LangGraph/SQLAlchemy/etc. are
  not yet reliably tested on it → using **Python 3.11.15** via `uv venv`
  at `backend/.venv` instead. Use `uv pip install -r requirements.txt
  --python .venv` for all backend deps, and invoke the venv's own
  python/uvicorn/alembic directly (`.venv/Scripts/...` on Windows) rather
  than relying on `python`/`pip` on PATH.
- Ollama is installed (v0.32.6). `qwen2.5:7b-instruct-q4_K_M` (the pinned
  model) was being pulled in the background as of this update — check
  `ollama list`. `qwen2.5:3b-instruct` and `nemotron-mini` are also
  available locally as lighter fallbacks. **`.env` is currently pinned to
  `qwen2.5:3b-instruct`** as a temporary stand-in while the 7b model
  downloaded (slow connection, ~30 min pull) — switch `OLLAMA_MODEL` (and
  set a real `OLLAMA_FALLBACK_MODEL`, e.g. `llama3.1:8b-instruct-q4_K_M`
  if you pull it) back to the pinned model once available, and remove the
  temporary note comment above it in `.env`.
- Node v24.16.0, git 2.54.0 available.
- No Docker verified yet — docker-compose.yml is a stub, not yet tested.
- `.env` exists locally (gitignored, not committed) — copied from
  `.env.example`. A fresh session/machine needs to re-copy it.

### What's built (Phases 0-3)

- **Data layer**: SQLAlchemy models for User, Patient, Doctor +
  DoctorAvailability (weekly recurring windows), Department, Appointment,
  Payment, Report, ConversationSession, AuditLog. One Alembic migration
  applied. `scripts/seed_demo_data.py` seeds 6 departments, 7 doctors
  (with availability), 5 patients — idempotent, safe to re-run.
- **Services layer** (`backend/app/services/`): the DB "tools" agents
  call — patients, departments, doctors (incl. simple load-balancing via
  `best_available_doctor`), scheduling (weekly-availability-minus-bookings
  slot search + booking), conversations (session persistence), audit
  logging, and a deterministic keyword-based `emergency.py`.
- **LLM wiring** (`backend/app/llm/`): `ollama_client.py` wraps the
  Ollama chat API with retry + fallback-model logic and a `chat_json`
  helper that returns `None` (not an exception) on unparseable output, so
  callers can degrade gracefully. `prompts.py` has the triage
  classification prompt template.
- **Agents** (`backend/app/agents/`):
  - `triage_agent.py` — LLM-based symptom→department classification with
    a deterministic keyword fallback (see "Deviations" below).
  - `scheduling_agent.py` — fully deterministic: doctor assignment,
    slot-finding, slot-choice parsing, booking. No LLM involved by design.
  - `orchestrator.py` — the LangGraph supervisor. **Per-turn graph**: a
    channel calls `run_turn(db, state, user_input)` once per inbound
    message; state is a plain JSON-serializable dict persisted in
    `ConversationSession.state` between calls (no live graph process, no
    checkpointer needed). Routing is deterministic, keyed off a `stage`
    field. Graph shape and full rationale are documented in the module
    docstring — read it before modifying.
- **CLI REPL** (`backend/app/cli_repl.py`): `python -m app.cli_repl
  [phone]` — manually verified end-to-end: new-patient name capture,
  LLM-based triage → doctor assignment → slot listing → booking, and the
  emergency fast-path (with audit log entry). All working against the
  real seeded DB.
- **Tests**: 17 pytest tests across scheduling, emergency detection,
  triage fallback, and full orchestrator conversation flows (in-memory
  SQLite fixture in `tests/conftest.py`). All passing.

### Bug found & fixed during Phase 2/3 testing

SQLite doesn't round-trip `tzinfo` through SQLAlchemy's
`DateTime(timezone=True)` — values read back naive. `available_slots()`
in `scheduling.py` was building its "already booked" exclusion set from
DB rows (naive) and comparing against freshly-generated candidate slots
(tz-aware UTC); naive != aware always compares False, so **booked slots
were never actually excluded** — a real double-booking bug, not just a
test artifact. Fixed by re-attaching UTC tzinfo when reading booked slots
back out. Caught by `test_available_slots_excludes_booked` — this is why
the pytest suite matters even in a fast-moving MVP.

### What's built (Phase 4)

- **`backend/app/channels/web_chat.py`** — FastAPI WebSocket endpoint at
  `/ws/chat?phone=<phone>`. Thin adapter: identify/create patient +
  session (same services the CLI uses), then loop on `run_turn()`. One
  JSON frame per turn out (`{"role", "content", "stage"}`), one text
  frame per turn in. CORS opened for `localhost:5173` (Vite dev) in
  `main.py` — tighten before any real deployment.
- **`frontend/`** — minimal React + Vite chat widget (no UI framework, no
  state library — plain hooks + CSS, per the "modest footprint"
  constraint). Phone-number "identify" screen, then a chat log +
  composer. Shows a red emergency banner when a turn's response carries
  `stage: "emergency"`. `VITE_WS_URL` env var overrides the WS endpoint
  (defaults to `ws://localhost:8000/ws/chat`).
- **Verified two ways**: a raw Python `websockets` client script
  (booking flow end-to-end) and manually in Chrome via claude-in-chrome
  (typed a symptom, got triaged to Orthopedics, booked a slot, screenshot
  confirmed the UI renders correctly, no console errors).
- **Dockerfiles added** for `backend/` and `frontend/` and
  `docker-compose.yml` now wires up all three services (ollama, backend,
  frontend) — **not yet tested end-to-end via `docker compose up`**; the
  non-Docker path is what's actually been verified this session.

Dev servers were left running at the end of this session for a quick
first look: backend on :8000, frontend on :5173. Restart per README if
they're no longer up.

Next up: Phase 5 — Payments agent (mock-mode first, then Razorpay
test-mode keys behind the same interface).

---

## Mission

Build a local-first, zero-cost multi-agent hospital automation system:
appointment booking, doctor assignment/triage, an AI voice assistant,
WhatsApp-style chat support, medical report generation/delivery, and
payment handling — coordinated by one orchestrator agent.

Optimize for a real, running MVP over exhaustive polish — get something
end-to-end working before adding channels.

## Hard constraints

- **100% local and free to run.** No paid APIs in the deployed app. The
  only "AI brain" is a locally-hosted Ollama model — never call
  Anthropic/OpenAI/Gemini APIs from the app itself.
- **No cloud services required to run day-to-day.** SQLite (or local
  Postgres via Docker), local file storage, local LLM. Payment gateway and
  WhatsApp integration are the two exceptions, both handled in
  sandbox/free-tier mode — never wired to move real money or require a
  paid plan.
- **Modest footprint.** Keep dependencies lean. Must run comfortably on:
  24GB RAM, RTX 5060 (8GB VRAM), Python + FastAPI backend.

## Pinned tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11, FastAPI | best free local-AI ecosystem |
| DB | SQLite via SQLAlchemy + Alembic | zero-setup now, one-line swap to Postgres later |
| LLM runtime | Ollama, `qwen2.5:7b-instruct-q4_K_M` (fallback `llama3.1:8b-instruct-q4_K_M`) | fits 8GB VRAM w/ GPU accel; try `qwen2.5:14b-instruct-q4_K_M` later if quality needs a bump |
| Agent orchestration | LangGraph (self-hosted, no LangSmith/cloud) | supervisor pattern, tool-calling, explicit state graph |
| Web chat channel | FastAPI WebSocket + tiny React (Vite) widget | cheapest way to test the whole conversation loop before WhatsApp |
| WhatsApp channel | Baileys (Node.js) standalone gateway → FastAPI webhook | free, no Meta business verification for prototyping. **ToS-grey-area, can get a number banned** — swap to official Meta WhatsApp Cloud API before real deployment. Phase 7, after everything else works over web chat. |
| Voice channel | faster-whisper (STT) + Ollama (LLM) + Piper (TTS), browser mic/speaker widget | browser voice assistant, NOT real PSTN calls. Twilio/Exotel is the (paid) upgrade seam. |
| Payments | Razorpay Test Mode, `MOCK_PAYMENTS=true` flag | works immediately, zero external account needed |
| Reports | reportlab/weasyprint → PDF under `./storage/reports/` | free, local, no cloud storage |
| Auth | JWT, roles: patient, doctor, front_desk, admin | simple, no external auth provider |
| Containerization | docker-compose.yml (backend, Ollama, optional Postgres, whatsapp-gateway, frontend); everything also runs without Docker via plain pip/npm | one-command spin-up is nice-to-have, not a blocker |

## Architecture recap

One **Orchestrator Agent** (LangGraph supervisor) sits in front of every
channel and routes to specialist agents, each a LangGraph node with its
own tools bound to the DB/services layer:

1. **Triage & Doctor-Assignment** — classify symptoms/department, match to
   a specialist by expertise, availability, and current load.
2. **Appointment Scheduling** — find slots, book/reschedule/cancel, keep
   doctor calendars in sync.
3. **Voice Agent** — browser-based voice intake/reminders.
4. **WhatsApp/Chat Support Agent** — FAQs, document upload, booking
   conversation, feedback.
5. **Payments & Billing** — payment links/mock checkout, reconciliation
   status.
6. **Report Generation** — compiles a structured report from
   appointment/lab data.
7. **Report Delivery** — sends the finished report to the right patient
   (chat/email) after a consent check.
8. **Notifications & Reminders** — reminders for appointments/follow-ups
   (in-app + email via local SMTP or free provider, never required).

Plus an **emergency fast-path**: if the Voice or Chat agent detects
emergency language, the orchestrator skips scheduling/payment and flags
the case for immediate human (front-desk/admin) attention in the
dashboard — no real ER integration, just a loud, prioritized alert.

## Data model (starting point — adjust as needed)

`User(role)`, `Patient`, `Doctor(specialty, department)`, `Department`,
`Appointment(patient, doctor, slot, status)`,
`Payment(appointment, amount, status, provider_ref)`,
`Report(appointment, file_path, delivered_at, consent_at)`,
`ConversationSession(channel, patient, state, history)`,
`AuditLog(actor, action, entity, timestamp)`.

## Repo layout

```
hospital-automation/
  CLAUDE.md                  <- this file
  README.md
  .env.example
  docker-compose.yml
  backend/
    app/
      main.py
      models/                <- SQLAlchemy models
      services/              <- DB access, business logic, PDF gen, mock payments
      agents/
        orchestrator.py
        triage_agent.py
        scheduling_agent.py
        payments_agent.py
        report_agent.py
        notifications_agent.py
        voice_agent.py        (Phase 8)
      channels/
        web_chat.py           (Phase 4)
        whatsapp_webhook.py   (Phase 7)
        voice_ws.py           (Phase 8)
      llm/
        ollama_client.py
    alembic/
    tests/
  whatsapp-gateway/            <- Node + Baileys, Phase 7 only
  frontend/                    <- React + Vite: chat widget + admin dashboard
  scripts/
    seed_demo_data.py
```

## Build phases

Work through these in order, commit after each one lands and passes its
own smoke test.

- **Phase 0 — Scaffold.** Repo structure, `.env.example`, README, stub
  docker-compose.yml, git init + first commit.
- **Phase 1 — Data layer.** SQLAlchemy models, Alembic migration,
  `scripts/seed_demo_data.py` with departments/doctors/fake patients.
- **Phase 2 — Orchestrator skeleton.** LangGraph graph with supervisor +
  Triage + Scheduling agents wired to real DB tools, testable from a
  plain CLI/REPL script (no HTTP yet). Get the "brain" booking a real
  appointment end-to-end in text before building any UI.
- **Phase 3 — LLM wiring.** Ollama client wrapper, prompt templates per
  agent, tool-calling contracts, retries/validation for local-model
  quirks.
- **Phase 4 — Web chat channel.** FastAPI WebSocket endpoint + minimal
  React chat widget talking to the orchestrator. *(Natural checkpoint —
  if usage runs low, stop here with everything committed.)*
- **Phase 5 — Payments agent.** Mock-mode first, then real Razorpay
  test-mode keys behind the same interface.
- **Phase 6 — Reports.** Generation (PDF) + delivery (in-chat link/email)
  with a consent check step before sending anything.
- **Phase 7 — WhatsApp gateway.** Baileys service + webhook wiring into
  the same orchestrator used by web chat.
- **Phase 8 — Voice agent.** faster-whisper + Piper + Ollama behind a
  browser widget.
- **Phase 9 — Admin dashboard.** Doctor calendar view, appointments
  table, audit log viewer, emergency-flag inbox.
- **Phase 10 — Tests & polish.** pytest coverage on services/agents,
  full end-to-end demo script using seed data.

## Working rules (for Claude Code across sessions)

- Prefer small, real, working increments over large speculative
  scaffolding.
- If local model tool-calling turns out unreliable for a given agent,
  it's fine to fall back to a simpler deterministic router
  (keyword/intent classifier) for that specific step — note the tradeoff.
  A working simple thing beats a broken clever thing here.
- Update this file at the end of every phase: what's done, what's next,
  any deviations from the plan and why.
- Commit after each phase with a clear message. Don't let uncommitted
  work pile up across a session boundary.

## Deviations from plan (log as they happen)

- **Supervisor routing is deterministic, not LLM-driven.** The
  orchestrator's node-to-node routing (`orchestrator.py`) is keyed off an
  explicit `stage` field rather than an LLM deciding "which agent next."
  Only symptom→department classification (triage) actually calls the
  local LLM; scheduling (slot search, booking) is pure DB logic. This
  follows the working rule "a working simple thing beats a broken clever
  thing" — control flow correctness matters more than flexibility here,
  and a 7B-class local model adds real value in the one place it's used
  (free-text interpretation) without being asked to also reliably drive
  graph control flow.
- **Phases 2 and 3 were built together**, not sequentially. The
  orchestrator skeleton (Phase 2) isn't meaningfully testable without
  LLM-based triage, so `ollama_client.py` / `prompts.py` (Phase 3) landed
  in the same session before the Phase 2 CLI smoke test could run.
- **Emergency detection is deterministic keyword matching**, not LLM
  based — intentional, not a fallback-of-convenience. See the docstring
  in `app/services/emergency.py`: a safety-critical gate shouldn't depend
  on a small local model's occasional miss.
