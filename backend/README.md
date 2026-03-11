## Backend — Offline Emergency Intelligence Hub

This directory contains the FastAPI backend for the Offline Emergency Intelligence Hub.  
It exposes a REST API that orchestrates the audio → AI triage → inventory → volunteer dispatch pipeline and is designed to run fully offline.

---

## 1. Quick Start

### 1.1. Create and activate a virtualenv

```bash
python -m venv .venv
.venv\Scripts\activate  # on Windows
# source .venv/bin/activate  # on macOS/Linux
```

### 1.2. Install dependencies

The project uses `pyproject.toml` / Poetry, but you can also install directly:

```bash
pip install -r requirements.txt
```

If you are using Poetry:

```bash
poetry install
```

### 1.3. Download models & prepare data

1. **LLaMA model**  
   Place a `Llama-3.2-3B-Instruct-Q4_K_M.gguf` (or compatible) file in:

   ```text
   backend/models/
   ```

   The default path is configured in `config.py`:

   ```python
   LLAMA_MODEL_PATH = MODELS_DIR / "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
   ```

2. **Protocol PDFs (for RAG)**  
   Put emergency manuals and protocols in:

   ```text
   backend/data/protocols/*.pdf
   ```

3. **Inventory CSV**  
   Ensure `backend/data/inventory.csv` exists. A sample format is documented in `PROJECT_STRUCTURE.md`.

### 1.4. Run the backend

From the `backend/` directory:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

On startup:

- PDFs in `data/protocols/` are indexed by LlamaIndex.
- The escalation scheduler for the priority queue is started.
- The health endpoint `/health` becomes available for the Electron app.

---

## 2. Main Modules

### 2.1. Entry point

- `main.py`  
  Creates the FastAPI app, registers routers, builds the vector index on startup, and starts the APScheduler escalation job.

### 2.2. Configuration

- `config.py`  
  Central place for:
  - paths (`DATA_DIR`, `PROTOCOLS_DIR`, `INVENTORY_CSV`, `MODELS_DIR`, …)
  - model settings (`WHISPER_MODEL`, `EMBED_MODEL`, `LLAMA_MODEL_PATH`, …)
  - API host/port
  - volunteer settings and escalation interval.

---

## 3. Agents (Group 1)

Located in `agents/` — all are pure-function style modules:

- `denoiser.py` — STEP 2: audio denoising (configurable: `"noisereduce"` or `"facebook"`).
- `intake_agent.py` — STEP 3: Whisper STT (`transcribe()`).
- `retrieval_agent.py` — STEP 4: LlamaIndex retrieval (`build_index()`, `retrieve()`).
- `vagueness_agent.py` — STEP 4b: hypothesis expansion when retrieval is low-confidence.
- `rag_triage_agent.py` — STEP 5: RAG + LLaMA triage to multi-situation JSON.
- `logistics_agent.py` — STEP 6: annotate situations with inventory availability.
- `agents/__init__.py` — re-exports all public agent functions for easy import.

These are **stateless** and can be tested in isolation.

---

## 4. Core & Routers (Group 2)

### 4.1. Core state and scheduling (`core/`)

- `priority_queue.py`  
  Max-heap of emergency requests (singleton `priority_queue`) with:
  - `push`, `peek_top_pending`, `get_sorted`, `update_key`, `update`.

- `request_store.py`  
  In-memory registry for all requests (singleton `request_store`).

- `dispatch_engine.py`  
  Volunteer state machine:
  - `VOLUNTEERS` dict (`V-01` …),
  - `dispatch(queue)` to assign highest-priority pending request,
  - `volunteer_return(...)` to mark volunteers available and re-dispatch.

- `escalation_scheduler.py`  
  APScheduler job that:
  - runs every `ESCALATION_INTERVAL_SECS` (default 60s),
  - boosts `heap_key` based on severity + waiting time.

- `core/__init__.py`  
  Exports the shared singletons and functions (`priority_queue`, `request_store`, `VOLUNTEERS`, `dispatch`, `volunteer_return`, `get_free_volunteer`).

### 4.2. Routers (`routers/`)

All routers use Pydantic models from `schemas.py` for request/response validation:

- `pipeline.py`
  - `POST /pipeline`  
    Full pipeline: base64 audio → denoise → STT → retrieval (+vagueness if needed) → triage → logistics.  
    Stores a PENDING request in `request_store`, returns the multi-situation report.

- `approve.py`
  - `POST /approve`  
    HITL manager selects situations + optional manual override:
    - marks selected situations,
    - reserves items via `InventoryManager`,
    - computes/updates heap key,
    - pushes to `priority_queue` and calls `dispatch(...)`,
    - returns updated queue + volunteers.

- `queue.py`
  - `GET /queue`  
    Returns the current heap-sorted request list.

- `volunteers.py`
  - `GET /volunteers`  
    Returns the `VOLUNTEERS` state for the dashboard.

- `volunteer_return.py`
  - `POST /volunteer/return`  
    Marks a volunteer as back at base, restores returned items to inventory, updates the request to `RESOLVED`, then re-runs `dispatch(...)`.

- `inventory.py`
  - `GET /inventory` — full inventory view.
  - `PUT /inventory/refill` — manual daily or partial refill.

---

## 5. Utilities & Data

- `utils/audio_utils.py`  
  - `save_base64_wav()` — decodes base64 audio and writes `REQ-XXX_raw.wav`.
  - `get_clean_path()` — path for `REQ-XXX_clean.wav`.
  - `cleanup_temp()` — removes temp audio files after processing.

- `utils/inventory_manager.py`  
  `InventoryManager` encapsulates all `inventory.csv` reads/writes:
  - `reserve`, `restore`, `daily_refill`, `partial_refill`, `get_all`.

- `utils/logger.py`  
  - `log_handoff()` appends structured events to `logs/handoffs.jsonl`.

- `data/`  
  - `inventory.csv` — current stock levels.
  - `protocols/` — PDFs used by LlamaIndex.

---

## 6. Testing & Manual Checks

With the backend running on `127.0.0.1:8000`:

- **Health check**

```bash
curl http://127.0.0.1:8000/health
```

- **Queue**

```bash
curl http://127.0.0.1:8000/queue
```

- **Volunteers**

```bash
curl http://127.0.0.1:8000/volunteers
```

To test the full audio pipeline, send a base64-encoded WAV to `POST /pipeline` (the Electron frontend does this via `window.api.runPipeline(audio_b64)`).

---

## 7. Design Rules (Important)

- All shared config lives in `config.py` (no hard-coded paths).
- All request/response schemas live in `schemas.py` (no inline Pydantic models in routers).
- Core modules (`core/*`) must **never** import agents; only routers may call agents.
- Agents are pure functions; they should be easy to unit-test independently.

