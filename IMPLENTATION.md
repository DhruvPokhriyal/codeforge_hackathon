# 🛠️ Implementation Guide
## Full Technical Breakdown — Offline Emergency Intelligence Hub

---

## Pipeline Overview

```
audio_base64
  → denoiser.py              clean .wav
  → intake_agent.py          transcript string
  → retrieval_agent.py       top-k chunks + confidence scores
       ├─ conf ≥ 0.8 ──────→ rag_triage_agent.py
       └─ conf < 0.8 ──────→ vagueness_agent.py → retry retrieval → rag_triage_agent.py
  → rag_triage_agent.py      multi-situation report JSON
  → logistics_agent.py       inventory availability per situation
  → [FRONTEND] HITL approval → manager selects situations, items reserved
  → priority_queue.py        heap push with computed key
  → dispatch_engine.py       assign free volunteer
  → escalation_scheduler.py  background key escalation every 60s
```

---

## Step 1 — Audio Denoising

Two denoisers are benchmarked on 10–15 samples (generated + real-world shelter recordings). Final implementation uses the winner. Both are supported in code via a config flag.

```python
# backend/agents/denoiser.py
import noisereduce as nr
import numpy as np
import scipy.io.wavfile as wav

# Option A: noisereduce
def denoise_noisereduce(input_path: str, output_path: str) -> str:
    rate, data = wav.read(input_path)
    if data.ndim == 2:
        data = data.mean(axis=1).astype(np.int16)
    cleaned = nr.reduce_noise(
        y=data.astype(np.float32),
        sr=rate,
        stationary=True,
        prop_decrease=0.85
    )
    wav.write(output_path, rate, cleaned.astype(np.int16))
    return output_path

# Option B: Facebook Denoiser (dns64 model)
def denoise_facebook(input_path: str, output_path: str) -> str:
    import torch
    from denoiser import pretrained
    from denoiser.dsp import convert_audio

    model = pretrained.dns64()
    model.eval()
    wav_tensor, sr = torchaudio.load(input_path)
    wav_tensor = convert_audio(wav_tensor, sr, model.sample_rate, model.chin)
    with torch.no_grad():
        denoised = model(wav_tensor[None])[0]
    torchaudio.save(output_path, denoised, model.sample_rate)
    return output_path

# Config-driven selection
DENOISER = "noisereduce"   # or "facebook"

def denoise(input_path: str, output_path: str) -> str:
    if DENOISER == "facebook":
        return denoise_facebook(input_path, output_path)
    return denoise_noisereduce(input_path, output_path)
```

---

## Step 2 — Speech to Text (Whisper)

```python
# backend/agents/intake_agent.py
import whisper

_model = None

def get_model():
    global _model
    if _model is None:
        _model = whisper.load_model("base")
    return _model

def transcribe(audio_path: str) -> str:
    model = get_model()
    result = model.transcribe(audio_path, fp16=False)  # fp16=False = CPU only
    return result["text"].strip()
```

---

## Step 3 — RAG Retrieval with Confidence Check

```python
# backend/agents/retrieval_agent.py
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.core.response.schema import Response
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import Settings

Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
Settings.llm = None   # we control LLM separately

CONFIDENCE_THRESHOLD = 0.8

_index = None

def build_index(pdf_dir: str = "./data/protocols/"):
    global _index
    docs = SimpleDirectoryReader(pdf_dir).load_data()
    _index = VectorStoreIndex.from_documents(docs)

def retrieve(query: str, top_k: int = 5) -> dict:
    """Returns chunks with scores and a vague flag."""
    retriever = _index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query)

    chunks = [
        {
            "text":       n.node.get_content(),
            "score":      n.score,
            "source":     n.node.metadata.get("file_name", "unknown"),
            "page":       n.node.metadata.get("page_label", "?")
        }
        for n in nodes
    ]

    top_score = chunks[0]["score"] if chunks else 0.0
    is_vague  = top_score < CONFIDENCE_THRESHOLD

    return {
        "chunks":   chunks,
        "is_vague": is_vague,
        "top_score": top_score
    }
```

