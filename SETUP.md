# ⚙️ Setup Guide
## Libraries, Models & Installation — Offline Emergency Intelligence Hub

> ✅ After completing this guide, your system will run **100% offline**.
> Internet is only needed during this one-time setup.

---

## System Requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| RAM | 6 GB | 8 GB+ |
| CPU Cores | 4 | 8+ |
| Disk Space | 6 GB free | 10 GB free |
| Python | 3.9+ | 3.11 |
| OS | Windows 10 / Ubuntu 20.04 / macOS 11 | Any |
| Internet | Only during setup | ❌ Not needed at runtime |

---

## Step 0 — Prerequisites

### Install Python 3.11
```bash
# Check your version first
python --version

# Ubuntu/Debian
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip -y

# macOS (via Homebrew)
brew install python@3.11

# Windows — download from https://python.org/downloads
```

### Install system audio libraries (Linux only)
```bash
sudo apt install portaudio19-dev ffmpeg -y
```

### Install ffmpeg (macOS)
```bash
brew install ffmpeg
```

### Install ffmpeg (Windows)
Download from https://ffmpeg.org/download.html and add to PATH.

---

## Step 1 — Create Project & Virtual Environment

```bash
# Create project folder
mkdir emergency-hub
cd emergency-hub

# Create virtual environment
python -m venv venv

# Activate it
# Linux / macOS:
source venv/bin/activate

# Windows:
venv\Scripts\activate

# Confirm activation (should show venv path)
which python
```

> ⚠️ Always activate the virtual environment before running anything.

---

## Step 2 — Install All Libraries

### Create `requirements.txt`

Paste this into `requirements.txt` in your project root:

```txt
# Speech to Text
openai-whisper==20231117

# LLM Inference (CPU)
llama-cpp-python==0.2.90

# PDF Vector Search
llama-index==0.10.68
llama-index-embeddings-huggingface==0.2.3

# Embeddings
sentence-transformers==3.0.1

# Data & Fuzzy Matching
pandas==2.2.2
rapidfuzz==3.9.7

# UI
gradio==4.42.0

# Audio Recording
sounddevice==0.4.7
scipy==1.13.1
numpy==1.26.4
```

### Install everything
```bash
pip install -r requirements.txt
```

> ⏱️ This will take 5–15 minutes depending on internet speed. (~1.5GB download)

### Verify key installs
```bash
python -c "import whisper; print('Whisper OK')"
python -c "from llama_cpp import Llama; print('llama-cpp OK')"
python -c "import gradio; print('Gradio OK')"
python -c "from llama_index.core import VectorStoreIndex; print('LlamaIndex OK')"
```

All four should print `OK`.

---

## Step 3 — Download AI Models

### Model 1: Whisper Base (Speech-to-Text)
**Size:** ~140MB | **Auto-downloads** on first use

```bash
python -c "import whisper; whisper.load_model('base'); print('Whisper base downloaded!')"
```

The model saves to `~/.cache/whisper/` automatically.

---

### Model 2: LLaMA 3.2 3B GGUF (Triage LLM)
**Size:** ~2.0GB | **Manual download required**

```bash
# Create models directory
mkdir -p models

# Option A — Download via huggingface-hub (recommended)
pip install huggingface-hub
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='bartowski/Llama-3.2-3B-Instruct-GGUF',
    filename='Llama-3.2-3B-Instruct-Q4_K_M.gguf',
    local_dir='./models'
)
print('LLaMA downloaded!')
"
```

```bash
# Option B — Direct wget (Linux/macOS)
wget -P ./models "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
```

For Windows — open this URL in browser and save to `./models/`:
```
https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf
```

**Verify:**
```bash
ls -lh models/
# Should show: Llama-3.2-3B-Instruct-Q4_K_M.gguf  ~2.0G
```

---

### Model 3: all-MiniLM-L6-v2 (PDF Embeddings)
**Size:** ~80MB | **Auto-downloads** on first use

```bash
python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('MiniLM downloaded!')
"
```

Saves to `~/.cache/huggingface/` automatically.

---

## Step 4 — Prepare Data Files

### Create folder structure
```bash
mkdir -p data/protocols
mkdir -p temp
mkdir -p utils
mkdir -p agents
```

### Create `data/inventory.csv`
```bash
cat > data/inventory.csv << 'EOF'
Item,Quantity,Bin Location,Category
Leg Splint,4,A-1,Medical
Bandages,50,A-2,Medical
Tourniquets,10,A-1,Medical
Neck Brace,2,A-3,Medical
First Aid Kit,8,A-4,Medical
CPR Mask,5,A-4,Medical
Water Bottles,200,B-3,Resources
Energy Bars,150,B-1,Resources
Baby Formula,20,B-2,Resources
Oral Rehydration Salts,40,B-4,Resources
Blankets,30,C-1,Comfort
Sleeping Bags,15,C-2,Comfort
Flashlights,15,D-2,Equipment
Batteries AA,100,D-1,Equipment
Whistle,20,D-3,Equipment
EOF
```

