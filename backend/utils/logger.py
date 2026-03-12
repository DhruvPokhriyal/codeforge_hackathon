# backend/utils/logger.py
# Structured JSON Handoff Logger
#
# Records every agent-to-agent transition to logs/handoffs.jsonl.
# Log entries appear in the dashboard's expandable log panel.
#
# Public interface:
#   log_handoff(from_agent, to_agent, reason, payload) -> None
#
# Output format (one JSON object per line):
# {
#   "timestamp":  "14:32:09.441",
#   "from_agent": "RETRIEVAL_AGENT",
#   "to_agent":   "VAGUENESS_AGENT",
#   "reason":     "top_score=0.43 < threshold=0.8",
#   "payload":    { ... }
# }

import json
from datetime import datetime

from config import LOGS_DIR

# ── Configuration ──────────────────────────────────────────────────────────────

# Path to the handoffs log file (JSON Lines format)
# Each line is a separate JSON object for easy appending and streaming
# .jsonl extension indicates JSON Lines format
_HANDOFFS_LOG_FILE_PATH = LOGS_DIR / "handoffs.jsonl"


# ── Public API ────────────────────────────────────────────────────────────────

def log_handoff(
    from_agent: str,
    to_agent: str,
    reason: str,
    payload: dict,
) -> None:
    """
    Record a handoff event between agents in the pipeline.
    
    This function creates a structured log entry and appends it to the
    handoffs.jsonl file. These logs power the expandable handoff panel
    in the dashboard, allowing shelter managers to see exactly how the
    AI arrived at its recommendations.
    
    Log Entry Fields:
    ─────────────────────────────────────────────────────────────
    timestamp    : Exact time of handoff (HH:MM:SS.mmm)
    from_agent   : Agent that completed its task
    to_agent     : Agent that will process next
    reason       : Why the handoff occurred (thresholds, completion, etc.)
    payload      : Data being passed (varies by handoff type)
    ─────────────────────────────────────────────────────────────
    
    File Format: JSON Lines (.jsonl)
    ─────────────────────────────────────────────────────────────
    Each line is a complete JSON object. This format enables:
    • Append-only writes (no file locking issues)
    • Streaming reads (process line by line)
    • Easy import into log aggregators (Splunk, ELK, etc.)
    • Human readability (each entry on its own line)
    ─────────────────────────────────────────────────────────────
    
    Args:
        from_agent: Name of the agent transferring control
                   Examples:
                   - "AUDIO_INPUT"     → Initial audio received
                   - "DENOISER"         → Audio cleaning complete
                   - "INTAKE_AGENT"     → Transcription done
                   - "RETRIEVAL_AGENT"  → RAG chunks fetched
                   - "VAGUENESS_AGENT"  → Clarification needed
                   - "RAG_TRIAGE_AGENT" → Situations identified
                   - "LOGISTICS_AGENT"  → Inventory checked
        
        to_agent: Name of the agent receiving control
                 Examples same as from_agent, representing the next step
        
        reason: Human-readable explanation for the handoff
                Examples:
                - "top_score=0.43 < threshold=0.8" (vagueness trigger)
                - "chunks ready" (retrieval complete)
                - "audio cleaned" (denoising done)
                - "situations ready" (triage complete)
        
        payload: The data being passed to the next agent
                Varies by handoff type:
                - Intake → Retrieval: {"transcript": "..."}
                - Retrieval → Triage: {"chunk_count": 5}
                - Triage → Logistics: {"count": 3} (situations found)
                - Includes request_id, scores, or other context
    
    Returns:
        None: Writes to file system, no return value
    
    Example Log Entry:
    ─────────────────────────────────────────────────────────────
    {
        "timestamp": "14:32:09.441",
        "from_agent": "RETRIEVAL_AGENT",
        "to_agent": "VAGUENESS_AGENT",
        "reason": "top_score=0.43 < threshold=0.8",
        "payload": {
            "transcript": "need help with flooding",
            "top_score": 0.43
        }
    }
    ─────────────────────────────────────────────────────────────
    """
    # STEP 1: Construct the log entry with all relevant information
    # This creates a structured record that's both human-readable
    # and machine-parseable for the dashboard.
    log_entry = {
        # Timestamp with milliseconds for precise ordering and debugging
        # Format: HH:MM:SS.mmm (e.g., "14:32:09.441")
        # [:-3] removes last 3 digits (microseconds → milliseconds)
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        
        # Agent names are converted to uppercase for consistency in logs
        # This ensures "retrieval_agent", "RetrievalAgent", and "RETRIEVAL_AGENT"
        # all appear the same in the log file.
        "from_agent": from_agent.upper(),
        "to_agent": to_agent.upper(),
        
        # Reason for the handoff (helps with debugging and dashboard display)
        # Should be concise but informative (e.g., includes scores/thresholds)
        "reason": reason,
        
        # The actual data being passed between agents
        # This varies by handoff type and provides context for the next agent
        "payload": payload,
    }
    
    # STEP 2: Append the entry to the log file
    # Using 'a' (append) mode ensures we don't overwrite existing logs
    # The file is created automatically if it doesn't exist
    with _HANDOFFS_LOG_FILE_PATH.open("a", encoding="utf-8") as log_file:
        # Convert the entry to JSON and write it as a new line
        # Each log entry occupies exactly one line in the file
        # The newline character ensures proper separation between entries
        log_file.write(json.dumps(log_entry) + "\n")