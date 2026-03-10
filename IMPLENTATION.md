# 🛠️ Track 2: Implementation Guide
## Offline Emergency Intelligence Hub — Full Technical Breakdown

---

## System Architecture Overview

```
VOICE INPUT (mic or .wav file)
        ↓
┌─────────────────────────┐
│   AGENT 1: INTAKE       │  ← openai-whisper (base model, CPU)
│   Speech → Clean Text   │
└─────────────────────────┘
        ↓  [HANDOFF LOG #1]
┌─────────────────────────┐
│   AGENT 2: TRIAGE       │  ← LLaMA 3.2 3B GGUF Q4_K_M
│   Severity + Need       │    Outputs structured JSON
│   Classification        │
└─────────────────────────┘
        ↓  [HANDOFF LOG #2]
┌─────────────────────────┐
│   AGENT 3: LOGISTICS    │  ← pandas (CSV) + LlamaIndex (PDF)
│   Inventory Check +     │    rapidfuzz for fuzzy matching
│   Protocol Retrieval    │
└─────────────────────────┘
        ↓  [HANDOFF LOG #3]
┌─────────────────────────┐
│   DASHBOARD (Gradio)    │  ← High-contrast Monochrome UI
│   Alert + Instructions  │    Works fully offline
└─────────────────────────┘
```

All three agents run sequentially. Every handoff is logged as structured JSON — visible in the UI for judges and operators.

---

## Component 1: Intake Agent (Whisper)

### What it does
Converts spoken emergency reports into clean text. Handles noisy environments (background crying, alarms, crowd noise) through Whisper's noise-robust architecture.

### Why `whisper-base`
- Size: ~140MB — fast to load
- CPU inference: 2–4 seconds for a 10-second audio clip
- Multilingual support built-in
- `fp16=False` flag disables GPU requirement entirely

### Code

```python
# agents/intake_agent.py
import whisper

model = whisper.load_model("base")

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribes audio file to text.
    fp16=False ensures CPU-only execution.
    """
    result = model.transcribe(audio_path, fp16=False)
    transcript = result["text"].strip()
    return transcript


def record_live(duration_seconds: int = 10, output_path: str = "temp_audio.wav"):
    """
    Records live audio from microphone.
    Fallback: user can also upload a pre-recorded file.
    """
    import sounddevice as sd
    import numpy as np
    import scipy.io.wavfile as wav

    SAMPLE_RATE = 16000
    print(f"Recording for {duration_seconds} seconds...")
    audio = sd.rec(
        int(duration_seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='int16'
    )
    sd.wait()
    wav.write(output_path, SAMPLE_RATE, audio)
    print("Recording complete.")
    return output_path
```

### Input Options for Demo
- 🎙️ Live microphone recording
- 📁 Upload `.wav` / `.mp3` file
- ⌨️ Manual text input (fallback for demos)

---

## Component 2: Triage Agent (LLaMA 3.2 3B)

### What it does
Reads the transcribed report and produces a structured JSON assessment: severity level, emergency type, and the specific resource or action needed.

### Why LLaMA 3.2 3B Q4_K_M GGUF
- Quantized to ~2GB RAM usage
- CPU inference: ~5–10 tokens/second (sufficient for this use case)
- Strong instruction-following for JSON output
- `n_threads=4` tunes to available CPU cores

### The Prompt (Critical — Tune This)

```python
TRIAGE_PROMPT = """You are an emergency triage AI operating in a disaster shelter.
Analyze the report below and respond ONLY with valid JSON. No preamble, no explanation.

Report: "{transcript}"

JSON format:
{{
  "severity": "CRITICAL or HIGH or MEDIUM or LOW",
  "emergency_type": "Medical or Trapped or Resource or Mental Health or Other",
  "key_need": "specific item or action (2-4 words max)",
  "summary": "one sentence summary of the situation",
  "reasoning": "one sentence explaining why this severity level"
}}"""
```

> **Key design choice:** `temperature=0.1` keeps output deterministic and structured. Higher temperatures cause JSON formatting failures.

### Code

