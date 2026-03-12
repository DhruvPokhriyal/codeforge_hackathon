from fastapi import APIRouter

from config import VOLUNTEER_COUNT, ESCALATION_INTERVAL_SECS


router = APIRouter()


@router.get("/settings/frontend")
async def get_frontend_settings():
    """
    Return configuration values used by the Electron renderer.

    This endpoint centralises literals that were previously hard-coded
    in the frontend so the UI can be fully driven by server settings.
    """
    return {
        "volunteer_count": VOLUNTEER_COUNT,
        "polling": {
            # Queue / volunteers poll cadence in milliseconds
            "queue_ms": ESCALATION_INTERVAL_SECS * 1000,
            "volunteers_ms": ESCALATION_INTERVAL_SECS * 1000,
            # Per-card timer tick in milliseconds
            "timers_ms": 1000,
        },
        "audio": {
            # Extensions the upload widget should allow
            "accepted_extensions": [".wav", ".mp3", ".flac", ".ogg", ".m4a"],
        },
        "ui_text": {
            "upload": {
                "drop_hint": "Click to upload or drag & drop",
                "invalid_file": "Invalid file. Please drop a supported audio file.",
                "no_file_selected": "Please select an audio file first.",
            },
            "processing": {
                "starting": "⏳ Denoising audio...",
                "steps": [
                    "⏳ Transcribing speech...",
                    "⏳ Running triage analysis...",
                    "⏳ Allocating resources...",
                ],
                "done": "✓ Processing complete.",
            },
        },
    }

