# backend/routers/approve.py
# POST /approve — HITL manager approves situations and triggers dispatch
#
# Steps:
#   1. Validate request_id exists and is PENDING
#   2. Mark selected situations (or apply manual override)
#   3. Reserve inventory for selected situations atomically
#   4. Push request to priority heap
#   5. Run dispatch — assign free volunteer if available
#   Returns updated queue and volunteer state

from fastapi import APIRouter, HTTPException

from schemas import ApproveRequest, ApproveResponse
from core import priority_queue, request_store, dispatch, VOLUNTEERS
from utils.inventory_manager import InventoryManager

# Create router instance for approval endpoints
router = APIRouter()

# Initialize inventory manager for stock operations
_inventory_manager = InventoryManager()


@router.post("/approve", response_model=ApproveResponse)
async def approve_request(approval_data: ApproveRequest):
    """
    Human-in-the-loop approval endpoint for triage results.
    
    This endpoint is called when a shelter manager reviews and approves
    the AI-generated situations for an emergency request. It handles:
    
    1. Validation: Ensures the request exists and is still pending
    2. Selection: Marks which AI-proposed situations are approved
    3. Override: Allows manual creation of situations if needed
    4. Inventory: Reserves necessary items for approved situations
    5. Prioritization: Pushes to priority queue with correct heap key
    6. Dispatch: Immediately tries to assign a volunteer
    
    The response includes the updated queue and volunteer states for
    real-time dashboard updates.
    
    Args:
        approval_data: ApproveRequest schema containing:
            - request_id: The ID of the request being approved
            - selected_indices: Which situations are approved (by index)
            - manual_override: Optional manually-created situation
    
    Returns:
        ApproveResponse: Contains updated queue and volunteer status
    
    Raises:
        HTTPException 404: If request_id not found
        HTTPException 409: If request is not in PENDING state
    """
    # STEP 1: Validate request existence and state
    existing_request = request_store.get(approval_data.request_id)
    if not existing_request:
        raise HTTPException(
            status_code=404, 
            detail=f"Request {approval_data.request_id} not found"
        )
    
    if existing_request.get("status") != "PENDING":
        raise HTTPException(
            status_code=409, 
            detail=f"Request is {existing_request.get('status')}, must be PENDING"
        )

    # Extract situations from the request
    request_situations = existing_request["situations"]

    # STEP 2: Mark selected situations as approved
    # Loop through all situations and mark selected ones based on indices
    for situation_index, situation_data in enumerate(request_situations):
        situation_data["selected"] = situation_index in approval_data.selected_indices

    # STEP 3: Handle manual override if provided
    if approval_data.manual_override:
        # Create a new situation from manual override data
        override_situation = {
            "label": approval_data.manual_override.get("condition", "Manual Override"),
            "severity": "HIGH",  # Default severity for overrides
            "severity_score": 75,  # Default score (matches HIGH severity)
            "travel_time_min": 10,  # Default travel time estimate
            "resolution_time_min": 20,  # Default resolution time estimate
            "confidence": 1.0,  # Maximum confidence for manual override
            "materials": [
                {
                    "item": item_name,
                    "quantity": 1,  # Default quantity per item
                    "available": False,  # Initially marked unavailable
                    "available_qty": 0,  # No stock checked yet
                    "bin": "?",  # Unknown bin location
                }
                for item_name in approval_data.manual_override.get("items", [])
            ],
            "instructions": ["Follow manual override instructions"],
            "reasoning": "Manager manual override",
            "source_chunks": [],  # No source chunks for manual entries
            "selected": True,  # Override is automatically selected
            # Calculate heap key: severity_score - (travel×2) - resolution
            "heap_key": 75 - 20 - 20,  # 75 - 40 = 35 (medium-high priority)
        }
        request_situations.append(override_situation)

    # STEP 4: Reserve inventory for all selected situations
    # Filter to only approved situations
    approved_situations = [sit for sit in request_situations if sit.get("selected")]
    
    # Loop through all materials in approved situations
    for situation in approved_situations:
        for material in situation.get("materials", []):
            # Only reserve if the item is marked as available
            if material.get("available"):
                _inventory_manager.reserve(
                    material["item"], 
                    material["quantity"]
                )

    # STEP 5: Update request priority based on best selected situation
    # Find the highest heap_key among approved situations
    best_priority_key = max(
        (situation["heap_key"] for situation in approved_situations),
        default=existing_request["heap_key"],  # Fallback to existing if none selected
    )
    
    # Update the request in the store
    request_store.update(
        approval_data.request_id, 
        {
            "heap_key": best_priority_key,
            "situations": request_situations
        }
    )

    # STEP 6: Push to priority queue and attempt dispatch
    # Get the updated request from store
    updated_request = request_store.get(approval_data.request_id)
    
    # Add to priority queue
    priority_queue.push(updated_request)
    
    # Try to assign to an available volunteer
    dispatch(priority_queue)

    # STEP 7: Return updated state for dashboard
    return ApproveResponse(
        request_id=approval_data.request_id,
        # Return full sorted queue (all requests in priority order)
        queue=[request for request in priority_queue.get_sorted()],
        # Return all volunteers with their current status
        volunteers=[
            {"volunteer_id": volunteer_id, **volunteer_info}
            for volunteer_id, volunteer_info in VOLUNTEERS.items()
        ],
    )