---

## Step 4 — Vagueness Resolver (When Confidence < 0.8)

```python
# backend/agents/vagueness_agent.py
from llama_cpp import Llama

VAGUENESS_PROMPT = """You are an emergency medical AI.
The following distress report is unclear or ambiguous.
Generate 2-3 possible medical conditions for each severity level.

Report: "{transcript}"

Respond ONLY in JSON:
{{
  "CRITICAL": ["cardiac arrest", "stroke", "internal bleeding"],
  "HIGH":     ["fracture with shock", "spinal injury"],
  "MEDIUM":   ["seizure", "diabetic episode"],
  "LOW":      ["exhaustion", "dehydration"]
}}"""

def resolve_vagueness(transcript: str, llm: Llama) -> dict:
    prompt = VAGUENESS_PROMPT.format(transcript=transcript)
    resp = llm(prompt, max_tokens=400, temperature=0.2)
    raw = resp["choices"][0]["text"].strip()
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except:
        return {
            "CRITICAL": ["cardiac arrest"],
            "HIGH":     ["fracture"],
            "MEDIUM":   ["fever"],
            "LOW":      ["dehydration"]
        }

def resolve_and_retrieve(transcript: str, llm: Llama, retrieve_fn) -> list:
    """Expand hypotheses → retrieve for each → merge unique top chunks."""
    hypotheses = resolve_vagueness(transcript, llm)
    all_chunks = []
    seen_texts = set()

    for severity, conditions in hypotheses.items():
        for condition in conditions:
            query = f"{condition} first aid emergency treatment"
            result = retrieve_fn(query, top_k=3)
            for chunk in result["chunks"]:
                if chunk["text"] not in seen_texts:
                    seen_texts.add(chunk["text"])
                    chunk["hypothesis"] = condition
                    chunk["hypothesis_severity"] = severity
                    all_chunks.append(chunk)

    # Sort by score descending
    return sorted(all_chunks, key=lambda c: c["score"], reverse=True)[:10]
```

---

## Step 5 — RAG LLM + Triage Agent

This is the core agent. It reads the transcript + retrieved chunks and generates a **multi-situation structured report** with triage severity, materials, instructions, and heap key components.

```python
# backend/agents/rag_triage_agent.py

RAG_TRIAGE_PROMPT = """You are an emergency medical AI at a disaster shelter.
You have received a distress call and retrieved relevant first-aid information.

TRANSCRIPT: "{transcript}"

RETRIEVED INFORMATION:
{chunks_text}

Generate a structured emergency response report.
List ALL plausible situations (2-4). For each situation provide:
- label: short name of the condition
- severity: CRITICAL, HIGH, MEDIUM, or LOW
- severity_score: CRITICAL=100, HIGH=75, MEDIUM=50, LOW=25
- travel_time_min: estimated minutes to reach person
- resolution_time_min: estimated minutes to resolve on-site
- materials: list of {{item, quantity}} required
- instructions: numbered step-by-step actions for volunteer
- reasoning: why this severity level

Respond ONLY with valid JSON array. No extra text.
[
  {{
    "label":               "Cardiac Arrest",
    "severity":            "CRITICAL",
    "severity_score":      100,
    "travel_time_min":     8,
    "resolution_time_min": 20,
    "confidence":          0.91,
    "materials":           [{{"item": "AED", "quantity": 1}}, {{"item": "CPR Mask", "quantity": 1}}],
    "instructions":        ["Step 1: Call for help", "Step 2: Begin CPR..."],
    "reasoning":           "Unresponsive person with abnormal leg position suggests cardiac or neurological event"
  }}
]"""

def compute_heap_key(severity_score: int, travel_time: int, resolution_time: int) -> float:
    return float(severity_score - (travel_time * 2) - resolution_time)

def run_rag_triage(transcript: str, chunks: list, llm: Llama) -> list:
    chunks_text = "\n\n".join(
        f"[Source: {c['source']} p.{c['page']} | Score: {c['score']:.2f}]\n{c['text']}"
        for c in chunks[:6]
    )
    prompt = RAG_TRIAGE_PROMPT.format(
        transcript=transcript,
        chunks_text=chunks_text
    )
    resp = llm(prompt, max_tokens=1200, temperature=0.15)
    raw  = resp["choices"][0]["text"].strip()

    try:
        start, end = raw.find("["), raw.rfind("]") + 1
        situations = json.loads(raw[start:end])
    except:
        situations = [{
            "label": "Unknown Emergency", "severity": "HIGH",
            "severity_score": 75, "travel_time_min": 10,
            "resolution_time_min": 20, "confidence": 0.5,
            "materials": [], "instructions": ["Assess situation on arrival"],
            "reasoning": "JSON parse failed — defaulted to HIGH"
        }]

    # Attach heap_key and source chunks to each situation
    for s in situations:
        s["heap_key"]      = compute_heap_key(
            s["severity_score"], s["travel_time_min"], s["resolution_time_min"]
        )
        s["source_chunks"] = [
            f"{c['source']} p.{c['page']}" for c in chunks[:3]
        ]
        s["selected"]      = False   # manager selects in HITL step

    return situations
```