```python
# agents/triage_agent.py
import json
from llama_cpp import Llama

llm = Llama(
    model_path="./models/llama-3.2-3b-instruct.Q4_K_M.gguf",
    n_ctx=2048,
    n_threads=4,       # set to your CPU core count
    n_gpu_layers=0,    # force CPU-only
    verbose=False
)

TRIAGE_PROMPT = """You are an emergency triage AI in a disaster shelter.
Analyze the report and respond ONLY with valid JSON. No extra text.

Report: "{transcript}"

{{
  "severity": "CRITICAL or HIGH or MEDIUM or LOW",
  "emergency_type": "Medical or Trapped or Resource or Mental Health or Other",
  "key_need": "specific item or action needed",
  "summary": "one sentence summary",
  "reasoning": "why this severity level"
}}"""

def triage(transcript: str) -> dict:
    prompt = TRIAGE_PROMPT.format(transcript=transcript)
    response = llm(
        prompt,
        max_tokens=300,
        temperature=0.1,
        stop=["}\n\n"]   # stop token to prevent rambling
    )
    raw = response['choices'][0]['text'].strip()

    # Safe JSON extraction
    try:
        # Find JSON block if model adds extra text
        start = raw.find('{')
        end = raw.rfind('}') + 1
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        # Fallback: safe default
        return {
            "severity": "HIGH",
            "emergency_type": "Other",
            "key_need": transcript[:50],
            "summary": transcript[:100],
            "reasoning": "JSON parse failed — defaulting to HIGH"
        }
```

### Severity Levels Defined

| Level | Criteria | UI Color |
|-------|----------|----------|
| CRITICAL | Life-threatening, immediate action | 🔴 Red |
| HIGH | Serious injury or urgent resource need | 🟠 Orange |
| MEDIUM | Non-urgent medical or moderate need | 🟡 Yellow |
| LOW | Minor request, informational | 🟢 Green |

---

## Component 3: Logistics Agent (CSV + PDF)

### Sub-task A: Inventory Check

Uses `pandas` for CSV lookup and `rapidfuzz` for fuzzy string matching — essential because voice transcription introduces spelling variations.

```python
# agents/logistics_agent.py (Part 1: Inventory)
import pandas as pd
from rapidfuzz import process, fuzz

df = pd.read_csv("data/inventory.csv")

def check_inventory(key_need: str) -> dict:
    """
    Fuzzy-matches key_need against inventory item names.
    Returns item details if found.
    """
    item_names = df['Item'].tolist()

    # Fuzzy match — handles "leg splint" vs "Leg Splints" vs "splint leg"
    best_match, score, idx = process.extractOne(
        key_need,
        item_names,
        scorer=fuzz.partial_ratio
    )

    if score >= 60:  # 60% match threshold
        row = df.iloc[idx]
        return {
            "found": True,
            "item": row['Item'],
            "quantity": int(row['Quantity']),
            "location": row['Bin Location'],
            "category": row['Category'],
            "available": int(row['Quantity']) > 0,
            "match_confidence": score
        }

    return {
        "found": False,
        "message": f"No inventory match found for: {key_need}",
        "suggestion": "Check with shelter coordinator"
    }
```

### Inventory CSV Format

```csv
Item,Quantity,Bin Location,Category
Leg Splint,4,A-1,Medical
Bandages,50,A-2,Medical
Tourniquets,10,A-1,Medical
Neck Brace,2,A-3,Medical
Water Bottles,200,B-3,Resources
Energy Bars,150,B-1,Resources
Blankets,30,C-1,Comfort
Baby Formula,20,C-2,Comfort
Flashlights,15,D-2,Equipment
First Aid Kit,8,A-4,Medical
```

---

### Sub-task B: Protocol Retrieval (Offline PDF)

Uses `LlamaIndex` to build a local vector index from first-aid PDFs at startup. Queries return relevant protocol steps without internet.

```python
# agents/logistics_agent.py (Part 2: PDF Protocols)
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import Settings

# Configure offline embedding model
Settings.embed_model = HuggingFaceEmbedding(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)
Settings.llm = None  # disable LlamaIndex's own LLM — we use llama-cpp

def build_protocol_index(pdf_dir: str = "./data/protocols/"):
    """
    Call once at startup. Builds vector index from all PDFs in directory.
    """
    documents = SimpleDirectoryReader(pdf_dir).load_data()
    index = VectorStoreIndex.from_documents(documents)
    return index.as_query_engine(similarity_top_k=3)

# Initialize at startup
query_engine = build_protocol_index()

def get_protocol(key_need: str) -> str:
    """
    Retrieves relevant first-aid steps from offline PDF knowledge base.
    """
    query = f"Step-by-step first aid instructions for: {key_need}"
    response = query_engine.query(query)
    return str(response)
```

