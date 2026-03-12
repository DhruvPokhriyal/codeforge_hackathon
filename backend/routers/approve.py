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

router = APIRouter()
_inventory = InventoryManager()


@router.post("/approve", response_model=ApproveResponse)
async def approve_request(body: ApproveRequest):
    req = request_store.get(body.request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="Request is not in PENDING state")

    situations = req["situations"]

    # Mark selected situations
    for i, sit in enumerate(situations):
        sit["selected"] = i in body.selected_indices

    # Apply manual override if provided
    if body.manual_override:
        override_sit = {
            "label": body.manual_override.get("condition", "Manual Override"),
            "severity": "HIGH",
            "severity_score": 75,
            "travel_time_min": 10,
            "resolution_time_min": 20,
            "confidence": 1.0,
            "materials": [
                {
                    "item": itm,
                    "quantity": 1,
                    "available": False,
                    "available_qty": 0,
                    "bin": "?",
                }
                for itm in body.manual_override.get("items", [])
            ],
            "instructions": ["Follow manual override instructions"],
            "reasoning": "Manager manual override",
            "source_chunks": [],
            "selected": True,
            "heap_key": 75 - 20 - 20,
        }
        situations.append(override_sit)

    # Reserve inventory for all selected situations
    selected = [s for s in situations if s.get("selected")]
    for sit in selected:
        for mat in sit.get("materials", []):
            if mat.get("available"):
                _inventory.reserve(mat["item"], mat["quantity"])

    # Update heap_key to use the best selected situation
    best_key = max(
        (s["heap_key"] for s in selected),
        default=req["heap_key"],
    )
    request_store.update(
        body.request_id, {"heap_key": best_key, "situations": situations}
    )

    # Push to priority heap and dispatch
    priority_queue.push(request_store.get(body.request_id))
    dispatch(priority_queue)

    return ApproveResponse(
        request_id=body.request_id,
        queue=[r for r in priority_queue.get_sorted()],
        volunteers=[{"volunteer_id": vid, **info} for vid, info in VOLUNTEERS.items()],
    )
