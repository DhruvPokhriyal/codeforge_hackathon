# backend/utils/audio_utils.py
# Audio helper utilities for pipeline pre/post-processing.
#
# Public interface:
#   save_base64_wav(audio_b64: str, request_id: str) -> str
#     · Decodes base64 audio and saves to temp/REQ-XXX_raw.wav
#     · Returns the file path
#
#   cleanup_temp(request_id: str) -> None
#     · Removes temp/REQ-XXX_raw.wav and temp/REQ-XXX_clean.wav

import base64
from pathlib import Path

from config import TEMP_DIR


def save_base64_wav(audio_b64: str, request_id: str) -> str:
    """
    Decode base64-encoded audio and write to a temp .wav file.
    Returns the absolute path to the saved file.
    """
    audio_bytes = base64.b64decode(audio_b64)
    out_path = TEMP_DIR / f"{request_id}_raw.wav"
    out_path.write_bytes(audio_bytes)
    return str(out_path)


def get_clean_path(request_id: str) -> str:
    """Return the expected path for the denoised output of a request."""
    return str(TEMP_DIR / f"{request_id}_clean.wav")


def cleanup_temp(request_id: str) -> None:
    """Remove both raw and clean temp files for a completed request."""
    for suffix in ("_raw.wav", "_clean.wav"):
        path = TEMP_DIR / f"{request_id}{suffix}"
        if path.exists():
            path.unlink()
