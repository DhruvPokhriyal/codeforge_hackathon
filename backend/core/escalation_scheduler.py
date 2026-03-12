# backend/core/escalation_scheduler.py
# APScheduler Background Job — Urgency Escalation
#
# Runs every 60 seconds. For each PENDING request, calculates how many hours
# it has been waiting and applies cumulative priority boosts per severity schedule.
# Ensures that LOW-priority items eventually outrank CRITICAL ones if ignored.
#
# Public interface:
#   start_scheduler(queue) -> None   — call once in FastAPI startup event

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from config import ESCALATION_INTERVAL_SECS

# Escalation schedule per severity:
# Each entry: (hours_since_request, key_boost, buffer_multiplier)
# Entries are applied cumulatively up to the current wait time.
# 
# The logic: As time passes, requests get priority boosts based on how long they've waited
# This ensures that even low priority requests eventually get handled if ignored too long
ESCALATION_SCHEDULE: dict[str, list] = {
    "CRITICAL": [
        (0.067, 500, 1.0),  # ~4 min — brain damage threshold (medical analogy)
    ],
    "HIGH": [
        (2, 20, 1.0),       # After 2 hours: +20 priority
        (4, 60, 1.2),       # After 4 hours: additional +60 (total +80)
        (5, 150, 1.5),      # After 5 hours: additional +150 (total +230)
    ],
    "MEDIUM": [
        (4, 10, 1.0),       # After 4 hours: +10 priority
        (8, 30, 1.2),       # After 8 hours: additional +30 (total +40)
        (12, 80, 1.5),      # After 12 hours: additional +80 (total +120)
    ],
    "LOW": [
        (6, 5, 1.0),        # After 6 hours: +5 priority
        (10, 15, 1.2),      # After 10 hours: additional +15 (total +20)
        (13, 40, 1.5),      # After 13 hours: additional +40 (total +60)
        (15, 100, 2.0),     # After 15 hours: additional +100 (total +160)
    ],
}


def _compute_buffer(travel_time: int, resolution_time: int, multiplier: float) -> float:
    """
    Calculate a buffer value that scales with the total time needed for a request.
    
    This buffer is added to the priority boost to account for requests that
    require more time/effort to complete.
    
    Args:
        travel_time: Minutes to reach the location
        resolution_time: Minutes to resolve the situation
        multiplier: Scaling factor from the escalation schedule
    
    Returns:
        float: Buffer value to add to priority boost
    """
    return (travel_time + resolution_time) * multiplier


def escalate_keys(queue) -> None:
    """
    Apply time-based urgency boosts to all PENDING requests.
    
    This function runs periodically (every 60 seconds by default) and:
    1. Examines every pending request in the queue
    2. Calculates how long each request has been waiting
    3. Applies cumulative priority boosts based on wait time and severity
    4. Updates the request's heap key (priority) in the queue
    
    The escalation is cumulative - if a request has waited long enough to meet
    multiple thresholds, all boosts are applied (up to the highest matching tier).
    """
    # Get current time for calculating wait durations
    current_time = datetime.now()
    
    # Iterate through all requests in the queue
    for request in queue.get_sorted():
        # Only process requests that are still pending (not assigned/resolved)
        if request.get("status") != "PENDING":
            continue

        # STEP 1: Determine the severity level of this request
        # Default to LOW if no situations or severity specified
        severity = request["situations"][0]["severity"] if request.get("situations") else "LOW"
        
        # STEP 2: Calculate how long this request has been waiting
        request_time = datetime.fromisoformat(request["time_of_request"])
        hours_waited = (current_time - request_time).total_seconds() / 3600

        # STEP 3: Get the escalation schedule for this severity level
        schedule = ESCALATION_SCHEDULE.get(severity, [])
        
        # STEP 4: Get the base priority key from the first situation
        base_priority = request["situations"][0]["heap_key"] if request.get("situations") else 0
        
        # STEP 5: Calculate total escalation boost
        total_escalation = 0.0
        
        # Apply all thresholds that the wait time has surpassed
        # The schedule is ordered from earliest to latest threshold
        for threshold_hours, boost_amount, buffer_multiplier in schedule:
            if hours_waited >= threshold_hours:
                # This threshold has been reached - calculate boost with buffer
                travel_minutes = request["situations"][0].get("travel_time_min", 10)
                resolution_minutes = request["situations"][0].get("resolution_time_min", 20)
                buffer_value = _compute_buffer(travel_minutes, resolution_minutes, buffer_multiplier)
                total_escalation = boost_amount + buffer_value  # Use the highest matching tier
            else:
                # Stop processing once we hit a threshold not yet reached
                # (schedule is cumulative up to current time)
                break

        # STEP 6: Calculate new priority key (base + escalation)
        new_priority = base_priority + total_escalation
        
        # STEP 7: Update the request's priority if it changed
        # Only update if the new key is different from current (avoid unnecessary operations)
        if new_priority != request.get("heap_key", base_priority):
            queue.update_key(request["request_id"], new_priority)
            
            # Increment escalation counter for tracking how many times this request has been escalated
            request["escalation_stage"] = request.get("escalation_stage", 0) + 1


# Create a background scheduler instance (singleton)
# This runs independently of the main application thread
_scheduler = BackgroundScheduler()


def start_scheduler(queue) -> None:
    """
    Register the escalation job and start the APScheduler instance.
    
    This function should be called once during application startup
    (typically in a FastAPI startup event) to begin the periodic
    escalation of pending requests.
    
    Args:
        queue: The request queue instance to monitor and update
    """
    _scheduler.add_job(
        lambda: escalate_keys(queue),           # The function to run
        trigger="interval",                      # Run on a fixed interval
        seconds=ESCALATION_INTERVAL_SECS,         # How often to run (from config)
        id="escalation_job",                       # Unique identifier for this job
    )
    _scheduler.start()  # Start the background scheduler