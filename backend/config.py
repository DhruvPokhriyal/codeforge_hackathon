# backend/config.py
# Central configuration — modify flags here to change behaviour across the app.
# All paths, thresholds, and feature flags live here.
# Import: from config import DENOISER, CONFIDENCE_THRESHOLD, ...

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PROTOCOLS_DIR = DATA_DIR / "protocols"
INVENTORY_CSV = DATA_DIR / "inventory.csv"
MODELS_DIR = BASE_DIR / "models"
VECTOR_STORE = BASE_DIR / "vector_store"
LOGS_DIR = BASE_DIR / "logs"
TEMP_DIR = BASE_DIR / "temp"

# Ensure runtime directories exist on import
for _dir in (LOGS_DIR, TEMP_DIR, VECTOR_STORE, DATA_DIR, PROTOCOLS_DIR, MODELS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ── Denoiser ──────────────────────────────────────────────────────────────────
# "noisereduce" — stationary spectral subtraction (CPU, fast)
# "facebook"    — DNS64 deep-learning model (CPU, slower, higher quality)
DENOISER: str = os.getenv("DENOISER", "noisereduce")

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")  # base | small | medium

# ── RAG / LlamaIndex ──────────────────────────────────────────────────────────
EMBED_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
RAG_TOP_K: int = 5
CONFIDENCE_THRESHOLD: float = 0.8  # below this → vagueness resolver kicks in
# ── LLM (via Ollama) ─────────────────────────────────────────────────────────
OLLAMA_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str = "gemma3:1b"
LLM_MAX_TOKENS: int = 1200
LLM_TEMPERATURE: float = 0.15
LLM_CONTEXT_SIZE: int = 8192

# ── FastAPI / Uvicorn ─────────────────────────────────────────────────────────
API_HOST: str = "127.0.0.1"
API_PORT: int = 8000

# ── Priority Queue ───────────────────────────────────────────────────────────
# Multiplied against severity_score so time penalties are significant
# but cannot fully negate severity (100×1000 >> 60 min travel penalty).
SCALE_FACTOR: int = 1000

# ── Volunteer Dispatch ────────────────────────────────────────────────────────
VOLUNTEER_COUNT: int = 3  # V-01 through V-03
ESCALATION_INTERVAL_SECS: int = 60  # APScheduler job interval
