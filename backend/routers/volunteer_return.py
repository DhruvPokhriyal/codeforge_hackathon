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

router = APIRouter()
_inventory = InventoryManager()


@router.post("/volunteer/return", response_model=VolunteerReturnResponse)
async def handle_volunteer_return(body: VolunteerReturnRequest):
    vol = VOLUNTEERS.get(body.volunteer_id)
    if not vol:
        raise HTTPException(status_code=404, detail="Volunteer not found")
    if vol["status"] != "BUSY":
        raise HTTPException(status_code=409, detail="Volunteer is not currently BUSY")

    volunteer_return(body.volunteer_id, body.returned_items, priority_queue, _inventory)

    return VolunteerReturnResponse(
        freed_volunteer=body.volunteer_id,
        queue=priority_queue.get_sorted(),
        volunteers=[{"volunteer_id": vid, **info} for vid, info in VOLUNTEERS.items()],
        inventory=_inventory.get_all(),
    )
