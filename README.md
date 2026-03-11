# 🚨 Offline Emergency Intelligence Hub

> **AI for Impact — 5-Day Sprint Challenge | Track 2: Disaster Relief**  
> A fully offline, CPU-only multi-agent emergency coordination system for disaster shelters.

---

## 📌 Problem Statement

During natural disasters, internet and cloud services fail first. Volunteers in shelters are overwhelmed, untrained for medical triage, and unable to locate resources quickly. This project turns a standard laptop into a **"digital lifeboat"** — a self-contained AI command center that works entirely offline.

---

## 🎯 End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                 │
│   User uploads / records an audio file describing an issue      │
└──────────────────────────┬──────────────────────────────────────┘
                           │  audio file (.wav / .mp3)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BACKEND                                  │
│                                                                 │
│   ┌─────────────────────────────────┐                          │
│   │  STEP 1 — Audio Denoising       │  ← noise reduction       │
│   │  Clean background noise from    │    (RNNoise / noisereduce)│
│   │  shelter environment            │                          │
│   └──────────────┬──────────────────┘                          │
│                  │  clean audio                                 │
│                  ▼                                              │
│   ┌─────────────────────────────────┐                          │
│   │  STEP 2 — Speech-to-Text        │  ← openai-whisper (base) │
│   │  Transcribe cleaned audio       │    CPU-only, offline      │
│   │  into plain text                │                          │
│   └──────────────┬──────────────────┘                          │
│                  │  transcript text                             │
│                  ▼                                              │
│   ┌─────────────────────────────────┐                          │
│   │  STEP 3 — Triage Agent          │  ← LLaMA 3.2 3B GGUF    │
│   │  Classify severity of the issue │    Outputs structured    │
│   │  (CRITICAL / HIGH / MEDIUM /    │    JSON: severity, type, │
│   │   LOW) + assign Request ID      │    description, req_id   │
│   └──────────────┬──────────────────┘                          │
│                  │  { req_id, severity_score, ... }            │
│                  ▼                                              │
│   ┌─────────────────────────────────┐                          │
│   │  STEP 4 — Priority Max-Heap     │  ← Python heapq          │
│   │  Insert request into max-heap   │    keyed by severity     │
│   │  Most severe request always     │    score; O(log n)       │
│   │  sits at the top                │    insert & pop          │
│   └──────────────┬──────────────────┘                          │
│                  │  sorted issue queue                         │
│                  ▼                                              │
│   ┌─────────────────────────────────┐                          │
│   │  STEP 5 — Helper Dispatcher     │  6 helpers available     │
│   │  Pop highest-severity request,  │  Helpers stay BUSY until │
│   │  assign to a free helper.       │  resolution_time of that │
│   │  Low-priority requests wait     │  request is reached.     │
│   │  until all high-priority ones   │  Each helper tracks      │
│   │  are resolved or in-progress.   │  their current req_id.   │
│   └──────────────┬──────────────────┘                          │
│                  │                                              │
└──────────────────┼──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DASHBOARD                                  │
│                                                                 │
│  Issue Queue (sorted highest → lowest severity)                 │
│  ┌──────────┬────────────┬──────────┬───────────┬───────────┐  │
│  │ Req ID   │ Severity   │ Issue    │ Req Time  │ Res Time  │  │
│  ├──────────┼────────────┼──────────┼───────────┼───────────┤  │
│  │ REQ-0042 │ 🔴 CRITICAL│ ...      │ 14:03:11  │ 14:18:11  │  │
│  │ REQ-0039 │ 🔴 CRITICAL│ ...      │ 14:01:44  │ 14:16:44  │  │
│  │ REQ-0045 │ 🟠 HIGH    │ ...      │ 14:05:02  │ 14:15:02  │  │
│  │ REQ-0041 │ 🟡 MEDIUM  │ ...      │ 14:02:55  │ 14:12:55  │  │
│  └──────────┴────────────┴──────────┴───────────┴───────────┘  │
│                                                                 │
│  Helper Status (6 helpers total)                                │
│  ┌──────────────┬────────────┬───────────────────────────────┐  │
│  │ Helper       │ Status     │ Assigned Request              │  │
│  ├──────────────┼────────────┼───────────────────────────────┤  │
│  │ Helper-1     │ 🟢 BUSY    │ REQ-0042 (until 14:18:11)    │  │
│  │ Helper-2     │ 🟢 BUSY    │ REQ-0039 (until 14:16:44)    │  │
│  │ Helper-3     │ 🟢 BUSY    │ REQ-0045 (until 14:15:02)    │  │
│  │ Helper-4     │ ⚪ FREE    │ —                             │  │
│  │ Helper-5     │ ⚪ FREE    │ —                             │  │
│  │ Helper-6     │ ⚪ FREE    │ —                             │  │
│  └──────────────┴────────────┴───────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Concepts

### Request ID
Every incoming audio report is assigned a unique `REQ-XXXX` identifier at the triage step. This ID is used across the entire system — in the heap, in dispatcher logs, and on the dashboard — so any stakeholder can instantly look up which helper is handling which issue.

### Max-Heap Priority Queue
Requests are stored in a **max-heap** keyed by numeric severity score:

