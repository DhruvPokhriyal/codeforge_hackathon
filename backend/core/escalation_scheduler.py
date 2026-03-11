# backend/core/escalation_scheduler.py
# APScheduler Background Job — Urgency Escalation
#
# Runs every 60 seconds. For each PENDING request, calculates how many hours
# it has been waiting and applies cumulative priority boosts per severity schedule.
# Ensures that LOW-priority items eventually outrank CRITICAL ones if ignored.
#
# Public interface:
#   start_scheduler(queue) -> None   — call once in FastAPI startup event

import math
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import ESCALATION_INTERVAL_SECS

# Escalation schedule per severity:
# Each entry: (hours_since_request, key_boost, buffer_multiplier)
# Entries are applied cumulatively up to the current wait time.
ESCALATION_SCHEDULE: dict[str, list] = {
    "CRITICAL": [
        (0.067, 500, 1.0),  # ~4 min — brain damage threshold
    ],
    "HIGH": [
        (2, 20, 1.0),
        (4, 60, 1.2),
        (5, 150, 1.5),
    ],
    "MEDIUM": [
        (4, 10, 1.0),
        (8, 30, 1.2),
        (12, 80, 1.5),
    ],
    "LOW": [
        (6, 5, 1.0),
        (10, 15, 1.2),
        (13, 40, 1.5),
        (15, 100, 2.0),
    ],
}


def _compute_buffer(travel_time: int, resolution_time: int, multiplier: float) -> float:
    return (travel_time + resolution_time) * multiplier


def escalate_keys(queue) -> None:
    """Apply time-based urgency boosts to all PENDING requests."""
    now = datetime.now()
    for req in queue.get_sorted():
        if req.get("status") != "PENDING":
            continue

        severity = req["situations"][0]["severity"] if req.get("situations") else "LOW"
        t_req = datetime.fromisoformat(req["time_of_request"])
        hours_wait = (now - t_req).total_seconds() / 3600

        schedule = ESCALATION_SCHEDULE.get(severity, [])
        base_key = req["situations"][0]["heap_key"] if req.get("situations") else 0
        escalation = 0.0

        for threshold_h, boost, buf_mult in schedule:
            if hours_wait >= threshold_h:
                travel = req["situations"][0].get("travel_time_min", 10)
                res = req["situations"][0].get("resolution_time_min", 20)
                buffer = _compute_buffer(travel, res, buf_mult)
                escalation = boost + buffer  # take highest matching tier
            else:
                break  # schedule is cumulative up to current time

        new_key = base_key + escalation
        if new_key != req.get("heap_key", base_key):
            queue.update_key(req["request_id"], new_key)
            req["escalation_stage"] = req.get("escalation_stage", 0) + 1


_scheduler = BackgroundScheduler()


def start_scheduler(queue) -> None:
    """Register the escalation job and start the APScheduler instance."""
    _scheduler.add_job(
        lambda: escalate_keys(queue),
        trigger="interval",
        seconds=ESCALATION_INTERVAL_SECS,
        id="escalation_job",
    )
    _scheduler.start()