---

## Step 6 — Inventory Check Per Situation

```python
# backend/agents/logistics_agent.py
import pandas as pd
from rapidfuzz import process, fuzz

df = pd.read_csv("./data/inventory.csv")

def check_availability(item_name: str) -> dict:
    names = df["Item"].tolist()
    match, score, idx = process.extractOne(item_name, names, scorer=fuzz.partial_ratio)
    if score < 55:
        return {"found": False, "available": False, "quantity": 0}
    row = df.iloc[idx]
    avail = int(row["Available"])
    return {
        "found":     True,
        "item":      row["Item"],
        "available": avail > 0,
        "quantity":  avail,
        "bin":       row["Bin Location"],
    }

def annotate_situations(situations: list) -> list:
    """Add availability info to every material in every situation."""
    for sit in situations:
        for mat in sit.get("materials", []):
            inv = check_availability(mat["item"])
            mat["available"]      = inv["available"]
            mat["available_qty"]  = inv.get("quantity", 0)
            mat["bin"]            = inv.get("bin", "?")
    return situations
```

---

## Step 7 — Human-in-the-Loop (Frontend Logic)

The frontend renders each situation as a card. The manager selects ≥ 1, then clicks Approve. Items for all selected situations are reserved atomically.

```javascript
// frontend/app.js — HITL rendering

function renderHITLReport(situations) {
    const container = document.getElementById('hitl-panel')
    container.innerHTML = ''

    situations.forEach((sit, i) => {
        const card = document.createElement('div')
        card.className = `situation-card severity-${sit.severity.toLowerCase()}`
        card.innerHTML = `
          <h3>${sit.label} <span class="badge">${sit.severity}</span></h3>
          <p>Confidence: ${(sit.confidence * 100).toFixed(0)}%</p>
          <p>Travel: ${sit.travel_time_min}min | Resolution: ${sit.resolution_time_min}min</p>

          <h4>Materials</h4>
          <ul>
            ${sit.materials.map(m => `
              <li class="${m.available ? '' : 'greyed-out'}">
                ${m.available ? '☑' : '☐'} ${m.item} ×${m.quantity}
                — ${m.available ? `Bin ${m.bin} (${m.available_qty} avail.)` : 'OUT OF STOCK'}
              </li>
            `).join('')}
          </ul>

          <h4>Instructions</h4>
          <ol>${sit.instructions.map(s => `<li>${s}</li>`).join('')}</ol>

          <details>
            <summary>📄 Source Chunks (Explainability)</summary>
            ${sit.source_chunks.map(s => `<p class="chunk-ref">${s}</p>`).join('')}
          </details>

          <label>
            <input type="checkbox" id="select-${i}" onchange="toggleSituation(${i})">
            Select this situation
          </label>
        `
        container.appendChild(card)
    })

    // Manual override
    container.innerHTML += `
      <div id="manual-override">
        <h3>⚙️ Override Manually</h3>
        <input id="manual-condition" placeholder="Condition description" />
        <input id="manual-items" placeholder="Items (comma-separated)" />
      </div>
      <button onclick="approveSelected()">✅ Approve & Dispatch</button>
    `
}
```

