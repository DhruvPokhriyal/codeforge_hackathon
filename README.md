# 🚨 Offline Emergency Intelligence Hub
> **AI for Impact — 5-Day Sprint Challenge | Track 2: Disaster Relief**
> A fully offline, CPU-only multi-agent RAG triage and volunteer dispatch system for disaster shelters.

---

## 📌 Problem Statement

During natural disasters, the internet and cloud services fail first. A **command-center laptop** at the shelter receives distress calls as audio files. Volunteers (1–3 people on-site) must be dispatched to people in need. The shelter has:
- A fixed **inventory** of medical and survival supplies
- A **library of offline PDFs** (first-aid manuals, emergency protocols)
- A **limited number of volunteers** who physically travel to people in distress

The system must triage every incoming report, retrieve relevant protocols from PDFs using RAG, confirm what inventory is available, dispatch volunteers to the highest-priority cases first, and track everything on a live dashboard — all with zero internet.

---

## 🔄 Complete System Workflow

```
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 1 — AUDIO INPUT                      [Electron Frontend]       │
│  Volunteer loads incoming distress audio file (from phone call etc.) │
│  Sent to backend as base64 via POST /pipeline                        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ audio file (base64)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 2 — AUDIO DENOISING                  [FastAPI Backend]         │
│  noisereduce (or facebook denoiser — benchmarked) strips:            │
│  crowd noise · alarms · rain · crackling phone audio                 │
│  → clean .wav ready for transcription                                │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ denoised .wav
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 3 — SPEECH TO TEXT                   [FastAPI Backend]         │
│  Whisper base (fp16=False) → clean transcript string                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ transcript
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 4 — RAG RETRIEVAL (First Pass)       [FastAPI Backend]         │
│  Embed transcript → semantic search over offline PDF index           │
│  Returns top-k chunks with confidence scores                         │
│                                                                      │
│  CONFIDENCE CHECK:                                                   │
│    Top chunk score ≥ 0.8 → proceed to Step 5                        │
│    Top chunk score < 0.8 → VAGUE QUERY → Step 4b                    │
└───────────────┬──────────────────────────┬───────────────────────────┘
                │ (clear, conf ≥ 0.8)      │ (vague, conf < 0.8)
                │                          ▼
                │          ┌───────────────────────────────────────────┐
                │          │  STEP 4b — LLM VAGUENESS RESOLVER         │
                │          │  "my neighbour uncle is not moving and     │
                │          │   his legs look wrong"                     │
                │          │  LLM generates possible diagnoses at       │
                │          │  each criticality level:                   │
                │          │    CRITICAL: cardiac arrest, stroke        │
                │          │    HIGH: fracture + shock                  │
                │          │    LOW: faint, exhaustion                  │
                │          │  → Retry retrieval for each hypothesis     │
                │          └──────────────────┬────────────────────────┘
                │                             │ expanded queries
                └──────────────┬──────────────┘
                               │ retrieved chunks (with source refs)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 5 — RAG LLM + TRIAGE                [FastAPI Backend]          │
│  LLM reads retrieved chunks + transcript                             │
│  Outputs a structured report listing MULTIPLE situation possibilities│
│  Each possibility includes:                                          │
│    · Situation label + severity (CRITICAL / HIGH / MEDIUM / LOW)    │
│    · Materials/equipment required                                    │
│    · Step-by-step instructions (for the volunteer on-site)          │
│    · Retrieved source chunks (for explainability)                    │
│                                                                      │
│  HEAP KEY formula per situation:                                     │
│    key = severity_score                                              │
│          - (travel_time_min × 2)                                     │
│          - resolution_time_min                                       │
│    + exponential urgency escalation over time (see Core Logic)      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ multi-situation report
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 6 — INVENTORY CHECK                  [FastAPI Backend]         │
│  For each situation possibility in the report:                       │
│    Check each required item against inventory CSV                    │
│    Items available → shown normally                                  │
│    Items unavailable → greyed out in UI checklist                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ availability-annotated report
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 7 — HUMAN-IN-THE-LOOP APPROVAL       [Electron Frontend]       │
│  Shelter manager sees the full report:                               │
│    · Multiple situation possibilities with checklists                │
│    · Items greyed out if unavailable in inventory                    │
│    · Retrieved PDF source chunks shown for explainability            │
│    · Manager selects ≥ 1 situation(s) to confirm                    │
│    · OR manually overrides: enters own condition + items             │
│    · Selected items are RESERVED from inventory                      │
│  → Manager clicks Approve → enters Priority Queue                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ approved situations + reserved items
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 8 — MAX-HEAP PRIORITY QUEUE          [FastAPI Backend]         │
│  Request pushed into max-heap                                        │
│  heap_key = severity_score - (travel_time×2) - resolution_time      │
│  Key escalates exponentially over time per category thresholds       │
│  Buffer time added at each escalation step                           │
│  Same-key tie-break = arrival time (FIFO)                           │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ heap updated
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 9 — VOLUNTEER DISPATCH ENGINE        [FastAPI Backend]         │
│  Assigns free volunteers to top-heap tasks                           │
│  Timer per volunteer (countdown to expected return)                  │
│  Timer hits 0 → freezes at 0 / goes negative                        │
│  Volunteer NOT reassigned until shelter head clicks "Back at base"   │
│  On return: popup checklist of items taken — manager ticks returned  │
│  Returned items restored to inventory immediately                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ live state
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 10 — LIVE DASHBOARD                  [Electron Renderer]       │
│                                                                      │
│  Panel A — Priority Queue (heap order, auto-refresh)                 │
│    REQ-ID · Severity · Summary · Request Time · Volunteer            │
│    Expected Return · Status · [Back at Base] button                  │
│                                                                      │
│  Panel B — Volunteer Activity Board                                  │
│    Volunteer ID · Status · Current REQ-ID                            │
│    Countdown timer (live clock) · Items taken                        │
│                                                                      │
│  Panel C — Inventory Status                                          │
│    All items · Available qty · Reserved qty · Total                  │
│    Daily refill indicator · Low-stock alert (≤ 60%)                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 Core Logic

### Heap Key Formula

```
heap_key = severity_base_score
           - (travel_time_minutes × 2)
           - resolution_time_minutes
           + urgency_escalation(t)
