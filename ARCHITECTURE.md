# 🏗️ System Architecture
## Offline Emergency Intelligence Hub — Electron + FastAPI

---

## Stack at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                   ELECTRON SHELL (Frontend)                     │
│         Dashboard UI · HITL Approval · Volunteer Timers         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP (127.0.0.1 only)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FASTAPI BACKEND (Python)                       │
│              Uvicorn ASGI · 127.0.0.1:8000                      │
└───┬──────────┬──────────┬────────────┬────────────┬────────────┘
    │          │          │            │            │
Agents      Agents     Agents       Core          Core
(audio)    (RAG)      (triage)    (heap)       (dispatch)
```

---

## Complete System Architecture

```
ELECTRON MAIN PROCESS (electron/main.js)
  │
  ├─ spawn Python backend/main.py
  ├─ poll GET /health every 500ms → wait for 200 OK
  ├─ createBrowserWindow() → load frontend/index.html
  └─ kill backend on app.quit

PRELOAD (electron/preload.js)
  └─ contextBridge exposes:
       window.api.runPipeline(audio_b64)
       window.api.approveReport(request_id, selected_indices)
       window.api.volunteerReturn(volunteer_id, returned_items)
       window.api.getQueue()
       window.api.getVolunteers()
       window.api.getInventory()

RENDERER (frontend/)
  ┌─────────────────────────────────────────────────────────────┐
  │ Input Panel                                                 │
  │   Upload audio file → base64 → POST /pipeline              │
  ├─────────────────────────────────────────────────────────────┤
  │ HITL Report Panel (appears after /pipeline returns)         │
  │   Situation cards (1 per possible diagnosis)                │
  │   Each card: severity · confidence · materials checklist    │
  │   Items greyed-out if unavailable in inventory              │
  │   Source PDF chunks shown (explainability)                  │
  │   Manager selects ≥ 1 situations → POST /approve           │
  │   OR manual override → custom condition + items             │
  ├─────────────────────────────────────────────────────────────┤
  │ Panel A — Priority Queue (auto-refresh 3s)                  │
  │   Heap-sorted · REQ-ID · Severity · Volunteer               │
  │   Countdown timer · [Back at Base] button                   │
  ├─────────────────────────────────────────────────────────────┤
  │ Panel B — Volunteer Activity Board                          │
  │   All volunteers · status · live countdown timer            │
  │   Items taken per volunteer                                 │
  ├─────────────────────────────────────────────────────────────┤
  │ Panel C — Inventory                                         │
  │   Item · Available · Reserved · Total · Bin · Refill status │
  └─────────────────────────────────────────────────────────────┘

FASTAPI (127.0.0.1:8000)
  │
  POST /pipeline
    │
    ├─ agents/denoiser.py
    │    noisereduce OR facebook dns64 (config flag)
    │    raw.wav → clean.wav
    │
    ├─ agents/intake_agent.py
    │    Whisper base · fp16=False
    │    clean.wav → transcript string
    │
    ├─ agents/retrieval_agent.py
    │    LlamaIndex + all-MiniLM-L6-v2
    │    transcript → top-k chunks + confidence scores
    │    is_vague = (top_score < 0.8)
    │         │
    │    is_vague=True ──→ agents/vagueness_agent.py
    │         │              LLaMA 3.2 3B
    │         │              generate hypotheses per severity level
    │         │              retry retrieval per hypothesis
    │         │              merge + deduplicate chunks
    │         │
    │    is_vague=False ─→ proceed with original chunks
    │
    ├─ agents/rag_triage_agent.py
    │    LLaMA 3.2 3B
    │    transcript + chunks → situations[] JSON array
    │    Each situation: label · severity · severity_score
    │                    travel_time · resolution_time
    │                    heap_key = score - (travel×2) - resolution
    │                    materials · instructions · source_chunks
    │
    ├─ agents/logistics_agent.py
    │    pandas + rapidfuzz
    │    For each situation's materials → check availability
    │    Annotate: available (bool) · available_qty · bin
    │
    └─ Return: {request_id, situations[], is_vague, handoff_logs}

  POST /approve {request_id, selected_indices}
    │
    ├─ utils/inventory_manager.py  reserve items for selected situations
    ├─ core/priority_queue.py      push request (heap_key of top situation)
    ├─ core/dispatch_engine.py     dispatch() → assign free volunteer
    └─ Return: {queue[], volunteers[]}

  POST /volunteer/return {volunteer_id, returned_items[]}
    │
    ├─ utils/inventory_manager.py  restore(item, qty) for each returned
    ├─ core/dispatch_engine.py     volunteer_return() → AVAILABLE
    ├─ core/dispatch_engine.py     dispatch() → check next pending
    └─ Return: {freed_volunteer, queue[], volunteers[], inventory[]}

  BACKGROUND (APScheduler — every 60s)
    core/escalation_scheduler.py
      For each PENDING request:
        hours_wait = now - time_of_request
        schedule   = ESCALATION_SCHEDULE[severity]
        boost      = cumulative key increase for current hours_wait
        buffer     = f(travel_time, resolution_time) × multiplier
        new_key    = base_heap_key + boost + buffer
        queue.update_key(request_id, new_key)