On approve, `POST /approve` is called with selected situation indices. The backend reserves items and pushes to the heap.

---

## Step 8 — Max-Heap Priority Queue

```python
# backend/core/priority_queue.py
import heapq
from datetime import datetime

class PriorityQueue:
    def __init__(self):
        self._heap = []          # [(-heap_key, timestamp_str, request_id)]
        self._store = {}         # request_id → request dict

    def push(self, request: dict):
        key    = request["heap_key"]
        ts     = request["time_of_request"]
        req_id = request["request_id"]
        heapq.heappush(self._heap, (-key, ts, req_id))
        self._store[req_id] = request

    def peek_top_pending(self) -> dict | None:
        for neg_key, ts, req_id in self._heap:
            req = self._store.get(req_id)
            if req and req["status"] == "PENDING":
                return req
        return None

    def get_sorted(self) -> list:
        return [
            self._store[req_id]
            for _, _, req_id in sorted(self._heap)
            if req_id in self._store
        ]

    def update_key(self, request_id: str, new_key: float):
        """Called by escalation scheduler. Rebuilds heap."""
        if request_id in self._store:
            self._store[request_id]["heap_key"] = new_key
            # Rebuild heap (heapq has no decrease-key)
            self._heap = [
                (-self._store[rid]["heap_key"], ts, rid)
                for _, ts, rid in self._heap
                if rid in self._store
            ]
            heapq.heapify(self._heap)

    def update(self, request_id: str, updates: dict):
        if request_id in self._store:
            self._store[request_id].update(updates)

priority_queue = PriorityQueue()
```

---

## Step 9 — Exponential Urgency Escalation

```python
# backend/core/escalation_scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import math

# Escalation schedule per severity category
# Each entry: (hours_since_request, key_boost, buffer_multiplier)
ESCALATION_SCHEDULE = {
    "CRITICAL": [
        (0.067, 500, 1.0),   # 4 min — brain damage threshold
    ],
    "HIGH": [
        (2,  20,  1.0),
        (4,  60,  1.2),
        (5,  150, 1.5),
    ],
    "MEDIUM": [
        (4,  10,  1.0),
        (8,  30,  1.2),
        (12, 80,  1.5),
    ],
    "LOW": [
        (6,  5,   1.0),
        (10, 15,  1.2),
        (13, 40,  1.5),
        (15, 100, 2.0),
    ],
}

def compute_buffer(travel_time: int, resolution_time: int, multiplier: float) -> float:
    return (travel_time + resolution_time) * multiplier

def escalate_keys(queue):
    now = datetime.now()
    for req in queue.get_sorted():
        if req["status"] != "PENDING":
            continue

        severity   = req["situations"][0]["severity"]  # use dominant situation
        t_req      = datetime.fromisoformat(req["time_of_request"])
        hours_wait = (now - t_req).total_seconds() / 3600

        schedule   = ESCALATION_SCHEDULE.get(severity, [])
        base_key   = req["situations"][0]["heap_key"]
        escalation = 0

        for (threshold_h, boost, buf_mult) in schedule:
            if hours_wait >= threshold_h:
                travel    = req["situations"][0]["travel_time_min"]
                res       = req["situations"][0]["resolution_time_min"]
                buffer    = compute_buffer(travel, res, buf_mult)
                escalation = boost + buffer   # take highest matching tier
            else:
                break  # schedule is cumulative up to current time

        new_key = base_key + escalation
        if new_key != req["heap_key"]:
            queue.update_key(req["request_id"], new_key)
            req["escalation_stage"] += 1

scheduler = BackgroundScheduler()

def start_scheduler(queue):
    scheduler.add_job(
        lambda: escalate_keys(queue),
        trigger="interval",
        seconds=60,
        id="escalation_job"
    )
    scheduler.start()
```

