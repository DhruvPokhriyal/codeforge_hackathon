# 📁 Project Structure
## Offline Emergency Intelligence Hub — Electron + FastAPI

---

## Full Folder Tree

```
emergency-hub/
│
├── package.json                         # Electron config + npm scripts
├── requirements.txt                     # All Python dependencies
├── .gitignore
│
├── electron/
│   ├── main.js                          # Electron main process
│   │                                    #   · spawn('python', ['backend/main.py'])
│   │                                    #   · poll GET /health until 200 OK
│   │                                    #   · createBrowserWindow()
│   │                                    #   · kill backend on app.quit
│   └── preload.js                       # contextBridge IPC layer
│                                        #   exposes: runPipeline, approveReport,
│                                        #   volunteerReturn, getQueue, getVolunteers,
│                                        #   getInventory
│
├── frontend/
│   ├── index.html                       # App shell — 3-panel dashboard layout
│   ├── app.js                           # All UI logic:
│   │                                    #   · audio upload + base64 encoding
│   │                                    #   · POST /pipeline → render HITL report
│   │                                    #   · HITL approval: situation card selection,
│   │                                    #     greyed-out items, manual override
│   │                                    #   · POST /approve → dispatch
│   │                                    #   · Live countdown timers per volunteer
│   │                                    #   · "Back at Base" button + return popup
│   │                                    #   · POST /volunteer/return
│   │                                    #   · 3s polling: GET /queue, /volunteers, /inventory
│   └── styles.css                       # High-contrast dark emergency theme
│                                        #   CSS vars: --critical, --high, --medium, --low
│                                        #   .greyed-out for unavailable items
│                                        #   .timer.overdue for negative countdown
│
├── backend/
│   │
│   ├── main.py                          # FastAPI app init + Uvicorn entry point
│   │                                    #   · Binds 127.0.0.1:8000 only
│   │                                    #   · Registers all routers
│   │                                    #   · On startup: loads all models,
│   │                                    #     builds LlamaIndex, starts APScheduler
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── pipeline.py                  # POST /pipeline
│   │   │                                #   Steps: denoise → STT → retrieve →
│   │   │                                #   (vagueness?) → rag_triage → inventory check
│   │   │                                #   Returns: multi-situation report JSON
│   │   ├── approve.py                   # POST /approve
│   │   │                                #   Receives selected situation indices
│   │   │                                #   Reserves inventory items
│   │   │                                #   Pushes request to heap
│   │   │                                #   Triggers dispatch
│   │   ├── queue.py                     # GET /queue — heap-sorted request list
│   │   ├── volunteers.py                # GET /volunteers — all statuses + timers
│   │   ├── volunteer_return.py          # POST /volunteer/return
│   │   │                                #   Receives returned items checklist
│   │   │                                #   Restores items to inventory
│   │   │                                #   Marks volunteer AVAILABLE
│   │   │                                #   Re-runs dispatch
│   │   └── inventory.py                 # GET /inventory · PUT /inventory/refill
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── denoiser.py                  # STEP 2: Audio denoising
│   │   │                                #   · Option A: noisereduce (stationary, 85%)
│   │   │                                #   · Option B: Facebook Denoiser (dns64)
│   │   │                                #   · Config flag: DENOISER = "noisereduce"|"facebook"
│   │   ├── intake_agent.py              # STEP 3: Whisper base, fp16=False (CPU only)
│   │   ├── retrieval_agent.py           # STEP 4: LlamaIndex retrieval
│   │   │                                #   · Returns top-k chunks + confidence scores
│   │   │                                #   · Sets is_vague flag if top_score < 0.8
│   │   ├── vagueness_agent.py           # STEP 4b: SLM hypothesis expansion
│   │   │                                #   · Generates 2-3 conditions per severity level
│   │   │                                #   · Retries retrieval for each hypothesis
│   │   │                                #   · Merges and deduplicates chunks
│   │   ├── rag_triage_agent.py          # STEP 5: RAG SLM + Triage
│   │   │                                #   · Reads transcript + retrieved chunks
│   │   │                                #   · Outputs multi-situation JSON array
│   │   │                                #   · Each situation: label, severity, score,
│   │   │                                #     travel_time, resolution_time, materials,
│   │   │                                #     instructions, reasoning, source_chunks
│   │   │                                #   · Computes heap_key per situation
│   │   └── logistics_agent.py           # STEP 6: Inventory availability annotation
│   │                                    #   · fuzzy-matches each material to CSV
│   │                                    #   · annotates available/available_qty/bin
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── priority_queue.py            # Max-heap
│   │   │                                #   · Key: (-heap_key, timestamp, req_id)
│   │   │                                #   · push(), peek_top_pending(), get_sorted()
│   │   │                                #   · update_key() — rebuilds heap (no decrease-key)
│   │   │                                #   · Singleton shared across all routers
│   │   ├── dispatch_engine.py           # Volunteer assignment scheduler
│   │   │                                #   · VOLUNTEERS dict: V-01 to V-06
│   │   │                                #   · dispatch(): assign free vol to top PENDING
│   │   │                                #   · volunteer_return(): restore items, re-dispatch
│   │   │                                #   · Timer expected_return = travel + resolution
│   │   │                                #   · Timer freezes at 0 — no auto-reassign
│   │   ├── escalation_scheduler.py      # APScheduler background job
│   │   │                                #   · Runs every 60 seconds
│   │   │                                #   · Checks all PENDING tasks
│   │   │                                #   · Applies exponential urgency boost per schedule
│   │   │                                #   · Adds buffer = f(travel, resolution) at each step
│   │   │                                #   · Calls queue.update_key()
│   │   └── request_store.py             # In-memory request registry
│   │                                    #   · request_id → full request dict
│   │                                    #   · filter_by_status(status)
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                    # Structured JSON handoff logger
│       │                                #   · log_handoff(from, to, reason, payload)
│       │                                #   · Appends to logs/handoffs.jsonl
│       ├── audio_utils.py               # save_base64_wav() · cleanup_temp()
│       └── inventory_manager.py         # InventoryManager class
│                                        #   · reserve(item, qty) — decrements Available
│                                        #   · restore(item, qty) — increments Available
│                                        #   · daily_refill() — full reset at midnight
│                                        #   · partial_refill() — refill items ≤ 60%
│
├── data/
│   ├── inventory.csv                    # Item | Available | Reserved | Total | Bin Location | Category
│   └── protocols/                       # Offline PDF knowledge base
│       ├── first_aid_manual.pdf         # Primary reference (St. John / WHO)
│       ├── trauma_guide.pdf
│       └── disaster_response.pdf
│
├── models/
│   └── gemma-3-1b-it-Q5_K_M.gguf           # Gemma 3 1B GGUF model
│
├── vector_store/                        # Auto-built by LlamaIndex on first run
│   └── (index files)                    # Rebuilt from /data/protocols/ if deleted
│
├── logs/
│   └── handoffs.jsonl                   # Append-only structured agent handoff log
│
├── temp/                                # REQ-XXX_raw.wav · REQ-XXX_clean.wav
│   └── .gitkeep                         # Cleared each session
│
└── scripts/
    └── download_models.py               # One-command model download script
```