> **Recommended PDF source:** St. John Ambulance First Aid Manual (public domain / freely available)  
> Place all PDFs in `./data/protocols/` — index covers all of them automatically.

---

## Component 4: Agent Orchestration & Handoff Logs

The handoff logger is the most impressive part of the demo. It makes the multi-agent flow **visible and auditable**.

```python
# utils/logger.py
import json
from datetime import datetime

handoff_log = []

def log_handoff(from_agent: str, to_agent: str, data: dict):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "from_agent": from_agent,
        "to_agent": to_agent,
        "payload": data
    }
    handoff_log.append(entry)
    print(f"\n[HANDOFF] {from_agent} ──→ {to_agent}")
    print(json.dumps(data, indent=2))
    return entry

def get_full_log():
    return json.dumps(handoff_log, indent=2)

def reset_log():
    handoff_log.clear()
```

### Full Pipeline Orchestrator

```python
# main_pipeline.py
from agents.intake_agent import transcribe_audio
from agents.triage_agent import triage
from agents.logistics_agent import check_inventory, get_protocol
from utils.logger import log_handoff, get_full_log, reset_log

def run_pipeline(audio_path: str = None, text_input: str = None):
    reset_log()

    # ── AGENT 1: INTAKE ──────────────────────────────
    if audio_path:
        transcript = transcribe_audio(audio_path)
    else:
        transcript = text_input

    log_handoff("INTAKE_AGENT", "TRIAGE_AGENT", {
        "transcript": transcript,
        "input_type": "voice" if audio_path else "text"
    })

    # ── AGENT 2: TRIAGE ──────────────────────────────
    triage_result = triage(transcript)
    log_handoff("TRIAGE_AGENT", "LOGISTICS_AGENT", triage_result)

    # ── AGENT 3: LOGISTICS ───────────────────────────
    inventory = check_inventory(triage_result["key_need"])
    protocol = get_protocol(triage_result["key_need"])

    log_handoff("LOGISTICS_AGENT", "DASHBOARD", {
        "inventory_result": inventory,
        "protocol_retrieved": protocol[:200] + "..."  # truncate for log
    })

    return {
        "transcript": transcript,
        "triage": triage_result,
        "inventory": inventory,
        "protocol": protocol,
        "full_log": get_full_log()
    }
```

---

## Component 5: Gradio Dashboard

High-contrast, dark theme. Designed for low-power emergency displays.

```python
# main.py
import gradio as gr
import json
from main_pipeline import run_pipeline

SEVERITY_ICONS = {
    "CRITICAL": "🔴 CRITICAL — IMMEDIATE ACTION REQUIRED",
    "HIGH":     "🟠 HIGH — URGENT RESPONSE NEEDED",
    "MEDIUM":   "🟡 MEDIUM — MONITOR AND ASSIST",
    "LOW":      "🟢 LOW — STANDARD ASSISTANCE"
}

def process_emergency(audio, text_input):
    if not audio and not text_input.strip():
        return "⚠️ Provide audio or text", "", "", "", ""

    result = run_pipeline(
        audio_path=audio if audio else None,
        text_input=text_input if not audio else None
    )

    severity_display = SEVERITY_ICONS.get(
        result['triage']['severity'], result['triage']['severity']
    )

    inv = result['inventory']
    if inv.get('found'):
        inventory_display = (
            f"✅ AVAILABLE\n"
            f"Item: {inv['item']}\n"
            f"Quantity: {inv['quantity']} units\n"
            f"Location: BIN {inv['location']}\n"
            f"Category: {inv['category']}"
        )
    else:
        inventory_display = f"❌ NOT IN INVENTORY\n{inv.get('message', '')}"

    return (
        severity_display,
        result['triage']['summary'],
        inventory_display,
        result['protocol'],
        result['full_log']
    )

with gr.Blocks(
    theme=gr.themes.Monochrome(),
    title="Emergency Intelligence Hub"
) as app:

    gr.Markdown("# 🚨 OFFLINE EMERGENCY INTELLIGENCE HUB")
    gr.Markdown("*Multi-agent triage system — works without internet*")

    with gr.Row():
        audio_input = gr.Audio(
            sources=["microphone", "upload"],
            type="filepath",
            label="🎙️ Voice Report"
        )
        text_input = gr.Textbox(
            label="⌨️ Or Type Report (fallback)",
            placeholder="Describe the emergency situation...",
            lines=4
        )

    submit_btn = gr.Button(
        "⚡ PROCESS EMERGENCY",
        variant="stop",
        size="lg"
    )

    gr.Markdown("---")
    gr.Markdown("## 📊 Assessment")

    with gr.Row():
        severity_out = gr.Textbox(label="SEVERITY LEVEL", lines=1)
        summary_out = gr.Textbox(label="SITUATION SUMMARY", lines=1)

    with gr.Row():
        inventory_out = gr.Textbox(label="📦 INVENTORY STATUS", lines=5)
        protocol_out = gr.Textbox(
            label="📋 FIRST AID PROTOCOL",
            lines=5
        )

    gr.Markdown("---")
    gr.Markdown("## 🔁 Agent Handoff Logs")
    logs_out = gr.Code(label="JSON Handoff Trail", language="json", lines=15)

    submit_btn.click(
        fn=process_emergency,
        inputs=[audio_input, text_input],
        outputs=[severity_out, summary_out, inventory_out, protocol_out, logs_out]
    )

if __name__ == "__main__":
    app.launch(server_name="0.0.0.0", server_port=7860)
```