```

| Severity | Base Score |
|----------|-----------|
| CRITICAL | 100 |
| HIGH | 75 |
| MEDIUM | 50 |
| LOW | 25 |

**Travel time and resolution time** are estimated by the RAG LLM per situation and penalise key (harder to reach = lower initial priority vs equally severe but reachable case). Buffer time is added at every escalation step: `buffer = f(travel_time, resolution_time)`.

---

### Exponential Urgency Escalation

Every unresolved request has its key escalated on a per-category schedule. The escalation is **exponential** — each interval shorter than the last, modelling real-world deterioration.

```
EXAMPLE — Common Cold (initially LOW):
  t=0h      key += 0       (baseline)
  t+6h      key += 5       (may develop fever)
  t+10h     key += 15      (high fever possible)
  t+13h     key += 40      (weakness, dehydration risk)
  t+15h     key += 100     (now effectively CRITICAL)

  Buffer added at each step = f(travel_time, resolution_time)
  so even short trips are re-evaluated against the escalated key

EXAMPLE — Fracture (HIGH):
  t=0h      key += 0
  t+2h      key += 20      (pain/shock worsening)
  t+4h      key += 60      (nerve damage risk)
  t+5h      key += 150     (vascular compromise)

EXAMPLE — Cardiac Arrest (CRITICAL):
  t=0h      key += 0
  t+4min    key += 500     (brain damage threshold)
```

Escalation runs on a **background scheduler** (APScheduler) checking all PENDING tasks every 60 seconds and updating keys.

---

### Vague Query Flow (RAG Confidence < 0.8)

```
Transcript: "my neighbour uncle is not moving and his legs look wrong"
               ↓
  Top retrieval confidence = 0.43  →  VAGUE
               ↓
  LLM Vagueness Resolver generates hypotheses:
    CRITICAL: cardiac arrest, stroke, internal bleeding
    HIGH:     severe fracture with shock, spinal injury
    MEDIUM:   faint, seizure, diabetic episode
    LOW:      exhaustion, dehydration
               ↓
  Retry retrieval for each hypothesis
               ↓
  Merge top chunks across all hypotheses
               ↓
  RAG LLM generates multi-situation report (all possibilities)
