# backend/agents/intake_agent.py
# STEP 3 — Speech-to-Text via Whisper
#
# Transcribes a denoised .wav file to a plain-text string.
# Model is loaded lazily on first call and cached for the process lifetime.
# Uses openai-whisper, "base" model, fp16=False (CPU-safe).
#
# Public interface:
#   transcribe(audio_path: str) -> str
#     · audio_path — path to a clean .wav file (output of denoiser)
#     · returns    — stripped transcript string

import whisper

from config import WHISPER_MODEL

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(WHISPER_MODEL)
    return _model


def transcribe(audio_path: str) -> str:
    """
    Load Whisper model (lazy singleton) and transcribe audio_path.
    fp16=False ensures CPU-only operation without hardware precision errors.
    """
    model = _get_model()
    result = model.transcribe(audio_path, fp16=False)
    return result["text"].strip()