### Add First Aid PDFs to `data/protocols/`
Download any of these free, public-domain resources:

| Resource | Link |
|----------|------|
| WHO Basic Emergency Care | https://www.who.int/publications/i/item/basic-emergency-care |
| Red Cross First Aid Manual | Search "Red Cross First Aid PDF free download" |
| FEMA Disaster Preparedness | https://www.ready.gov/sites/default/files/2020-03/ready_are-you-ready-guide.pdf |

```bash
# Example: Download FEMA guide
wget -P data/protocols/ "https://www.ready.gov/sites/default/files/2020-03/ready_are-you-ready-guide.pdf"
```

> You need **at least one PDF** in `data/protocols/` for the logistics agent to work.

---

## Step 5 — Create `__init__.py` Files

```bash
touch agents/__init__.py
touch utils/__init__.py
```

---

## Step 6 — Verify Full Offline Setup

**Disable Wi-Fi**, then run this test:

```bash
python -c "
import whisper
from llama_cpp import Llama
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
import pandas as pd
from rapidfuzz import fuzz
import gradio as gr

print('✅ All imports successful')
print('✅ System is ready for offline use')
"
```

---

## Step 7 — First Run

```bash
python main.py
```

On first run, LlamaIndex will build the vector index from your PDFs.
This takes ~30–60 seconds. Subsequent runs are instant (index is cached).

Open browser at: `http://localhost:7860`

---

## Complete Library Reference

### Core AI Libraries

| Library | Version | Purpose | Size |
|---------|---------|---------|------|
| `openai-whisper` | 20231117 | Speech-to-text (Agent 1) | 140MB model |
| `llama-cpp-python` | 0.2.90 | Run GGUF LLMs on CPU (Agent 2) | — |
| `llama-index` | 0.10.68 | PDF vector search orchestration (Agent 3) | — |
| `llama-index-embeddings-huggingface` | 0.2.3 | HuggingFace embedding bridge | — |
| `sentence-transformers` | 3.0.1 | MiniLM embedding model (Agent 3) | 80MB model |

### Data & Matching

| Library | Version | Purpose |
|---------|---------|---------|
| `pandas` | 2.2.2 | Read and query `inventory.csv` |
| `rapidfuzz` | 3.9.7 | Fuzzy string matching for inventory lookup |
| `numpy` | 1.26.4 | Numerical operations (whisper dependency) |

### UI & Audio

| Library | Version | Purpose |
|---------|---------|---------|
| `gradio` | 4.42.0 | Web-based dashboard UI |
| `sounddevice` | 0.4.7 | Live microphone recording |
| `scipy` | 1.13.1 | Save `.wav` files from mic input |

### Models Summary

| Model | File/Cache Location | Size | Download Method |
|-------|---------------------|------|-----------------|
| Whisper Base | `~/.cache/whisper/base.pt` | 140MB | Auto on first run |
| LLaMA 3.2 3B Q4_K_M | `./models/Llama-3.2-3B-Instruct-Q4_K_M.gguf` | ~2.0GB | Manual (Step 3) |
| all-MiniLM-L6-v2 | `~/.cache/huggingface/...` | 80MB | Auto on first run |

**Total download: ~2.3GB**
**Total RAM at runtime: ~4–5GB**

---

## Troubleshooting

### `llama-cpp-python` install fails
```bash
# Install with no binary (build from source)
CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" \
pip install llama-cpp-python --no-cache-dir
```

### `sounddevice` PortAudio error (Linux)
```bash
sudo apt install portaudio19-dev -y
pip install sounddevice --force-reinstall
```

### Whisper ffmpeg error
```bash
# Ubuntu
sudo apt install ffmpeg -y
# macOS
brew install ffmpeg
```

### LlamaIndex rebuild vector store
```bash
# Delete and rebuild
rm -rf vector_store/
python -c "from agents.logistics_agent import build_protocol_index; build_protocol_index()"
```

### Out of memory during LLM inference
Edit `triage_agent.py` and reduce context:
```python
llm = Llama(model_path="...", n_ctx=1024, n_threads=2)  # reduce ctx and threads
```

---

## Quick Reference — Daily Use

```bash
# 1. Navigate to project
cd emergency-hub

# 2. Activate virtual environment
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# 3. Run
python main.py

# 4. Open in browser
# http://localhost:7860

# 5. Disable Wi-Fi — everything still works ✅
```