```

---

### Human-in-the-Loop Report (Step 7)

The manager sees a report card per situation possibility:

```
┌─────────────────────────────────────────────────────┐
│ SITUATION A: Cardiac Arrest             🔴 CRITICAL  │
│ Confidence: 0.91                                     │
│                                                      │
│ Materials Required:                                  │
│  ☑ AED (Defibrillator)     Bin C-3  — AVAILABLE (2) │
│  ☑ CPR Mask                Bin A-4  — AVAILABLE (5) │
│  ☐ Oxygen Tank             Bin B-1  — OUT OF STOCK  │  ← greyed
│                                                      │
│ Instructions: [Step 1... Step 2...] [Source: pg.34] │
│ Retrieved chunks: [chunk 1] [chunk 2]               │
│                                                      │
│  [ SELECT THIS SITUATION ]                           │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SITUATION B: Severe Fracture + Shock   🟠 HIGH       │
│ Confidence: 0.76                                     │
│ ...                                                  │
│  [ SELECT THIS SITUATION ]                           │
└─────────────────────────────────────────────────────┘

  [ OVERRIDE MANUALLY ]  ← manager enters own diagnosis + items

  [ APPROVE SELECTED → DISPATCH ]
```

Manager selects ≥ 1 situation(s). All selected situations' required items are **reserved** from inventory simultaneously.

---

### Volunteer Timer + Return Flow

```
Volunteer dispatched → countdown timer starts on dashboard
  timer = travel_time + resolution_time (per situation estimate)

Timer reaches 0:
  → Freezes at 0:00 (or counts negative)
  → Volunteer NOT reassigned automatically
  → Shelter head must click "Back at Base" button

"Back at Base" clicked:
  → Popup: checklist of every item volunteer took
  → Manager ticks which items were returned/unused
  → Returned items restored to inventory immediately
  → Volunteer status → AVAILABLE
  → Dispatch engine re-runs for next task
```

---

### Inventory Management

```
RESERVATION:   Items reserved when situation(s) approved in Step 7
               available_qty -= reserved_qty
               reserved shown separately on inventory panel

RETURN:        When volunteer returns, manager checks returned items
               available_qty += returned_qty

DAILY REFILL:  Full refill every 24 hours (midnight reset)
               If item ≤ 60% remaining → flag for early refill

DISPLAY:
  Item | Available | Reserved | Total | Status
  Leg Splint | 3 | 1 | 4 | ✅
  AED        | 0 | 2 | 2 | ⚠️ ALL RESERVED
  Oxygen     | 0 | 0 | 0 | 🔴 OUT OF STOCK
