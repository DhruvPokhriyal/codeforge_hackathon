# ⚙️ Setup Guide
## Libraries, Models & Installation — Offline Emergency Intelligence Hub

> ✅ After completing this guide your system runs **100% offline**.
> Internet only needed during this one-time setup.

---

## System Requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| RAM | 6 GB | 10 GB+ |
| CPU Cores | 4 | 8+ |
| Disk Space | 8 GB free | 12 GB free |
| Python | 3.9+ | 3.11 |
| Node.js | 18+ | 20 LTS |
| OS | Windows 10 / Ubuntu 20.04 / macOS 11 | Any |
| Internet | Only during setup | ❌ Not needed at runtime |

---

## Step 0 — Prerequisites

### Python 3.11
```bash
python --version   # check first

# Ubuntu/Debian
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip -y

# macOS
brew install python@3.11

# Windows → https://python.org/downloads
```

### Node.js 20 LTS
```bash
# Ubuntu (via nvm)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
nvm install 20 && nvm use 20

# macOS
brew install node@20

# Windows → https://nodejs.org/en/download
```

### System audio + ffmpeg
```bash
# Ubuntu
sudo apt install portaudio19-dev ffmpeg -y

# macOS
brew install ffmpeg

# Windows → https://ffmpeg.org/download.html (add bin/ to PATH)
```

---

## Step 1 — Clone & Virtual Environment

```bash
git clone https://github.com/your-team/emergency-hub.git
cd emergency-hub/backend

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
which python                   # confirm venv active
```

---

## Step 2 — Install Python Libraries

### Full requirements.txt

See `backend/requirements.txt` for the pinned dependency list (kept in sync with the active venv).

Key install notes:
- **torch** must be the CPU-only build: `pip install torch --index-url https://download.pytorch.org/whl/cpu`
- **llama-cpp-python** prebuilt CPU wheels: `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`
- **ffmpeg** is a **system package** required by Whisper (not installable via pip)

```bash
# Ubuntu — install ffmpeg first
sudo apt install -y ffmpeg

pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
pip install -r requirements.txt
```

> ⏱️ Takes 10–20 minutes. Downloads ~2.5 GB of packages including PyTorch.

### Verify installs
```bash
python -c "import whisper; print('whisper ✅')"
python -c "from llama_cpp import Llama; print('llama-cpp ✅')"
python -c "import noisereduce; print('noisereduce ✅')"
python -c "import fastapi; print('fastapi ✅')"
python -c "from llama_index.core import VectorStoreIndex; print('llama-index ✅')"
python -c "from apscheduler.schedulers.background import BackgroundScheduler; print('APScheduler ✅')"
ffmpeg -version 2>&1 | head -1   # system check
```

---

## Step 3 — Install Node Dependencies

```bash
npm install
```

Minimum `package.json`:
```json
{
  "name": "emergency-hub",
  "version": "1.0.0",
  "main": "electron/main.js",
  "scripts": {
    "start": "electron .",
    "build": "electron-builder"
  },
  "devDependencies": {
    "electron": "^31.0.0",
    "electron-builder": "^24.0.0"
  }
}
```

---

## Step 4 — Download AI Models

### Model 1: Whisper Base (auto on first use)
**Size:** 140 MB

```bash
python -c "import whisper; whisper.load_model('base'); print('Whisper base ✅')"
```

### Model 2: Gemma 3 1B Q5_K_M GGUF (manual)
**Size:** ~0.9 GB

```bash
mkdir -p models

python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
  repo_id='bartowski/gemma-3-1b-it-GGUF',
  filename='gemma-3-1b-it-Q5_K_M.gguf',
    local_dir='./models'
)
print('Gemma ✅')
"
```

**Alternative:**
```bash
wget -P ./models \
  "https://huggingface.co/bartowski/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q5_K_M.gguf"
```

### Model 3: all-MiniLM-L6-v2 (auto on first use)
**Size:** 80 MB

```bash
python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('MiniLM ✅')
"
```

### Model 4: Facebook Denoiser dns64 (auto on first use)
**Size:** ~90 MB

```bash
python -c "
from denoiser import pretrained
pretrained.dns64()
print('Facebook Denoiser ✅')
"
```

---

## Step 5 — Prepare Data Files

### Create directories
```bash
mkdir -p data/protocols temp vector_store logs
touch temp/.gitkeep logs/.gitkeep
touch backend/agents/__init__.py backend/core/__init__.py
touch backend/routers/__init__.py backend/utils/__init__.py
```

