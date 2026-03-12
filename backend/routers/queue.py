# backend/routers/queue.py
# GET /queue — Live heap-sorted request list
#
# Returns all requests in priority order (highest heap_key first).
# Frontend polls this endpoint every 3 seconds to refresh the queue panel.

from fastapi import APIRouter

from core import priority_queue

# Create router instance for queue endpoints
router = APIRouter()


@router.get("/queue")
async def get_queue():
    """
    Retrieve the current request queue sorted by priority.
    
    This endpoint returns all requests (PENDING, ASSIGNED, and RESOLVED)
    in descending order of urgency. The sorting is based on:
    
    1. Base heap_key (from severity - travel_time×2 - resolution_time)
    2. Plus escalation boosts from waiting time
    3. Higher key = higher urgency = appears first
    
    The frontend dashboard polls this endpoint every 3 seconds to:
    - Display the live queue of emergency requests
    - Show which requests are pending vs assigned
    - Track priority changes as requests escalate
    - Monitor overall system workload
    
    Returns:
        dict: Contains 'queue' key with list of all requests sorted by:
              - heap_key (descending - highest priority first)
              - For equal keys, order is determined by heap implementation
              
    Example response:
    {
        "queue": [
            {
                "request_id": "REQ-ABC123",
                "status": "PENDING",
                "heap_key": 95.5,
                "escalation_stage": 2,
                ...
            },
            ...
        ]
    }
    """
    # Get all requests sorted by priority (highest first)
    sorted_requests = priority_queue.get_sorted()
    
    # Return wrapped in response object
    # The frontend expects {"queue": [...]} structure
    return {"queue": sorted_requests}