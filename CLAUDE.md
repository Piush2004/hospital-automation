# Hospital Automation — Project Memory

This file is the persistent memory for this project across Claude Code
sessions. **Read this first in any new session.** Update the "Status" and
"Deviations from plan" sections at the end of every phase, and commit.

---

## STATUS (updated 2026-08-18, session 3)

**Phases 0-8 done**, plus a stress-test pass earlier this session that
found and fixed two real concurrency bugs (see "Stress test findings"
below — do this before trusting the app under any real concurrent load,
it's not optional polish). A real conversation — browser text chat,
CLI, real WhatsApp, or now browser voice — can triage a symptom, assign
a doctor, book a real appointment, pay for it (mock checkout by
default), have a doctor complete the visit with notes, ask the patient
for consent, and deliver a generated PDF report — fully offline, end to
end, over any of those four channels, verified safe under concurrent
multi-patient load. Phase 9 (admin dashboard) is the nominal next phase,
but real auth is worth considering first — see "Deviations" for why it's
been deferred multiple times now.

### Stress test findings (session 3) — fixed, re-verified

Ran `scripts/stress_test.py` (new this session) against the live server:
8 patients concurrently competing for the same doctor's slots, plus 15
concurrent full booking flows across departments. **First run failed
badly** — both bugs below were real, not test artifacts:

1. **Double-booking race condition.** `book_appointment()` only checked
   "is this slot free?" via a SELECT, then inserted — no atomicity
   between the two. One slot got booked **7 times** in the first run.
   Fixed with a DB-level partial unique index on
   `(doctor_id, slot_start)` WHERE status is active (see
   `Appointment.__table_args__` in `app/models/appointment.py`,
   migration `da269aa6b22a`). `book_appointment()` now catches the
   resulting `IntegrityError` and raises a clean `SlotAlreadyBookedError`;
   the orchestrator's `slot_choice_node` catches *that* and re-offers
   fresh availability instead of crashing the turn — verified this
   actually happens gracefully in both a pytest test
   (`test_slot_taken_by_race_reoffers_fresh_slots`) and the live rerun
   (all 8 racing patients landed on 8 *different* slots).
2. **Event-loop blocking.** `web_chat.py`'s websocket handler called the
   synchronous `run_turn()` — which does blocking DB queries and a
   blocking Ollama HTTP call — directly inside `async def`. Under any
   real concurrency this blocks the *entire* event loop long enough that
   other connections' keepalive pings time out; every single connection
   in the first stress run failed with `ConnectionClosedError`. Fixed by
   wrapping the blocking work in `asyncio.to_thread` (both the initial
   session setup and each turn). Applied the same fix to
   `payments_web.py`'s `/pay/{ref}/complete` for consistency, even though
   its blocking window is much smaller (no LLM call there).

**Re-ran after fixing both**: 8/8 race-test bookings succeeded (each
landing on a distinct slot), 15/15 load-test bookings succeeded (p50
5.9s / p95 8.7s, dominated by the 7b model's triage latency, not the
fixes), zero double-bookings, zero server errors. This is what "passes
properly" looked like — the user asked for a stress test specifically
*before* moving to Phase 8, and it's exactly the kind of bug a
CLI-driven or single-browser-tab smoke test would never have surfaced.
34 pytest tests now (4 new, all passing).

If you add more concurrent-write paths later (e.g. Phase 8 voice
sessions, or a future admin dashboard doing bulk operations), re-run
`scripts/stress_test.py` rather than assuming this class of bug can't
recur — the pattern to watch for is any `async def` FastAPI handler that
calls synchronous DB/LLM code without `asyncio.to_thread`.

Environment discovered/changed this session:
- Python 3.14.5 is the system default, but LangGraph/SQLAlchemy/etc. are
  not yet reliably tested on it → using **Python 3.11.15** via `uv venv`
  at `backend/.venv` instead. Use `uv pip install -r requirements.txt
  --python .venv` for all backend deps, and invoke the venv's own
  python/uvicorn/alembic directly (`.venv/Scripts/...` on Windows) rather
  than relying on `python`/`pip` on PATH.
- **`qwen2.5:7b-instruct-q4_K_M` (the pinned model) finished pulling this
  session** after being re-attempted across two sessions total (slow
  connection). `.env`'s `OLLAMA_MODEL` is now set to it, with
  `qwen2.5:3b-instruct` as `OLLAMA_FALLBACK_MODEL`. Re-verified the full
  demo_walkthrough.py loop against it — works, and triage picks
  sensible-if-different departments than the 3b model did (e.g. General
  Medicine instead of Cardiology for "cough and chest tightness" — both
  defensible). `llama3.1:8b-instruct-q4_K_M` (the originally-pinned
  fallback) was never pulled; `qwen2.5:3b-instruct` is standing in for it
  and works fine as a fallback.
- Node v24.16.0, git 2.54.0 available. Docker 29.7.2 + Compose v5.4.0
  available but **still not tested end-to-end** — Dockerfiles exist for
  backend/frontend/whatsapp-gateway and docker-compose.yml wires up all
  four services, but the non-Docker path is what's actually verified.
- `.env` exists locally (gitignored, not committed) — copied from
  `.env.example`. A fresh session/machine needs to re-copy it; recent
  sessions added `APP_BASE_URL` and `SMTP_ENABLED` keys — diff against
  `.env.example` if picking up an old `.env`. `whatsapp-gateway/.env`
  is a **separate** file (also gitignored) — copy from
  `whatsapp-gateway/.env.example` too if running the gateway.
- **`uvicorn --reload` hung mid-reload earlier this session** (one file
  changed, logged "Reloading...", then never restarted — kept serving
  stale code indefinitely with no error). Cost some debugging time before
  it was noticed (routes returned generic 404s instead of the app's
  actual responses). If you use `--reload`, verify routes actually
  changed after an edit (curl something route-specific) rather than
  trusting the log alone.
- Dev servers as of this update (session 3): **backend uvicorn and
  frontend are both running** (:8000, :5173). Backend is running
  `uvicorn app.main:app --port 8000 --ws-max-size 20971520` — no
  `--reload`, and note the `--ws-max-size` flag is now required for the
  voice channel to work (see Phase 8 below); restart manually with that
  flag after further code changes. The WhatsApp gateway (:3001) is
  **stopped** — no real WhatsApp account has been paired against this
  build yet, so `whatsapp-gateway/auth_info/` is still empty and a fresh
  `npm start` will print a QR code needing a real scan.

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

### What's built (Phase 5)

- **Schema**: `AppointmentStatus.pending_payment` (new — booking now lands
  here, not `confirmed`, until payment succeeds). `Doctor.consultation_fee`
  (Numeric, seeded with varied per-doctor values — see
  `scripts/seed_demo_data.py`). Migration
  `24f96d68ea32_add_consultation_fee_and_pending_.py` — autogenerate
  handled the SQLite CHECK-constraint change via batch mode correctly
  this time (Phase 1's migration was hand-written; this one didn't need
  to be). `pending_payment` counts as an "active" status for slot-exclusion
  purposes (`services/doctors.ACTIVE_STATUSES`) so a second patient can't
  grab a slot someone's mid-checkout on.
- **`app/services/payment_providers/`** — the two-backend split:
  `base.py` (ABC: `create_payment_link`, `check_status`), `mock.py` (zero
  network, builds a link to our own `/pay/{reference}` page), `razorpay.py`
  (Payment Links API — **written but unverified, no test Razorpay account
  was available**; the mock path is what's actually been exercised).
- **`app/agents/payments_agent.py`** — `create_payment_link` /
  `confirm_payment`, matching the interface named in the brief. One
  Payment row per Appointment (schema's `unique=True` on
  `appointment_id`); a failed attempt is retried by regenerating the link
  on the same row, not inserting a new one.
- **`app/channels/payments_web.py`** — `GET /pay/{reference}` (mock
  checkout HTML, Paid/Failed buttons) and `POST /pay/{reference}/complete`.
  Only ever serves `provider == "mock"` payments — a real Razorpay link
  points at Razorpay's own hosted checkout instead.
- **Async notification pattern** (new, will be reused by Phase 6's report
  delivery): `app/services/live_connections.py` is an in-memory
  `(channel, external_id) -> websocket` registry, populated by
  `web_chat.py` on connect/disconnect. `app/services/notifications.py`
  splits into a sync DB-persistence half (`queue_message_for_patient` —
  safe to call from anywhere, including standalone scripts) and an async
  `push_live` half (only meaningful inside the FastAPI process). The
  orchestrator's `awaiting_payment_node` is the reconciliation
  counterpart: even if the live push is missed (patient reconnected on a
  different connection, etc.), the *next* message they send re-checks the
  DB and catches up. This same pattern is what Phase 6's report-ready
  notification will reuse.
- **Verified**: pytest (5 new payments_agent tests + updated orchestrator
  tests covering the paid and failed paths, 23 total, all passing);
  manually via curl against the mock checkout page; and — the one that
  actually proves the async design — a `websockets` test script that
  keeps a chat connection open, completes payment via a *separate* HTTP
  call, and confirms the confirmation message arrives on the open
  socket with no user input. Also verified the failure→retry path the
  same way (failed payment pushes a message live, next chat message gets
  a fresh link).
- **`scripts/demo_walkthrough.py`** (new) — scripted, non-interactive
  transcript: greet → symptom → pick slot → pay (mock) → reconcile →
  confirmed. Re-runnable (closes any prior active session for its demo
  phone number first). This is the smoke test for the full booking+pay
  loop; Phase 6 extended it further (see below).

### What's built (Phase 6)

- **`app/services/appointments.py`**: `complete_visit(db, appointment_id,
  notes)` — flips a `confirmed` appointment to `completed` with notes
  attached. Validates the appointment was actually `confirmed` first.
- **`app/agents/report_agent.py`**: `generate_report` renders a one-page
  PDF (reportlab `canvas`, not the heavier `platypus` layout engine — not
  needed for one fixed-field page) to
  `storage/reports/appointment_{id}_report.pdf` and creates/updates the
  Report row. `find_undelivered_report(db, patient_id)` — most recent
  generated-but-`consent_at is None` report for a patient; used by both
  the proactive ask and the reactive "send my report" re-ask path.
- **`app/agents/report_delivery_agent.py`**: `consent_question`,
  `decline_message`, `unclear_answer_message` (text builders) and
  `deliver_report` (records `consent_at`/`delivered_at`/
  `delivery_channel=chat`, builds the `/reports/{id}/download` link,
  attempts an optional email via `app/services/email.py` if
  `SMTP_ENABLED=true` and the patient has an email on file — wrapped in
  try/except so a broken SMTP config never blocks chat delivery, which
  already succeeded by that point). **Email path is unverified** — no
  SMTP account was configured; same honesty caveat as the Razorpay
  provider in Phase 5.
- **`app/doctor_cli.py`** (new, crude-but-real internal tool): lists
  `confirmed` appointments, takes notes, calls `complete_visit` +
  `generate_report`, then persists the consent question + an
  `awaiting_report_consent` state flag via
  `notifications.queue_message_for_patient` (same Phase 5 pattern), and
  best-effort pings a new internal endpoint (below) to live-push it if
  the patient's channel happens to be open right now.
- **`app/channels/internal.py`** (new): `POST
  /internal/push-live/{patient_id}` — lets a separate-process tool
  (doctor_cli) ask the running FastAPI process to do the live websocket
  push on its behalf, since an in-memory registry only exists within one
  process. No auth — local-prototype internal tool only.
- **`app/channels/reports_web.py`** (new): `GET /reports/{id}/download`
  — serves the PDF, 404s unless `consent_at` is set. Manually verified
  the gate: 404 before consent, still 404 after an explicit decline, 200
  once consent is given (including via the keyword re-ask path).
- **Orchestrator**: two new nodes (`report_consent_ask_node`,
  `report_consent_answer_node`) and a state field
  (`awaiting_report_consent: {"report_id": int} | None`). The router
  (`_make_router`, now a db-bound closure — was a plain function before,
  since the report-keyword check needs a DB query) checks, in priority
  order: emergency → `awaiting_report_consent` set → "my report"-style
  keyword match with an actual undelivered report on file → normal
  `stage`-based routing. This means the consent Q&A is fully orthogonal
  to whatever `stage` a patient was already in (mid-booking, done,
  whatever) — it doesn't touch `stage` at all, so the original flow
  resumes untouched once consent is resolved.
- **`app/services/report_requests.py`** (new): deterministic keyword
  match for "send my report" style messages — same rationale as
  `emergency.py` (narrow, safety/UX-adjacent-enough intent, a keyword
  list is more predictable than asking the local LLM).
- **8 new pytest tests** (31 total, all passing): PDF generation +
  idempotent re-run, `find_undelivered_report` filtering, and the full
  consent flow (yes/no/unclear/keyword-re-ask/no-false-positive-without-
  a-report) driven through the real `run_turn()` orchestrator.
- **Manually verified end-to-end twice** against the running server and
  real seeded patients: book → pay → `doctor_cli` completes visit →
  consent asked in chat → PDF downloaded and inspected (correct patient/
  doctor/department/notes) — and separately, the decline → still-gated
  → keyword re-ask → accept → download cycle.
- **`scripts/demo_walkthrough.py`** extended to run the complete loop
  non-interactively (book → pay → doctor completes visit → consent →
  deliver), confirmed re-runnable.

### What's built (Phase 7)

- **`whatsapp-gateway/`** (new top-level service, Node + CommonJS):
  `index.js` uses `@whiskeysockets/baileys` (the actively-maintained
  fork — the plain `baileys` package name is stale/deprecated) with
  `useMultiFileAuthState` for session persistence in `./auth_info/`
  (gitignored). Deliberately minimal deps: no Express — the `/send`
  endpoint is hand-rolled on Node's built-in `http` module, and outbound
  webhook calls use Node 18+'s built-in global `fetch` rather than
  adding axios/node-fetch.
- **Two message flows**, matching the async-notification pattern
  established in Phase 5: **inbound** (WhatsApp message arrives →
  `messages.upsert` → `POST /webhook/whatsapp` on the backend → backend
  runs one orchestrator turn and returns `{reply}` synchronously → relay
  over the same Baileys socket) and **outbound/proactive** (backend
  wants to nudge a patient who isn't mid-message — payment confirmed,
  report ready — via `notifications.push_live`'s new whatsapp branch →
  `POST http://gateway/send {phone, message}` → gateway relays it).
  WhatsApp doesn't fit the websocket-shaped `live_connections` registry
  (there's no per-conversation connection object, just one gateway
  that's either reachable or not), so it's handled as a special case in
  `push_live` instead of being forced into that abstraction.
- **`app/channels/whatsapp_webhook.py`** (new): `POST /webhook/whatsapp`,
  a `{phone, message, secret}` → `{reply}` adapter over the same
  `run_turn()` every channel uses. Rejects on `secret` mismatch (401).
  First-contact handling differs deliberately from web_chat's websocket:
  there's no separate "connect" event to proactively push a greeting
  through, so on a brand-new session it replies with *just* the
  greeting and does not process whatever the patient's actual first
  message said — same semantics as every other channel (their real
  first answer is their *next* message), rather than guessing whether
  their opening "hi" was meant to answer a question they hadn't been
  asked yet.
- **`app/services/whatsapp_client.py`** (new): the outbound half —
  `send_whatsapp_message(phone, text)`, a thin `httpx.post` to the
  gateway's `/send`. Called via `asyncio.to_thread` from
  `notifications.push_live` since it's a blocking call inside an async
  function.
- **A real bug caught and fixed in the gateway itself**: `makeWASocket()`
  returns a socket object synchronously, well before the connection is
  actually authenticated — checking `if (!currentSocket)` to guard the
  `/send` endpoint was wrong, since the object exists immediately but
  calling `.sendMessage()` on it before the connection is actually
  "open" fails deep inside Baileys with an unhelpful
  `Cannot read properties of undefined (reading 'id')` error instead of
  a clean 503. Fixed by tracking a real `isConnected` boolean set from
  the `connection.update` event's `open`/`close` transitions. Caught by
  actually calling the endpoint, not by inspection — worth remembering
  next time something here "looks obviously fine."
- **What's actually been verified** (honest boundary — see "Deviations"):
  the FastAPI webhook side end-to-end against the real backend and DB
  (secret rejection, first-contact greeting-only reply, full
  triage→booking→payment-link flow, all via curl simulating what the
  gateway sends) and the gateway's own HTTP plumbing (`/send`'s 503 when
  unpaired, confirmed correct after the bug fix above; the backend's
  `push_live` correctly calling it and degrading gracefully on failure).
  **The actual Baileys↔WhatsApp connection has never been paired or
  tested against a real account** — that step requires a human scanning
  a QR code with a phone, which no session so far has had available.
  Whoever does this first should watch for: message formatting
  differences (WhatsApp may render the numbered slot list oddly),
  whether `extractText` handles all the message shapes real WhatsApp
  clients send (voice notes, reactions, edits — currently only handles
  plain text/caption), and the reconnect logic on real network drops.
- **docker-compose.yml** now wires up all four services, with
  service-name-based URLs for the container network
  (`WHATSAPP_GATEWAY_URL=http://whatsapp-gateway:3001` etc.) and a
  named volume for `auth_info` persistence. Still unverified like the
  rest of the Docker path.
- No new pytest tests this phase — see the "channel adapters aren't
  pytest-unit-tested" note in Deviations below for why, consistent with
  how `web_chat.py` and `payments_web.py` were already handled.

### What's built (Phase 8, session 3)

- **Stack**: `faster-whisper` for STT (`ctranslate2`-based, no PyTorch
  dependency), `piper-tts` for TTS (`onnxruntime`-based). Both resolved
  cleanly with modest dependency trees — no heavy ML framework needed for
  either. Default config: Whisper `base` model, CPU, `int8` compute type
  (no CUDA toolkit version-matching required — reliable over fast, bump
  `STT_DEVICE=cuda` in `.env` if you have a working ctranslate2 CUDA
  setup); Piper voice `en_US-lessac-medium` (~60MB, downloaded once via
  `python -m piper.download_voices`, cached in `storage/voices/`,
  gitignored). Whisper's own model auto-downloads via `huggingface_hub`
  on first use — no manual step needed for that half.
- **`app/services/speech_to_text.py`** / **`text_to_speech.py`**: thin
  wrappers, each with a module-level singleton model instance (loading
  takes a few seconds, reused across calls — same pattern as
  `OllamaClient` in `web_chat.py`). STT returns `""` for silence rather
  than raising; TTS returns `b""` for empty text. `transcribe()` uses
  `vad_filter=True` (voice activity detection) to reduce hallucinated
  text on quiet/noisy segments — matters more for live mic input than it
  would for clean uploaded audio.
- **`app/agents/voice_agent.py`**: `process_voice_turn()` composes STT →
  the *same* `run_turn()` orchestrator every other channel uses → TTS.
  Returns the transcribed text separately from the reply, not just
  folded into state — the channel surfaces "what was heard" back to the
  UI, since STT errors are common and a voice UI silently misunderstanding
  someone is worse than a text UI where they can see exactly what they
  typed.
- **`app/channels/voice_ws.py`**: `/ws/voice?phone=<phone>`, mirrors
  `web_chat.py`'s structure closely (same `asyncio.to_thread` pattern for
  blocking work, same session load/resume logic). Protocol: server sends
  one JSON text frame per turn (`content`, `heard`, `stage`, `has_audio`)
  immediately followed by a binary frame with the raw WAV reply, when
  there is one. Client sends one binary frame per utterance (push-to-talk
  — the complete recorded clip, whatever format `MediaRecorder` produced;
  faster-whisper decodes via ffmpeg/`av` internally, no client-side
  conversion needed).
- **Real bug found and fixed via actual end-to-end testing**: sending
  audio base64-embedded inside the JSON frame (the original design) hit
  uvicorn's default 1MB websocket frame limit on any reply longer than
  ~15 seconds spoken — the connection died with "message too big" on the
  very first realistic multi-slot triage reply. Fixed two ways: (1)
  switched to a separate binary frame for audio (removes base64's ~33%
  overhead), (2) documented `--ws-max-size 20971520` as part of the
  standard run command (README step 4) and baked it into
  `backend/Dockerfile`'s CMD. This is exactly the same *category* of
  lesson as the stress-test bugs earlier this session: a thing that looks
  fine until you actually push real data through it end-to-end.
- **Frontend**: `frontend/src/VoiceWidget.jsx` (new), a hold-to-talk
  widget using `MediaRecorder`/`getUserMedia`, alongside `ChatWidget` via
  a mode toggle in `App.jsx` (no router added — local `useState`, kept
  it simple). Correlates each JSON metadata frame with the binary audio
  frame that immediately follows it via a ref flag, plays audio through
  a hidden `<audio>` element.
- **Verification — read this before assuming voice "just works" end to
  end**: the actual voice *agent* pipeline (STT → orchestrator → TTS) was
  verified thoroughly and automatically, with no human needed: a test
  script (`voice_ws_test.py`, written to the session scratchpad, not
  committed — reproducible via the pattern in this note) used Piper
  itself to synthesize realistic spoken utterances, sent them through the
  real `/ws/voice` endpoint, and confirmed correct transcription (STT
  reproduced "I have chronic back pain after lifting something heavy"
  essentially verbatim), correct orchestrator behavior (triage → slot
  list → booking, including a session-resume-after-reconnect case that
  came up by accident and worked correctly), and correct large-reply
  audio delivery (a 31-second, 1.37MB WAV reply transmitted successfully
  after the frame-size fix). **What was *not* verified**: an actual human
  speaking into an actual microphone through the browser UI. Attempted
  this directly — clicking "Hold to talk" via browser automation
  triggers Chrome's native `getUserMedia` permission prompt, which lives
  outside the page's DOM and isn't reachable by coordinate-based
  automation (confirmed by the tab hanging exactly when the prompt would
  appear, then reloading on Escape, losing the session — not a bug, just
  the boundary). This is the same category of limitation as Phase 7's
  WhatsApp QR pairing: something only a human can complete. Grant mic
  permission once in the browser and it should work; if it doesn't,
  start debugging from `VoiceWidget.jsx`'s `startRecording()` (does
  `getUserMedia` resolve? does `MediaRecorder` produce non-empty chunks?
  does the `onstop` handler's blob actually reach `ws.send`?) rather than
  assuming the backend is at fault — the backend half is the
  thoroughly-verified half.
- No new pytest tests this phase (same rationale as Phase 7's WhatsApp
  webhook — `voice_ws.py` uses `SessionLocal()` directly like every other
  channel adapter, and the real models are too heavy to load in a fast
  unit-test suite). The verification that exists is the live end-to-end
  test described above, not automated regression coverage — if
  `speech_to_text.py`/`text_to_speech.py`/`voice_agent.py` change later,
  re-run an equivalent live test rather than trusting pytest to catch a
  regression here.

Next up: Phase 9 (admin dashboard) is the nominal next phase, but
building real auth might be worth doing first or alongside it — no JWT/
login system exists anywhere yet, and it's been deferred multiple times
now (see Deviations). Worth explicitly asking the user which they'd
rather have next rather than assuming the numeric phase order still
matches priority.

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
- **CLI REPL doesn't get live payment-confirmation push, by design, not
  oversight.** `payments_web.py`'s live-push (via `live_connections.py`)
  only works within the FastAPI process — the CLI REPL is a separate
  Python process with its own memory, so an in-memory registry can't
  reach it. The DB persistence + `awaiting_payment_node` reconciliation
  path still works correctly for CLI sessions; they just find out on
  their *next* message instead of instantly. Real channels (web chat now,
  WhatsApp/voice later) all run inside the same FastAPI process as the
  payment webhook, so they get the live push. This is why
  `demo_walkthrough.py` explicitly sends one more turn after simulating
  payment, instead of asserting an unprompted push arrived.
- **Razorpay provider is implemented but unverified** — no test-mode
  Razorpay account was available while building this. The interface
  (`create_payment_link`/`check_status`) matches the mock provider
  exactly, so switching `MOCK_PAYMENTS=false` with real test keys
  *should* work without touching `payments_agent.py`, but smoke-test it
  before trusting it — see the docstring in
  `app/services/payment_providers/razorpay.py`.
- **Doctor visit-completion is a CLI script (`doctor_cli.py`), not an
  authenticated endpoint** — the brief offered both options explicitly.
  No JWT/login flow exists anywhere in the app yet (Phase 0-6 never
  needed one), and standing up real auth just to gate this one action
  felt like doing Phase 9's work early, badly. If Phase 9 (admin
  dashboard) lands before this gets revisited, build real auth there and
  retrofit this endpoint at the same time rather than inventing a
  separate half-auth scheme now.
