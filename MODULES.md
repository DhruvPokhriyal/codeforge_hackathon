# 📦 Modules — Team Division
## Offline Emergency Intelligence Hub

> Three independent groups, each owning a coherent slice of the system.
> Similar modules are grouped together so each team can build, run, and test
> their slice **without waiting on other groups**.

---

## Shared Contract File  ← read by ALL groups

| File | Purpose |
|------|---------|
| `backend/schemas.py` | Pydantic models for every request body, response, and domain object |
| `backend/config.py`  | All feature flags, file paths, and tunable constants |

> **Rule:** Never define schemas inline in routers or agents.
> Always import from `schemas.py`. Never hard-code paths — import from `config.py`.

---

## Group 1 — Audio & AI Pipeline 🤖

**Owns:** `backend/agents/` · `backend/utils/audio_utils.py` · `backend/tests/`

These are pure-function modules: given inputs, they produce outputs with no shared state.
Each agent can be run and tested in isolation.

| File | Step | Description |
|------|------|-------------|
| `backend/agents/denoiser.py` | 2 | Audio denoising (noisereduce OR Facebook DNS64) |
| `backend/agents/intake_agent.py` | 3 | Whisper base STT — clean WAV → transcript string |
| `backend/agents/retrieval_agent.py` | 4 | LlamaIndex RAG — transcript → top-k chunks + confidence |
| `backend/agents/vagueness_agent.py` | 4b | LLM hypothesis expansion when `top_score < 0.8` |
| `backend/agents/rag_triage_agent.py` | 5 | Gemma 3 1B — chunks + transcript → multi-situation JSON |
| `backend/agents/logistics_agent.py` | 6 | Fuzzy inventory check — annotates each material with availability |
| `backend/utils/audio_utils.py` | — | `save_base64_wav()` · `get_clean_path()` · `cleanup_temp()` |
| `backend/agents/__init__.py` | — | Public interface — re-exports all agent functions |
| `backend/tests/test_denoiser.py` | — | Denoiser benchmark tool (noisy_input → denoised_output) |

**Independence checklist:**
- [ ] Set `DENOISER` flag in `config.py` (start with `noisereduce`, benchmark vs `facebook`)
- [ ] Place test `.wav` files in `backend/tests/noisy_input/`
- [ ] Place PDFs in `backend/data/protocols/` (required for retrieval_agent)
- [ ] Download model to `backend/models/` (required for vagueness + rag_triage)
- [ ] Test each agent as a standalone function:
  ```python
  # Example: test intake agent
  from backend.agents.intake_agent import transcribe
  print(transcribe("backend/tests/noisy_input/sample.wav"))
  ```

**Dependency flow (inbound only):**
```
config.py  ──→  denoiser, intake_agent, retrieval_agent
schemas.py ──→  (read types for function return shapes)
data/protocols/ → retrieval_agent (PDF index)
data/inventory.csv → logistics_agent
models/*.gguf → vagueness_agent, rag_triage_agent
```

---

## Group 2 — Core Operations & API ⚙️

**Owns:** `backend/core/` · `backend/utils/inventory_manager.py` · `backend/utils/logger.py` · `backend/routers/` · `backend/main.py`

These modules manage application state (heap, volunteers, inventory) and expose the REST API.

| File | Description |
|------|-------------|
| `backend/core/priority_queue.py` | Max-heap with `push`, `peek_top_pending`, `get_sorted`, `update_key` |
| `backend/core/request_store.py` | In-memory request registry (add, get, update, filter_by_status) |
| `backend/core/dispatch_engine.py` | Volunteer state machine — AVAILABLE → BUSY + `dispatch()` + `volunteer_return()` |
| `backend/core/escalation_scheduler.py` | APScheduler background job — urgency boost every 60s |
| `backend/core/__init__.py` | Exports singletons: `priority_queue`, `request_store`, `VOLUNTEERS` |
| `backend/utils/inventory_manager.py` | `InventoryManager` — `reserve`, `restore`, `daily_refill`, `partial_refill` |
| `backend/utils/logger.py` | `log_handoff()` — structured JSON append to `logs/handoffs.jsonl` |
| `backend/routers/pipeline.py` | `POST /pipeline` — orchestrates all Group 1 agents |
| `backend/routers/approve.py` | `POST /approve` — HITL selection → reserve inventory → push to heap → dispatch |
| `backend/routers/queue.py` | `GET /queue` — live heap-sorted list |
| `backend/routers/volunteers.py` | `GET /volunteers` — all statuses + timers |
| `backend/routers/volunteer_return.py` | `POST /volunteer/return` — restore items, mark available, re-dispatch |
| `backend/routers/inventory.py` | `GET /inventory` · `PUT /inventory/refill` |
| `backend/main.py` | FastAPI app — startup, router registration, Uvicorn entry |