| Severity Label | Score |
|----------------|-------|
| 🔴 CRITICAL    | 4     |
| 🟠 HIGH        | 3     |
| 🟡 MEDIUM      | 2     |
| 🟢 LOW         | 1     |

The heap guarantees that `pop()` always returns the most severe unassigned request in O(log n) time.

### Helper Dispatch Rules
- **6 helpers** are available at start (combination of on-laptop volunteers and on-floor helpers).
- A helper is assigned only to the **top of the heap** (highest severity available).
- Once assigned, a helper is **BUSY** until the `resolution_time` of their current request elapses.
- **Low-priority requests are only dispatched when no CRITICAL or HIGH requests remain** unassigned in the queue.
- The dashboard shows each helper's current `req_id` and the time they become free again.

### Time Tracking
Each request carries two timestamps:
- `request_time` — when the audio was received by the backend.
- `resolution_time` — estimated time by which the issue should be resolved (set by triage agent based on severity; e.g., CRITICAL = +15 min, HIGH = +10 min, MEDIUM = +10 min, LOW = +20 min).

---

## 🏗️ Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Frontend | React / Gradio | Audio upload + live dashboard |
| Audio Denoising | `noisereduce` + `librosa` | CPU-friendly, no GPU needed |
| Speech-to-Text | `openai-whisper` (base) | Noise-robust, CPU-friendly, ~140 MB |
| Triage Agent | `LLaMA 3.2 3B Q4_K_M GGUF` | ~2 GB RAM, runs on CPU at ~8 tok/s |
| Priority Queue | Python `heapq` (max-heap) | O(log n) insert & pop |
| Helper Dispatcher | Custom Python scheduler | Heap-driven, time-aware assignment |
| Dashboard | `Gradio` / React | Real-time issue queue + helper status |
| Orchestration | Custom Python pipeline | Explicit JSON handoff logs |

**Total model size on disk: ~2.3 GB**

---

## 📁 Project Structure

```
emergency-hub/
│
├── main.py                        # Entry point — launches UI & initializes agents
├── main_pipeline.py               # Orchestrator — audio → denoise → STT → triage → heap → dispatch
│
├── agents/
│   ├── intake_agent.py            # Step 2: Whisper speech-to-text
│   ├── triage_agent.py            # Step 3: LLaMA severity classification → JSON + req_id
│   └── denoiser.py                # Step 1: Audio denoising (noisereduce / RNNoise)
│
├── core/
│   ├── priority_queue.py          # Max-heap wrapper (severity-keyed)
│   ├── dispatcher.py              # Helper assignment logic + busy-until tracking
│   └── request_store.py           # In-memory store of all requests by req_id
│
├── dashboard/
│   └── app.py                     # Gradio/React dashboard — issue queue + helper table
│
├── models/
│   └── llama-3.2-3b-instruct.Q4_K_M.gguf   # Download separately (~2 GB)
│
├── utils/
│   └── logger.py                  # JSON handoff log formatter
│
├── requirements.txt
└── README.md
```

---

## ⚙️ Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/your-team/emergency-hub.git
cd emergency-hub
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Download models
```bash
# Whisper (auto-downloads on first run)
python -c "import whisper; whisper.load_model('base')"

# LLaMA 3.2 3B GGUF — download from HuggingFace
# Place in ./models/llama-3.2-3b-instruct.Q4_K_M.gguf
```

> Get the GGUF model from: `https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF`

### 4. Add your inventory CSV
Edit `data/inventory.csv` with your shelter's resources (see format below).

### 5. Run
```bash
python main.py
# Opens at http://localhost:7860
```

> ✅ **Disable your Wi-Fi and test — it works fully offline.**

---

## 📊 Inventory CSV Format

```csv
Item,Quantity,Bin Location,Category
Leg Splint,4,A-1,Medical
Bandages,50,A-2,Medical
Water Bottles,200,B-3,Resources
Blankets,30,C-1,Comfort
Tourniquets,10,A-1,Medical
Flashlights,15,D-2,Equipment
```

---

## 🧪 Requirements

```
openai-whisper
llama-cpp-python
llama-index
llama-index-embeddings-huggingface
sentence-transformers
pandas
rapidfuzz
gradio
sounddevice
numpy
```

---

## 🖥️ System Requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| RAM | 6 GB | 8 GB+ |
| CPU | 4-core | 8-core |
| Disk | 5 GB free | 10 GB free |
| OS | Windows 10 / Ubuntu 20.04 / macOS 11 | Any |
| Internet | ❌ Not required at runtime | — |

---

## 📋 Evaluation Alignment

| Criteria | How We Address It |
|----------|-------------------|
| **Reliability** | LLaMA 3.2 structured JSON output + fuzzy inventory matching |
| **Feasibility** | Full pipeline under 15s on a 4-core CPU laptop |
| **Impact** | Designed for real disaster shelter workflows |
| **Open-Source** | Whisper, LLaMA, LlamaIndex, Gradio — 100% open-source |

---

## 👥 Team

Built for the **AI for Impact: 5-Day Sprint Challenge**  
Track 2 — Offline Emergency Intelligence Hub

---

## 📄 License

MIT License — open for humanitarian use and adaptation.