- **Email delivery (`app/services/email.py`) is implemented but
  unverified** — same situation as Razorpay: no SMTP account was
  configured. `SMTP_ENABLED` defaults to `false` and nothing else in the
  app depends on this path.
- **Report consent-ask CAN live-push on the proactive first ask, but only
  via an extra hop.** Unlike a payment (which resolves via an HTTP call
  the FastAPI process itself handles, so it can push directly), a doctor
  completing a visit happens in `doctor_cli.py` — a separate process with
  no access to the in-memory websocket registry. `doctor_cli.py` persists
  the question to the DB directly (guaranteed, works standalone) and then
  best-effort pings `POST /internal/push-live/{patient_id}` (new this
  phase — see `app/channels/internal.py`) so the *running server*, which
  does have registry access, can do the actual push. If the server isn't
  reachable when doctor_cli runs, this silently degrades to "patient sees
  it on their next message" — never a hard failure. The keyword-triggered
  re-ask doesn't need any of this, since it's answered synchronously
  within whatever request/turn triggered it.
- **Channel adapters (`web_chat.py`, `payments_web.py`,
  `whatsapp_webhook.py`) aren't pytest-unit-tested.** They all use
  `SessionLocal()` directly rather than FastAPI's `Depends(get_db)`
  pattern, which was the right call for a single-user local prototype
  (no request-scoped session lifecycle complexity needed) but means a
  `TestClient` would hit the real dev DB, not an isolated test one —
  wrong for unit tests. The actual logic they call (`run_turn`, every
  agent) is thoroughly covered; these are deliberately thin,
  verified-by-actually-running-them adapters instead. If this app ever
  needs proper endpoint-level tests, that's the point to introduce
  `Depends(get_db)` + a test-DB override — don't bolt on a parallel
  testing scheme without also fixing the underlying DB-access pattern.