---

## Data Flow Between Files

### Inbound Request (Audio → HITL Report)
```
frontend/app.js
    │  POST /pipeline {audio_base64}
    ▼
backend/routers/pipeline.py
    │
    ├── agents/denoiser.py          raw.wav → clean.wav
    ├── agents/intake_agent.py      clean.wav → transcript
    ├── agents/retrieval_agent.py   transcript → {chunks, is_vague, top_score}
    │       ├─ is_vague=True ──→ agents/vagueness_agent.py → expanded chunks
    │       └─ is_vague=False ─→ original chunks
    ├── agents/rag_triage_agent.py  chunks + transcript → situations[]
    ├── agents/logistics_agent.py   situations[] → annotated with availability
    │
    └── Return: {request_id, situations[], retrieval_was_vague, source_chunks}
    │
    ▼
frontend/app.js
    renderHITLReport(situations)
```

### Manager Approval (HITL → Heap)
```
frontend/app.js
    │  POST /approve {request_id, selected_indices, manual_override?}
    ▼
backend/routers/approve.py
    ├── utils/inventory_manager.py   reserve items for selected situations
    ├── core/priority_queue.py       push(request) with heap_key
    ├── core/dispatch_engine.py      dispatch(queue) → assign volunteer
    │
    └── Return: {queue[], volunteers[]}
```

### Volunteer Return Flow
```
frontend/app.js  [Back at Base button → popup checklist]
    │  POST /volunteer/return {volunteer_id, returned_items[]}
    ▼
backend/routers/volunteer_return.py
    ├── utils/inventory_manager.py   restore(item, qty) for each returned item
    ├── core/dispatch_engine.py      volunteer_return() → mark AVAILABLE
    ├── core/dispatch_engine.py      dispatch(queue) → check next pending task
    │
    └── Return: {freed_volunteer, queue[], volunteers[], inventory[]}
```

### Background Escalation (Every 60s)
```
core/escalation_scheduler.py  (APScheduler job)
    │
    ├── core/priority_queue.py   get_sorted() → all PENDING requests
    ├── [compute hours_wait, match escalation schedule]
    └── core/priority_queue.py   update_key(request_id, new_key)
```

---

## Inventory CSV Format

```csv
Item,Available,Reserved,Total,Bin Location,Category
Leg Splint,4,0,4,A-1,Medical
AED,2,0,2,C-3,Medical
CPR Mask,5,0,5,A-4,Medical
Bandages,50,0,50,A-2,Medical
Tourniquets,10,0,10,A-1,Medical
Water Bottles,200,0,200,B-3,Resources
Energy Bars,150,0,150,B-1,Resources
Blankets,30,0,30,C-1,Comfort
Flashlights,15,0,15,D-2,Equipment
```

---

## .gitignore

```gitignore
models/*.gguf
models/*.bin
vector_store/
temp/*.wav
temp/*.mp3
logs/*.jsonl
__pycache__/
*.pyc
venv/
.env
node_modules/
dist/
.DS_Store
```