---

## Step 10 — Volunteer Dispatch Engine

```python
# backend/core/dispatch_engine.py
from datetime import datetime, timedelta

VOLUNTEERS = {
    f"V-{i:02d}": {
        "status": "AVAILABLE",
        "request_id": None,
        "assigned_at": None,
        "expected_return": None,
        "items_taken": []
    }
    for i in range(1, 7)
}

def get_free_volunteer() -> str | None:
    for vid, info in VOLUNTEERS.items():
        if info["status"] == "AVAILABLE":
            return vid
    return None

def dispatch(queue) -> dict | None:
    top = queue.peek_top_pending()
    if not top:
        return None
    free = get_free_volunteer()
    if not free:
        return None

    now = datetime.now()

    # Compute expected return from dominant selected situation
    selected = [s for s in top["situations"] if s.get("selected")]
    if not selected:
        selected = top["situations"][:1]
    travel  = selected[0]["travel_time_min"]
    resolve = selected[0]["resolution_time_min"]
    exp_return = (now + timedelta(minutes=travel + resolve)).strftime("%H:%M:%S")

    items_taken = []
    for s in selected:
        for mat in s.get("materials", []):
            if mat.get("available"):
                items_taken.append({"item": mat["item"], "quantity": mat["quantity"]})

    VOLUNTEERS[free].update({
        "status":          "BUSY",
        "request_id":      top["request_id"],
        "assigned_at":     now.strftime("%H:%M:%S"),
        "expected_return": exp_return,
        "items_taken":     items_taken
    })
    queue.update(top["request_id"], {
        "status":             "ASSIGNED",
        "assigned_volunteer": free,
        "assigned_at":        now.strftime("%H:%M:%S"),
        "expected_return":    exp_return,
        "items_taken":        items_taken
    })
    return {"volunteer": free, "request_id": top["request_id"]}

def volunteer_return(volunteer_id: str, returned_items: list, queue, inventory_mgr):
    """
    Called when shelter head clicks 'Back at Base'.
    returned_items: [{"item": "Leg Splint", "quantity": 1}, ...]
    """
    req_id = VOLUNTEERS[volunteer_id]["request_id"]
    now    = datetime.now().strftime("%H:%M:%S")

    # Restore returned items to inventory
    for item in returned_items:
        inventory_mgr.restore(item["item"], item["quantity"])

    queue.update(req_id, {
        "status":        "RESOLVED",
        "actual_return": now,
        "items_returned": returned_items
    })

    VOLUNTEERS[volunteer_id] = {
        "status": "AVAILABLE", "request_id": None,
        "assigned_at": None, "expected_return": None, "items_taken": []
    }
    dispatch(queue)   # immediately check for next task
```

---

## Inventory Manager