- **WhatsApp gateway has never touched a real WhatsApp account.**
  Everything up to the Baileys↔WhatsApp boundary is verified (see "What's
  built (Phase 7)" above); the actual pairing requires a human with a
  phone, which no session has had. Treat the gateway as "should work,
  unverified past that specific boundary" rather than "done."
- **Auth/JWT has now been deferred twice** (Phase 5's payments and Phase
  6's report-completion both explicitly chose not to build it). This is
  still the right call — building real auth for one gated action each
  time is worse than building it once, properly, when something actually
  needs a full login system (Phase 9's admin dashboard is the obvious
  trigger). But it's worth flagging explicitly rather than let it become
  an implicit assumption: **there is currently no user authentication
  anywhere in this app.** `doctor_cli.py` and the `/internal/*` and
  `/reports/{id}/download` endpoints all trust the caller.
- **Concurrency bugs (double-booking race, event-loop blocking) were only
  found by an explicit stress test, not by any of the prior manual/CLI
  smoke testing.** See "Stress test findings" in STATUS above for the
  full writeup — kept brief here as a pointer: every prior session's
  testing was single-connection, sequential, so neither bug had a chance
  to show up. Any future channel or endpoint that does DB writes from an
  `async def` handler needs the same `asyncio.to_thread` treatment on
  its blocking calls, and any future "check then insert" pattern against
  a resource with real contention (slots, but potentially other things
  later) needs to ask whether it needs the same DB-level constraint
  treatment `Appointment.__table_args__` got here.
- **Voice's microphone permission is a human-only step, structurally
  identical to Phase 7's WhatsApp QR pairing.** Confirmed by actually
  attempting it via browser automation, not assumed: clicking "Hold to
  talk" triggers Chrome's native `getUserMedia` prompt, which lives
  outside the page DOM and isn't reachable by coordinate/ref-based
  automation. Don't burn time trying to script around this again — grant
  the permission once by hand and move on. The backend voice pipeline
  itself (STT → orchestrator → TTS) is thoroughly verified independent
  of this; see "What's built (Phase 8)" above for exactly what was and
  wasn't tested.
