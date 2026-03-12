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

# Path to the handoffs log file (JSON Lines format)
# Each line is a separate JSON object for easy appending and streaming
_HANDOFFS_LOG_FILE = LOGS_DIR / "handoffs.jsonl"


def log_handoff(
    from_agent: str,
    to_agent: str,
    reason: str,
    payload: dict,
) -> None:
    """
    Record a handoff event between agents in the pipeline.
    
    This function creates a structured log entry and appends it to the
    handoffs.jsonl file. Each entry captures:
    - When the handoff occurred (timestamp with milliseconds)
    - Which agent handed off control
    - Which agent received control
    - Why the handoff happened (e.g., threshold not met, clarification needed)
    - The payload/data being passed between agents
    
    The log file uses JSON Lines format (.jsonl) where each line is a complete
    JSON object. This format is ideal for:
    - Streaming/append-only writes
    - Easy parsing (read line by line)
    - Compatibility with log aggregation tools
    
    Args:
        from_agent: Name of the agent transferring control
                   (e.g., "RETRIEVAL_AGENT", "TRIAGE_AGENT")
        to_agent: Name of the agent receiving control
                 (e.g., "VAGUENESS_AGENT", "CLARIFICATION_AGENT")
        reason: Human-readable explanation for the handoff
               (e.g., "insufficient information", "needs severity assessment")
        payload: The data being passed to the next agent
                (varies based on handoff type - could be query, context, etc.)
    """
    # STEP 1: Construct the log entry with all relevant information
    log_entry = {
        # Timestamp with milliseconds for precise ordering (HH:MM:SS.mmm)
        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
        
        # Agent names are converted to uppercase for consistency in logs
        "from_agent": from_agent.upper(),
        "to_agent": to_agent.upper(),
        
        # Reason for the handoff (helps with debugging and dashboard display)
        "reason": reason,
        
        # The actual data being passed between agents
        "payload": payload,
    }
    
    # STEP 2: Append the entry to the log file
    # 'a' mode opens the file for appending (creates file if it doesn't exist)
    # UTF-8 encoding ensures proper handling of special characters
    with _HANDOFFS_LOG_FILE.open("a", encoding="utf-8") as log_file:
        # Convert the entry to JSON and write it as a new line
        # Adding newline ensures each entry is on its own line
        log_file.write(json.dumps(log_entry) + "\n")