```

---

### Request Object Schema

```json
{
  "request_id":          "REQ-007",
  "transcript":          "elderly woman, leg looks wrong, cannot move",
  "situations": [
    {
      "label":           "Fracture — Femur",
      "severity":        "HIGH",
      "severity_score":  75,
      "heap_key":        58.0,
      "travel_time_min": 7,
      "resolution_time_min": 15,
      "materials":       [{"item": "Leg Splint", "qty": 1, "bin": "A-1", "available": true}],
      "instructions":    "Step 1: Immobilise the limb...",
      "source_chunks":   ["first_aid_manual.pdf p.42", "trauma_guide.pdf p.11"],
      "confidence":      0.89,
      "selected":        true
    }
  ],
  "retrieval_was_vague": false,
  "time_of_request":     "14:32:07",
  "assigned_volunteer":  "V-02",
  "assigned_at":         "14:33:01",
  "expected_return":     "14:55:01",
  "actual_return":       null,
  "items_taken":         [{"item": "Leg Splint", "qty": 1}],
  "items_returned":      [],
  "status":              "ASSIGNED",
  "escalation_stage":    0,
  "next_escalation_at":  "16:32:07"
}
```

---

## 🖥️ Dashboard Panels

### Panel A — Priority Queue

| REQ-ID | Severity | Summary | Requested | Volunteer | Est. Return | Timer | Status |
|--------|----------|---------|-----------|-----------|-------------|-------|--------|
| REQ-007 | 🔴 CRITICAL | Cardiac arrest suspect | 14:32 | V-02 | 14:55 | 12:43 | ASSIGNED |
| REQ-003 | 🔴 CRITICAL | Child not breathing | 14:28 | V-01 | 14:43 | 02:11 | ASSIGNED |
| REQ-009 | 🟠 HIGH | Fracture + shock | 14:35 | V-03 | 14:58 | 18:00 | ASSIGNED |
| REQ-005 | 🟡 MEDIUM | Diabetic, no insulin | 14:30 | — | — | — | PENDING |
| REQ-002 | 🟢 LOW | Family needs food | 12:27 | — | — | — | PENDING ⚠️ escalating |

### Panel B — Volunteer Activity Board

| Volunteer | Status | REQ-ID | Task Summary | Timer | Items Taken | Action |
|-----------|--------|--------|-------------|-------|-------------|--------|
| V-01 | 🔴 BUSY | REQ-003 | Child not breathing | 02:11 | CPR Mask ×1 | [Back at Base] |
| V-02 | 🔴 BUSY | REQ-007 | Cardiac arrest | 12:43 | AED ×1, CPR Mask ×1 | [Back at Base] |
| V-03 | 🔴 BUSY | REQ-009 | Fracture | 18:00 | Leg Splint ×1 | [Back at Base] |
| V-04 | 🟢 AVAILABLE | — | — | — | — | — |

---

## 🏗️ Tech Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Frontend | Electron + HTML/CSS/JS | Desktop shell, dashboard, HITL approval UI |
| Backend | FastAPI + Uvicorn | REST API, 127.0.0.1 only |
| Audio Denoising | `noisereduce` + Facebook Denoiser (benchmarked) | Shelter noise removal |
| Speech-to-Text | `openai-whisper` base | Audio → transcript |
| RAG Retrieval | `LlamaIndex` + `all-MiniLM-L6-v2` | Semantic PDF search with confidence scores |
| Vagueness Resolver | LLaMA 3.2 3B GGUF | Expands vague queries into hypotheses |
| RAG LLM + Triage | LLaMA 3.2 3B GGUF | Multi-situation report + severity + instructions |
| Heap Key Escalation | APScheduler + custom formula | Exponential urgency escalation |
| Priority Queue | Python `heapq` | Max-heap with dynamic key escalation |
| Dispatch Engine | Custom Python scheduler | Volunteer assignment, timer, return flow |
| Inventory | `pandas` + `rapidfuzz` | CSV lookup, reservation, refill logic |
| Logging | Python `logging` + JSON | Full agent handoff logs, explainability trail |
| Packaging | PyInstaller + electron-builder | Single offline installer |

---

## 📁 Project Structure (Summary)

```
emergency-hub/
├── electron/           main.js · preload.js
├── frontend/           index.html · app.js · styles.css
├── backend/
│   ├── routers/        pipeline · queue · volunteers · resolve · inventory
│   ├── agents/         denoiser · intake · retrieval · vagueness · rag_triage · logistics
│   ├── core/           priority_queue · dispatch_engine · escalation_scheduler · request_store
│   └── utils/          logger · audio_utils · inventory_manager
├── data/               inventory.csv · protocols/*.pdf
├── models/             LLaMA GGUF
└── vector_store/       auto-generated LlamaIndex index
```

---

## ⚙️ Quick Setup

```bash
git clone https://github.com/your-team/emergency-hub.git && cd emergency-hub
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python scripts/download_models.py   # downloads LLaMA + Whisper + MiniLM
npm install
npm start
```

> ✅ Disable Wi-Fi after setup — zero runtime internet dependency.

---

## 📋 Evaluation Alignment

| Criteria | How We Address It |
|----------|-------------------|
| **Reliability** | Confidence-gated RAG, vagueness resolver, HITL override, exponential escalation prevents starvation, volunteer timer with freeze-on-zero |
| **Feasibility** | All models CPU-only, full pipeline <25s, heap + escalation in microseconds, single packaged installer |
| **Impact** | Every person in distress eventually served (no starvation). Explainable AI decisions. HITL keeps humans in control. One laptop runs an entire shelter. |
| **Open-Source** | Whisper · LLaMA · LlamaIndex · noisereduce · Electron · FastAPI · APScheduler — 100% open-source |

---

## 📄 License
MIT — open for humanitarian use and adaptation.