### inventory.csv
```bash
cat > data/inventory.csv << 'EOF'
Item,Available,Reserved,Total,Bin Location,Category
Leg Splint,4,0,4,A-1,Medical
AED,2,0,2,C-3,Medical
CPR Mask,5,0,5,A-4,Medical
Bandages,50,0,50,A-2,Medical
Tourniquets,10,0,10,A-1,Medical
Neck Brace,2,0,2,A-3,Medical
First Aid Kit,8,0,8,A-4,Medical
Oxygen Tank,1,0,1,B-1,Medical
Water Bottles,200,0,200,B-3,Resources
Energy Bars,150,0,150,B-1,Resources
Baby Formula,20,0,20,B-2,Resources
ORS Sachets,40,0,40,B-4,Resources
Blankets,30,0,30,C-1,Comfort
Flashlights,15,0,15,D-2,Equipment
Batteries AA,100,0,100,D-1,Equipment
EOF
```

### Add PDFs to `data/protocols/`

At least 1 PDF required for RAG to function.

| Source | Download Link |
|--------|--------------|
| WHO Basic Emergency Care | https://www.who.int/publications/i/item/basic-emergency-care |
| FEMA Disaster Guide | https://www.ready.gov/sites/default/files/2020-03/ready_are-you-ready-guide.pdf |

```bash
wget -P data/protocols/ \
  "https://www.ready.gov/sites/default/files/2020-03/ready_are-you-ready-guide.pdf"
```

---

## Step 6 — First Run

```bash
# Activate venv
source venv/bin/activate

# Launch (Electron auto-starts FastAPI)
npm start
```

On **first run** LlamaIndex builds the vector index from your PDFs (~30–60s). Subsequent runs are instant (index cached in `vector_store/`).

API explorer: `http://127.0.0.1:8000/docs`

---

## Complete Library Reference

### Python — AI / ML

| Library | Version | Purpose |
|---------|---------|---------|
| `openai-whisper` | 20231117 | Speech-to-text (CPU, fp16=False) |
| `noisereduce` | 3.0.2 | Stationary audio denoising |
| `denoiser` | 0.1.5 | Facebook dns64 neural denoiser |
| `torch` + `torchaudio` | 2.3.1 | Facebook denoiser dependency |
| `llama-cpp-python` | 0.2.90 | GGUF LLM on CPU (vagueness + triage) |
| `llama-index` | 0.10.68 | RAG framework (retrieval + vector store) |
| `llama-index-embeddings-huggingface` | 0.2.3 | HuggingFace embedding integration |
| `sentence-transformers` | 3.0.1 | all-MiniLM-L6-v2 embedding model |

### Python — Data + Backend

| Library | Version | Purpose |
|---------|---------|---------|
| `pandas` | 2.2.2 | Inventory CSV read/write |
| `rapidfuzz` | 3.9.7 | Fuzzy item name matching |
| `APScheduler` | 3.10.4 | Background escalation scheduler |
| `fastapi` | 0.111.0 | REST API |
| `uvicorn` | 0.30.1 | ASGI server |
| `scipy` | 1.13.1 | WAV file I/O |
| `numpy` | 1.26.4 | Audio array ops |

### Node

| Package | Version | Purpose |
|---------|---------|---------|
| `electron` | 31.x | Desktop shell |
| `electron-builder` | 24.x | Cross-platform packaging |

### Models

| Model | Location | Size | How Downloaded |
|-------|----------|------|----------------|
| `whisper-base` | `~/.cache/whisper/` | 140 MB | Auto |
| `gemma-3-1b-it-Q5_K_M.gguf` | `./models/` | ~0.9 GB | Manual (Step 4) |
| `all-MiniLM-L6-v2` | `~/.cache/huggingface/` | 80 MB | Auto |
| `facebook dns64` | `~/.cache/torch/hub/` | ~90 MB | Auto |

**Total download: ~2.5 GB · RAM at runtime: ~4–5 GB**

---

## Troubleshooting

### `llama-cpp-python` build fails
```bash
CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" \
pip install llama-cpp-python --no-cache-dir
```

### `torch` install too large / slow
```bash
pip install torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu
```

### LlamaIndex rebuild vector store
```bash
rm -rf vector_store/
python -c "from backend.agents.retrieval_agent import build_index; build_index()"
```

### APScheduler conflict at startup
```bash
pip install APScheduler==3.10.4 --force-reinstall
```

### Out of RAM during LLM inference
```python
# triage_agent.py — reduce context
llm = Llama(model_path="...", n_ctx=1024, n_threads=2, n_gpu_layers=0)
```

---

## Quick Reference — Daily Use

```bash
cd emergency-hub
source venv/bin/activate     # Linux/macOS
venv\Scripts\activate        # Windows
npm start                    # launches Electron + FastAPI together
# Disable Wi-Fi → still works fully ✅
```