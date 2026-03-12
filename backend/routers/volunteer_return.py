# backend/routers/volunteer_return.py
# POST /volunteer/return — Volunteer back at base
#
# Steps:
#   1. Validate volunteer_id exists and is BUSY
#   2. Restore returned items to inventory
#   3. Mark volunteer AVAILABLE, request RESOLVED
#   4. Re-run dispatch for next pending task
#   Returns freed volunteer, updated queue, volunteers, and inventory

from fastapi import APIRouter, HTTPException

from schemas import VolunteerReturnRequest, VolunteerReturnResponse
from core import VOLUNTEERS, volunteer_return, priority_queue
from utils.inventory_manager import InventoryManager

# Create router instance for volunteer return endpoints
router = APIRouter()

# Initialize inventory manager for stock operations
_inventory_manager = InventoryManager()


@router.post("/volunteer/return", response_model=VolunteerReturnResponse)
async def handle_volunteer_return(return_request: VolunteerReturnRequest):
    """
    Process a volunteer returning to base after completing a mission.
    
    This endpoint is called when a shelter manager clicks "Back at Base"
    for a volunteer. It handles the complete return workflow:
    
    1. Validation:
       - Verify volunteer exists
       - Ensure volunteer is actually BUSY (not already available)
    
    2. Inventory Restore:
       - Return any unused items to available stock
       - Decrement reserved quantities
    
    3. State Updates:
       - Mark volunteer as AVAILABLE for next assignment
       - Mark the associated request as RESOLVED
       - Record actual return time
    
    4. Auto-dispatch:
       - Immediately try to assign next pending request
       - Ensures no idle time if work is waiting
    
    Args:
        return_request: VolunteerReturnRequest containing:
            - volunteer_id: Which volunteer is returning (e.g., "V-01")
            - returned_items: List of items being returned
              Each item: {"item": str, "quantity": int}
    
    Returns:
        VolunteerReturnResponse containing:
            - freed_volunteer: ID of the volunteer now available
            - queue: Updated priority queue (for dashboard refresh)
            - volunteers: Updated volunteer states
            - inventory: Updated inventory after restores
    
    Raises:
        HTTPException 404: If volunteer_id not found
        HTTPException 409: If volunteer is not in BUSY state
    """
    # STEP 1: Validate volunteer exists
    volunteer_data = VOLUNTEERS.get(return_request.volunteer_id)
    if not volunteer_data:
        raise HTTPException(
            status_code=404, 
            detail=f"Volunteer {return_request.volunteer_id} not found"
        )
    
    # STEP 2: Validate volunteer is actually on a mission
    if volunteer_data["status"] != "BUSY":
        raise HTTPException(
            status_code=409, 
            detail=f"Volunteer {return_request.volunteer_id} is {volunteer_data['status']}, must be BUSY"
        )

    # STEP 3: Process the return
    # This core function handles:
    #   - Restoring items to inventory
    #   - Updating volunteer status to AVAILABLE
    #   - Marking request as RESOLVED
    #   - Re-running dispatch for next task
    volunteer_return(
        volunteer_id=return_request.volunteer_id,
        returned_items=return_request.returned_items,
        queue=priority_queue,
        inventory_mgr=_inventory_manager,
    )

    # STEP 4: Return comprehensive state update for dashboard
    return VolunteerReturnResponse(
        # Confirm which volunteer was freed
        freed_volunteer=return_request.volunteer_id,
        
        # Full sorted queue (for queue panel refresh)
        queue=priority_queue.get_sorted(),
        
        # All volunteers with current status (for volunteer panel)
        volunteers=[
            {"volunteer_id": volunteer_id, **volunteer_info}
            for volunteer_id, volunteer_info in VOLUNTEERS.items()
        ],
        
        # Updated inventory after returns (for inventory panel)
        inventory=_inventory_manager.get_all(),
    )