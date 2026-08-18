# Hospital Automation — Project Memory

This file is the persistent memory for this project across Claude Code
sessions. **Read this first in any new session.** Update the "Status" and
"Deviations from plan" sections at the end of every phase, and commit.

---

## STATUS (updated 2026-08-18)

**Current phase: 0 (scaffold) in progress.**

Environment discovered on this machine:
- Python 3.14.5 is the system default, but LangGraph/SQLAlchemy/etc. are
  not yet reliably tested on it → using **Python 3.11.15** via `uv venv`
  at `backend/.venv` instead. Use `uv pip install -r requirements.txt
  --python .venv` for all backend deps, and invoke the venv's own
  python/uvicorn/alembic directly (`.venv/Scripts/...` on Windows) rather
  than relying on `python`/`pip` on PATH.
- Ollama is installed (v0.32.6) but only has `qwen2.5:3b-instruct` and
  `nemotron-mini` pulled — **not** the pinned `qwen2.5:7b-instruct-q4_K_M`.
  Need to `ollama pull qwen2.5:7b-instruct-q4_K_M` (or accept 3b as a
  lighter-weight stand-in during dev — it's noticeably worse at
  structured tool-calling, expect to lean on the deterministic-router
  fallback more if using it).
- Node v24.16.0, git 2.54.0 available.
- No Docker verified yet — docker-compose.yml is a stub, not yet tested.

Next up: finish Phase 0 (README/env/gitignore done, need first commit),
then Phase 1 (SQLAlchemy models + Alembic + seed script).

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

- None yet.
