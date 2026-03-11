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

_LOG_FILE = LOGS_DIR / "handoffs.jsonl"


def log_handoff(
    from_agent: str,
    to_agent: str,
    reason: str,
    payload: dict,
) -> None:
    """Append a single handoff event to logs/handoffs.jsonl."""
    entry = {
        "timestamp":  datetime.now().strftime("%H:%M:%S.%f")[:-3],
        "from_agent": from_agent.upper(),
        "to_agent":   to_agent.upper(),
        "reason":     reason,
        "payload":    payload,
    }
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