---

## 4-Day Execution Plan

### Day 1 — Foundation & Intake Agent
- [ ] Set up Python virtual environment
- [ ] Install all dependencies (`pip install -r requirements.txt`)
- [ ] Download Whisper base model
- [ ] Download LLaMA 3.2 3B GGUF from HuggingFace
- [ ] Download `all-MiniLM-L6-v2` embedding model
- [ ] Build and test `intake_agent.py` end-to-end
- [ ] Test with noisy audio clip

### Day 2 — Triage + Logistics Agents
- [ ] Build `triage_agent.py` — test JSON output consistency
- [ ] Tune triage prompt for clean JSON (critical!)
- [ ] Create `inventory.csv` with 15–20 sample items
- [ ] Build inventory fuzzy-match logic
- [ ] Add first-aid PDFs to `./data/protocols/`
- [ ] Build and test `LlamaIndex` PDF query engine

### Day 3 — Orchestration + Dashboard
- [ ] Build `main_pipeline.py` — wire all 3 agents
- [ ] Implement handoff logger
- [ ] Build Gradio UI (`main.py`)
- [ ] Full end-to-end test with 5 different scenarios
- [ ] Fix edge cases (empty results, JSON parse failures)

### Day 4 — Polish + Demo Prep
- [ ] Test with Wi-Fi disabled (confirm fully offline)
- [ ] Prepare 5 demo scenarios (scripts ready to go)
- [ ] Record demo video with noisy background audio
- [ ] Write documentation on model choices / quantization
- [ ] Final latency benchmarks (target: <15s full pipeline on CPU)

---

## Models Reference

| Model | Size | Download |
|-------|------|----------|
| `whisper-base` | 140MB | Auto via `whisper.load_model("base")` |
| `llama-3.2-3b-instruct.Q4_K_M.gguf` | ~2.0GB | [HuggingFace — bartowski/Llama-3.2-3B-Instruct-GGUF](https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF) |
| `all-MiniLM-L6-v2` | 80MB | Auto via `HuggingFaceEmbedding(model_name=...)` |

**Total: ~2.3GB disk, ~4–5GB RAM at runtime**

---

## Requirements.txt

```
openai-whisper
llama-cpp-python
llama-index
llama-index-embeddings-huggingface
sentence-transformers
pandas
rapidfuzz
gradio>=4.0
sounddevice
numpy
scipy
```

---

## Demo Scenarios (Prepare These)

| Scenario | Voice Input | Expected Output |
|----------|-------------|-----------------|
| 1 | "Elderly woman, leg injury, can't move" | CRITICAL, Leg Splint, Bin A-1 |
| 2 | "Child is not breathing" | CRITICAL, CPR protocol |
| 3 | "Family needs water and food" | MEDIUM, Water + Food, Bin B-3 |
| 4 | "Person having panic attack" | HIGH, Mental Health protocol |
| 5 | "Need blankets for 3 people" | LOW, Blankets, Bin C-1 |

---

## Winning Factors Checklist

- [ ] Visible JSON agent handoff logs in UI
- [ ] Demo works with Wi-Fi fully disabled
- [ ] Noisy audio test included in demo
- [ ] High-contrast dark UI explicitly mentioned as emergency-optimized
- [ ] Graceful text fallback when voice fails
- [ ] All models pre-downloaded before demo day
- [ ] Latency under 15 seconds on laptop CPU
- [ ] Documentation covers quantization (Q4_K_M explanation)