```

---

## Heap Key Design

```
heap_key = severity_score - (travel_time_min × 2) - resolution_time_min

Example:
  CRITICAL fracture, 5min travel, 20min resolution:
  key = 100 - (5×2) - 20 = 70

  LOW food need, 3min travel, 5min resolution:
  key = 25 - (3×2) - 5 = 14

Over time (escalation):
  LOW food need after 6 hours:
  key = 14 + 5 (boost) + buffer = ~22

  LOW food need after 15 hours:
  key = 14 + 100 (boost) + buffer = ~120   ← now above CRITICAL!
```

---

## Vague Query Resolution Flow

```
Transcript: "uncle not moving, legs look wrong"
                  │
    Retrieval → top_score = 0.43  ←  VAGUE (< 0.8)
                  │
    LLM generates hypotheses:
      CRITICAL: ["cardiac arrest", "stroke"]
      HIGH:     ["femur fracture with shock", "spinal injury"]
      MEDIUM:   ["seizure", "diabetic episode"]
      LOW:      ["exhaustion", "dehydration"]
                  │
    Retry retrieval for each hypothesis (top-k=3 each)
    Merge + deduplicate all returned chunks (keep top 10 by score)
                  │
    RAG LLM generates report with ALL plausible situations listed
    Each situation has individual confidence score
```

---

## Volunteer Timer State Machine

```
  AVAILABLE
      │
      │ dispatch() called, free vol found
      ▼
  BUSY
    └── timer countdown: travel_time + resolution_time
    └── expected_return displayed on dashboard

  Timer hits 0:00
      │
      ▼
  OVERDUE (timer goes negative, displayed in red)
      │
      │  ← does NOT auto-reassign
      │  ← waits for shelter head action
      │
  Shelter head clicks "Back at Base"
      │
      ▼
  Return Popup (checklist of items taken)
  Manager ticks returned items
      │
      ▼
  Returned items → inventory_manager.restore()
  Volunteer → AVAILABLE
  dispatch() re-runs immediately
```

---

## Inventory State Machine

```
ITEM LIFECYCLE:

  Total (fixed)
    │
    ├─ Available (starts = Total)
    │     │
    │     ├─ HITL Approve → reserve(item, qty)
    │     │     Available -= qty
    │     │     Reserved  += qty
    │     │
    │     └─ Volunteer Returns → restore(item, qty)
    │           Available += qty
    │           Reserved  -= qty
    │
    └─ Daily Refill (midnight)
          Available = Total
          Reserved  = 0

  Low Stock Alert: Available / Total ≤ 0.60
  → Flag shown on inventory panel
  → partial_refill() can be triggered manually
```

---

## API Contract

### POST `/pipeline`
```
Request:  { "audio_base64": "...", "text_input": "..." }
Response: {
  "request_id":          "REQ-007",
  "situations":          [ ...array of situation objects... ],
  "retrieval_was_vague": false,
  "handoff_logs":        [ ...agent handoff entries... ]
}
```

### POST `/approve`
```
Request:  { "request_id": "REQ-007", "selected_indices": [0, 1] }
Response: { "queue": [...], "volunteers": [...] }
```

### POST `/volunteer/return`
```
Request:  {
  "volunteer_id":   "V-02",
  "returned_items": [{"item": "Leg Splint", "quantity": 1}]
}
Response: { "freed_volunteer": "V-02", "queue": [...], "volunteers": [...], "inventory": [...] }
```

### GET `/queue`
```
Response: [ ...heap-sorted requests, most critical first... ]
```

### GET `/volunteers`
```
Response: [
  { "volunteer_id": "V-01", "status": "BUSY",      "request_id": "REQ-003",
    "assigned_at": "14:29", "expected_return": "14:43", "items_taken": [...] },
  { "volunteer_id": "V-04", "status": "AVAILABLE",  "request_id": null, ... }
]
```

---

## Performance Profile

| Component | RAM | Latency |
|-----------|-----|---------|
| Electron shell | ~200 MB | instant |
| Whisper base | ~500 MB | 2–4s (10s clip) |
| Facebook Denoiser dns64 | ~300 MB | 1–3s |
| LLaMA 3.2 3B (vagueness) | ~2.5 GB | 8–12s |
| LLaMA 3.2 3B (triage) | shared | 10–18s |
| LlamaIndex retrieval | ~200 MB | <1s |
| Heap + dispatch | ~5 MB | <10ms |
| APScheduler | ~10 MB | ~2ms/tick |
| **Total** | **~3.7 GB** | **~25–40s full pipeline** |

---

## Offline Guarantee

```
Every dependency at runtime is local:

  Whisper inference      → ~/.cache/whisper/            ✅ local
  LLaMA inference        → ./models/*.gguf               ✅ local
  Facebook Denoiser      → ~/.cache/torch/hub/           ✅ local
  MiniLM embeddings      → ~/.cache/huggingface/         ✅ local
  LlamaIndex index       → ./vector_store/               ✅ local
  Inventory              → ./data/inventory.csv          ✅ local
  PDF protocols          → ./data/protocols/*.pdf        ✅ local
  Gradio / CDN           → not used                      ✅ none

  External network calls at runtime: ZERO
```