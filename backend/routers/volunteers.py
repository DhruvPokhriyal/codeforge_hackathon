# backend/routers/volunteers.py
# GET /volunteers — All volunteer statuses and countdown timers
#
# Returns the full VOLUNTEERS dict.
# Frontend polls this every 3 seconds to update Panel B (Volunteer Activity Board).

from fastapi import APIRouter

from core import VOLUNTEERS

# Create router instance for volunteer status endpoints
router = APIRouter()


@router.get("/volunteers")
async def get_volunteers():
    """
    Retrieve current status of all volunteers.
    
    This endpoint returns real-time information about each volunteer:
    
    Volunteer States:
    - AVAILABLE: Ready for new assignment
    - BUSY: Currently on a mission
      - Shows assigned request ID
      - Shows expected return time (countdown)
      - Shows items taken on mission
    
    Data Structure (per volunteer):
    {
        "volunteer_id": "V-01",           # Unique identifier
        "status": "AVAILABLE | BUSY",      # Current state
        "request_id": "REQ-ABC123",        # Active mission (if BUSY)
        "assigned_at": "14:32:09",          # When mission started
        "expected_return": "15:02:09",      # Countdown target
        "items_taken": [...]                 # Items checked out
    }
    
    The frontend dashboard polls this every 3 seconds to:
    - Display volunteer availability (Panel B)
    - Show countdown timers for active missions
    - Update when volunteers become free
    - Track which items are out on missions
    
    Returns:
        dict: Contains 'volunteers' key with list of all volunteers
              and their complete state information
              
    Example response:
    {
        "volunteers": [
            {
                "volunteer_id": "V-01",
                "status": "BUSY",
                "request_id": "REQ-ABC123",
                "assigned_at": "14:32:09",
                "expected_return": "15:02:09",
                "items_taken": [
                    {"item": "Bandages", "quantity": 5},
                    {"item": "Water", "quantity": 2}
                ]
            },
            {
                "volunteer_id": "V-02",
                "status": "AVAILABLE",
                "request_id": None,
                "assigned_at": None,
                "expected_return": None,
                "items_taken": []
            },
            ...
        ]
    }
    """
    # Transform the VOLUNTEERS dictionary into a list format
    # Each item becomes: {"volunteer_id": "V-01", "status": "AVAILABLE", ...}
    volunteer_list = [
        {"volunteer_id": volunteer_id, **volunteer_info}
        for volunteer_id, volunteer_info in VOLUNTEERS.items()
    ]
    
    # Return wrapped in response object
    # The frontend expects {"volunteers": [...]} structure
    return {"volunteers": volunteer_list}