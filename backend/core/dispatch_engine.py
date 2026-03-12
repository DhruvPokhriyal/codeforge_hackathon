# backend/core/dispatch_engine.py
# Volunteer Dispatch Engine
#
# Manages the AVAILABLE → BUSY state machine for 6 volunteers (V-01 to V-06).
# Assigns the highest-priority PENDING request to the first free volunteer.
# Timer is set to travel_time + resolution_time but does NOT auto-reassign
# when it hits 0 — the shelter head must manually click "Back at Base".
#
# Public interface:
#   VOLUNTEERS — dict[str, dict]  (shared mutable state for GET /volunteers)
#   get_free_volunteer() -> str | None
#   dispatch(queue) -> dict | None         — assign free vol to top PENDING
#   volunteer_return(volunteer_id, returned_items, queue, inventory_mgr) -> None

from datetime import datetime, timedelta

from config import VOLUNTEER_COUNT

# ── Volunteer state store ─────────────────────────────────────────────────────
# This dictionary tracks all volunteers and their current status
# Each volunteer has: status (AVAILABLE/BUSY), which request they're handling,
# when they were assigned, when they're expected back, and what items they took
VOLUNTEERS: dict[str, dict] = {
    f"V-{i:02d}": {
        "status": "AVAILABLE",           # Initial state: all volunteers free
        "request_id": None,               # No request assigned yet
        "assigned_at": None,               # No assignment time yet
        "expected_return": None,           # No expected return time yet
        "items_taken": [],                  # No items taken yet
    }
    for i in range(1, VOLUNTEER_COUNT + 1)  # Creates V-01, V-02, etc. based on config
}


def get_free_volunteer() -> str | None:
    """
    Find the first available volunteer.
    
    Returns:
        str: Volunteer ID (e.g., "V-01") if found
        None: If all volunteers are busy
    """
    # Loop through all volunteers in order (V-01, V-02, etc.)
    for volunteer_id, volunteer_info in VOLUNTEERS.items():
        # Check if this volunteer is AVAILABLE
        if volunteer_info["status"] == "AVAILABLE":
            return volunteer_id  # Return the first free one we find
    return None  # No volunteers available


def dispatch(queue) -> dict | None:
    """
    Try to assign the next pending request to an available volunteer.
    This is the core logic that matches requests to volunteers.
    
    Steps:
    1. Check if there's a pending request
    2. Check if there's a free volunteer
    3. Calculate expected return time based on travel + resolution time
    4. Record which items the volunteer took
    5. Update volunteer status to BUSY
    6. Update request status to ASSIGNED
    
    Returns:
        dict: Contains volunteer_id and request_id if assignment succeeded
        None: If no pending requests or no free volunteers
    """
    # STEP 1: Get the highest priority pending request
    top_request = queue.peek_top_pending()
    if not top_request:
        # No requests waiting to be assigned
        return None
    
    # STEP 2: Find a free volunteer
    available_volunteer = get_free_volunteer()
    if not available_volunteer:
        # All volunteers are busy right now
        return None

    # STEP 3: Record the current time for assignment tracking
    current_time = datetime.now()

    # STEP 4: Determine which situation we're handling
    # First try to find a situation marked as "selected" (user's choice)
    selected_situations = [s for s in top_request["situations"] if s.get("selected")]
    if not selected_situations:
        # If nothing is selected, just use the first situation
        selected_situations = top_request["situations"][:1]

    # STEP 5: Calculate when the volunteer should return
    # Total time = travel to site + time spent resolving the situation
    travel_duration = selected_situations[0]["travel_time_min"]
    resolution_duration = selected_situations[0]["resolution_time_min"]
    total_minutes = travel_duration + resolution_duration
    expected_return_time = (current_time + timedelta(minutes=total_minutes)).strftime("%H:%M:%S")

    # STEP 6: Figure out what items the volunteer needs to take
    # Only include items that are marked as available in inventory
    taken_items = [
        {"item": material["item"], "quantity": material["quantity"]}
        for situation in selected_situations
        for material in situation.get("materials", [])  # Each situation might need materials
        if material.get("available")  # Only take if the item is in stock
    ]

    # STEP 7: Update the volunteer's record to BUSY
    VOLUNTEERS[available_volunteer].update(
        {
            "status": "BUSY",                              # Volunteer is now occupied
            "request_id": top_request["request_id"],        # Remember which request they're handling
            "assigned_at": current_time.strftime("%H:%M:%S"),  # When they left
            "expected_return": expected_return_time,        # When they should be back
            "items_taken": taken_items,                      # What they took with them
        }
    )
    
    # STEP 8: Update the request's status to ASSIGNED
    queue.update(
        top_request["request_id"],
        {
            "status": "ASSIGNED",                           # Request is now being handled
            "assigned_volunteer": available_volunteer,       # Who's handling it
            "assigned_at": current_time.strftime("%H:%M:%S"),  # When it was assigned
            "expected_return": expected_return_time,         # When volunteer should return
            "items_taken": taken_items,                       # What items were taken
        },
    )
    
    # STEP 9: Return confirmation of the assignment
    return {
        "volunteer": available_volunteer, 
        "request_id": top_request["request_id"]
    }


def volunteer_return(
    volunteer_id: str,
    returned_items: list,
    queue,
    inventory_mgr,
) -> None:
    """
    Process a volunteer returning to base (manual trigger by shelter head).
    
    This function handles the complete return workflow:
    1. Find which request this volunteer was handling
    2. Return any unused items to inventory
    3. Mark the request as RESOLVED
    4. Mark the volunteer as AVAILABLE again
    5. Immediately try to assign the next pending request
    
    Args:
        volunteer_id: Which volunteer is returning (e.g., "V-01")
        returned_items: List of items being returned (may be empty)
        queue: The request queue (to update request status)
        inventory_mgr: Inventory manager (to return items to stock)
    """
    # STEP 1: Get the request ID this volunteer was handling
    associated_request_id = VOLUNTEERS[volunteer_id]["request_id"]
    
    # STEP 2: Record the current time for return tracking
    current_timestamp = datetime.now().strftime("%H:%M:%S")

    # STEP 3: Return all items to inventory
    # Each item in returned_items should have {"item": str, "quantity": int}
    for returned_item in returned_items:
        inventory_mgr.restore(returned_item["item"], returned_item["quantity"])

    # STEP 4: Update the request as RESOLVED (completed)
    queue.update(
        associated_request_id,
        {
            "status": "RESOLVED",                           # Request is now complete
            "actual_return": current_timestamp,              # When volunteer actually returned
            "items_returned": returned_items,                 # What items came back
        },
    )

    # STEP 5: Reset the volunteer to AVAILABLE state
    # This clears all assignment data and makes them ready for next task
    VOLUNTEERS[volunteer_id] = {
        "status": "AVAILABLE",           # Now free to take new assignments
        "request_id": None,               # No longer handling any request
        "assigned_at": None,               # Clear assignment time
        "expected_return": None,           # Clear expected return
        "items_taken": [],                  # Clear items they had taken
    }

    # STEP 6: Immediately try to assign the next pending task
    # This ensures we don't leave volunteers idle if there's work waiting
    dispatch(queue)  # Check if any requests are pending and assign if possible