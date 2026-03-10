# 🚨 Offline Emergency Intelligence Hub

> **AI for Impact — 5-Day Sprint Challenge | Track 2: Disaster Relief**  
> A fully offline, CPU-only multi-agent emergency coordination system for disaster shelters.

---

## 📌 Problem Statement

During natural disasters, internet and cloud services fail first. Volunteers in shelters are overwhelmed, untrained for medical triage, and unable to locate resources quickly. This project turns a standard laptop into a **"digital lifeboat"** — a self-contained AI command center that works entirely offline.

---

## 🎯 What It Does

A volunteer speaks (or types) an emergency report. Three AI agents process it in sequence:

```
Voice/Text Input
      ↓
[AGENT 1: INTAKE]     → Transcribes voice using Whisper
      ↓
[AGENT 2: TRIAGE]     → Classifies severity via LLaMA 3.2 3B
      ↓
[AGENT 3: LOGISTICS]  → Checks CSV inventory + retrieves PDF protocol
      ↓
Dashboard Alert (Severity + Location + First-Aid Steps)
```

**Example:** A volunteer reports an elderly person trapped with a leg injury.  
**Output:** 🔴 CRITICAL alert, "Leg Splint" protocol from offline PDF, confirmed available at **Bin A-1**.

---

## 🏗️ Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Speech-to-Text | `openai-whisper` (base) | Noise-robust, CPU-friendly, 140MB |
| Triage LLM | `LLaMA 3.2 3B Q4_K_M GGUF` | ~2GB RAM, runs on CPU at ~8 tok/s |
| PDF Retrieval | `LlamaIndex` + `all-MiniLM-L6-v2` | Offline vector search, 80MB |
| Inventory | `pandas` + `rapidfuzz` | CSV fuzzy matching |
| UI | `Gradio` (Monochrome theme) | High-contrast, zero frontend code |
| Orchestration | Custom Python pipeline | Explicit JSON handoff logs |

**Total model size on disk: ~2.3 GB**

---

## 📁 Project Structure

```
emergency-hub/
│
├── main.py                  # Entry point — launches Gradio UI
├── agents/
│   ├── intake_agent.py      # Whisper transcription
│   ├── triage_agent.py      # LLM severity classification
│   └── logistics_agent.py   # Inventory + PDF protocol retrieval
│
├── models/
│   └── llama-3.2-3b-instruct.Q4_K_M.gguf   # Download separately
│
├── data/
│   ├── inventory.csv        # Shelter resource manifest
│   └── protocols/           # Offline first-aid PDFs
│       └── first_aid_manual.pdf
│
├── utils/
│   └── logger.py            # Agent handoff log formatter
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