```python
# backend/utils/inventory_manager.py
import pandas as pd

CSV_PATH = "./data/inventory.csv"
REFILL_THRESHOLD = 0.60

class InventoryManager:
    def __init__(self):
        self.df = pd.read_csv(CSV_PATH)

    def reserve(self, item_name: str, quantity: int) -> bool:
        idx = self._find(item_name)
        if idx is None: return False
        if self.df.at[idx, "Available"] < quantity: return False
        self.df.at[idx, "Available"]  -= quantity
        self.df.at[idx, "Reserved"]   += quantity
        self._save()
        return True

    def restore(self, item_name: str, quantity: int):
        idx = self._find(item_name)
        if idx is None: return
        self.df.at[idx, "Available"]  += quantity
        self.df.at[idx, "Reserved"]   = max(0, self.df.at[idx, "Reserved"] - quantity)
        self._save()

    def daily_refill(self):
        """Full refill — run at midnight."""
        self.df["Available"] = self.df["Total"]
        self.df["Reserved"]  = 0
        self._save()

    def partial_refill(self):
        """Refill only items at ≤ 60% capacity."""
        for idx, row in self.df.iterrows():
            if row["Total"] > 0:
                pct = row["Available"] / row["Total"]
                if pct <= REFILL_THRESHOLD:
                    self.df.at[idx, "Available"] = row["Total"]
        self._save()

    def get_all(self) -> list:
        return self.df.to_dict(orient="records")

    def _find(self, item_name: str) -> int | None:
        from rapidfuzz import process, fuzz
        names = self.df["Item"].tolist()
        match, score, idx = process.extractOne(item_name, names, scorer=fuzz.partial_ratio)
        return idx if score >= 55 else None

    def _save(self):
        self.df.to_csv(CSV_PATH, index=False)
```

---

## FastAPI Route Summary

| Method | Route | Description |
|--------|-------|-------------|
| POST | `/pipeline` | Full pipeline: denoise → STT → retrieve → triage → inventory check |
| POST | `/approve` | Manager approves situations, reserves items, pushes to heap |
| POST | `/volunteer/return` | Marks volunteer back, restores items, re-dispatches |
| GET | `/queue` | Live heap-sorted request list |
| GET | `/volunteers` | All volunteer statuses + timers |
| GET | `/inventory` | Full inventory with available/reserved/total |
| PUT | `/inventory/refill` | Trigger refill (daily or partial) |
| GET | `/health` | Startup health check for Electron |

---

## Agent Handoff Log Format

Every agent transition is logged in structured JSON:

```json
{
  "timestamp":  "14:32:09.441",
  "from_agent": "RETRIEVAL_AGENT",
  "to_agent":   "VAGUENESS_AGENT",
  "reason":     "top_score=0.43 < threshold=0.8",
  "payload":    {
    "transcript":  "my neighbour uncle is not moving...",
    "top_score":   0.43,
    "is_vague":    true
  }
}
```

All logs are written to `logs/handoffs.jsonl` and surfaced in the dashboard's expandable log panel.

---

## Frontend — Volunteer Timer (Live Clock)

```javascript
// frontend/app.js — countdown timers
function startTimers(volunteers) {
    volunteers.forEach(v => {
        if (v.status !== "BUSY") return
        const el = document.getElementById(`timer-${v.volunteer_id}`)
        if (!el) return

        const expReturn = new Date(`1970-01-01T${v.expected_return}`)
        const now       = new Date(`1970-01-01T${new Date().toTimeString().slice(0,8)}`)
        let remaining   = Math.floor((expReturn - now) / 1000)  // seconds

        const interval = setInterval(() => {
            remaining--
            const mins = Math.floor(Math.abs(remaining) / 60)
            const secs = Math.abs(remaining) % 60
            const sign = remaining < 0 ? "-" : ""
            el.textContent = `${sign}${mins}:${secs.toString().padStart(2, "0")}`
            el.className   = remaining < 0 ? "timer overdue" : "timer"
            // Timer never clears — stays at negative until "Back at Base" pressed
        }, 1000)
    })
}
```

---

## Requirements.txt

```
# Audio
openai-whisper==20231117
noisereduce==3.0.2
denoiser==0.1.5          # facebook denoiser (benchmarked)
torchaudio==2.3.1
torch==2.3.1
scipy==1.13.1
sounddevice==0.4.7
numpy==1.26.4

# LLM
llama-cpp-python==0.2.90

# RAG
llama-index==0.10.68
llama-index-embeddings-huggingface==0.2.3
sentence-transformers==3.0.1

# Data
pandas==2.2.2
rapidfuzz==3.9.7

# Scheduling
APScheduler==3.10.4

# Backend
fastapi==0.111.0
uvicorn==0.30.1

# Model download
huggingface-hub==0.23.4
```