**Independence checklist:**
- [ ] Core modules (`priority_queue`, `dispatch_engine`, `request_store`) have zero agent imports
- [ ] Test queue/dispatch logic by mocking agent calls:
  ```python
  # Example: test heap logic without running LLM
  from backend.core.priority_queue import PriorityQueue
  pq = PriorityQueue()
  pq.push({"request_id": "R1", "heap_key": 70, "time_of_request": "2026-01-01T00:00:00", "status": "PENDING", "situations": []})
  assert pq.peek_top_pending()["request_id"] == "R1"
  ```
- [ ] Run the full API server with stub agents using `uvicorn backend.main:app`
- [ ] Use `GET /health` to confirm the backend is alive before integrating with frontend

**Dependency flow (inbound only):**
```
config.py  ──→  all modules
schemas.py ──→  routers (request/response validation)
agents/    ──→  routers/pipeline.py only (call agents here, never in core/)
core/      ──→  routers (import singletons from core/__init__.py)
utils/inventory_manager.py ──→  routers/approve.py, volunteer_return.py
```

---

## Group 3 — Frontend & Electron UI 🖥️

**Owns:** `frontend/`

Electron shell + all HTML/CSS/JS. Communicates with the backend exclusively via `window.api`
(contextBridge — defined in `electron/preload.js`). No Python knowledge required.

| File | Description |
|------|-------------|
| `frontend/electron/main.js` | Electron main: spawn backend, poll `/health`, create window, kill on quit |
| `frontend/electron/preload.js` | contextBridge — exposes `window.api.*` HTTP methods to renderer |
| `frontend/index.html` | 3-panel dashboard shell (Input, Queue, Volunteers, Inventory) |
| `frontend/app.js` | All renderer logic: upload, HITL, timers, polling, return modal |
| `frontend/styles.css` | High-contrast dark emergency theme (CSS vars for severity colours) |
| `frontend/package.json` | Electron config + npm scripts |

**Independence checklist:**
- [ ] `npm install` in `frontend/`
- [ ] Develop UI against a mock FastAPI server (return hardcoded JSON from `/pipeline`, `/queue`, etc.)
- [ ] `npm start` to launch Electron once backend is running
- [ ] Test `window.api` calls in DevTools console:
  ```js
  window.api.getQueue().then(console.log)
  window.api.getVolunteers().then(console.log)
  ```

**window.api contract (from preload.js):**
```
window.api.runPipeline(audio_b64)                    → POST /pipeline
window.api.approveReport(req_id, indices, override?) → POST /approve
window.api.volunteerReturn(vol_id, items)            → POST /volunteer/return
window.api.getQueue()                                → GET /queue
window.api.getVolunteers()                           → GET /volunteers
window.api.getInventory()                            → GET /inventory
```

**Dependency flow (outbound only):**
```
frontend/app.js → window.api.* (preload) → HTTP 127.0.0.1:8000 → FastAPI (Group 2)
```

---

## Integration Sequence

```
Phase 1 (parallel):
  Group 1 → implement + test each agent function independently
  Group 2 → implement + test core heap/dispatch/routers with mock agents
  Group 3 → implement + test all UI panels against mock API responses

Phase 2 (connect Group 1 + Group 2):
  Group 2 updates routers/pipeline.py to call real Group 1 agents
  Full backend test: POST /pipeline with a real audio file

Phase 3 (connect Group 3):
  Group 3 points Electron at the live FastAPI backend
  End-to-end test: audio file → HITL approval → dispatch → return
```

---

## Module Dependency Map

```
backend/config.py  ─────────────────────────→  ALL modules
backend/schemas.py ─────────────────────────→  ALL routers + agents (import types)
                                                          │
                    ┌──────────────────────────────────────────────────────┐
                    │             FASTAPI (127.0.0.1:8000)                 │
                    │                                                      │
              Group 2: core + routers             Group 1: agents         │
              ├─ priority_queue.py           ←   pipeline.py calls        │
              ├─ dispatch_engine.py          ←   approve.py calls         │
              ├─ request_store.py            ←   pipeline.py calls        │
              ├─ escalation_scheduler.py     ←   main.py starts           │
              ├─ inventory_manager.py        ←   approve.py, return.py    │
              └─ logger.py                  ←   pipeline.py calls         │
                    │                                                      │
              Group 3: frontend → window.api  →  HTTP →  Group 2 routers  │
                    └──────────────────────────────────────────────────────┘
```
