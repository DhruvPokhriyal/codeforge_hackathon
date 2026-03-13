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

from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException

from schemas import ApproveRequest, ApproveResponse, OverrideRequest, OverrideResponse
from core import priority_queue, request_store, dispatch, VOLUNTEERS, inventory as _inventory
from config import SCALE_FACTOR


router = APIRouter()


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


@router.post("/approve/override", response_model=OverrideResponse)
async def approve_override(body: OverrideRequest):
    src = request_store.get(body.source_request_id)
    if not src:
        raise HTTPException(status_code=404, detail="Source request not found")

    manual = body.manual_override or {}
    condition = (manual.get("condition") or "Manual Override").strip()
    notes = (manual.get("notes") or "").strip()
    resources = manual.get("resources") or []

    if not condition:
        raise HTTPException(status_code=400, detail="Override condition is required")

    materials = []
    for r in resources:
        item = (r.get("item") or "").strip()
        qty = int(r.get("qty") or 0)
        if not item or qty <= 0:
            continue
        inv = next((x for x in _inventory.get_all() if x.get("Item") == item), None)
        avail = int(inv.get("Available", 0)) if inv else 0
        materials.append(
            {
                "item": item,
                "quantity": qty,
                "available": avail >= qty,
                "available_qty": avail,
                "bin": inv.get("bin_location", "?") if inv else "?",
            }
        )

    severity_score = 75
    travel_time = 10
    resolution_time = 20
    heap_key = float(severity_score * SCALE_FACTOR - (travel_time * 2) - resolution_time)

    new_request_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"
    override_situation = {
        "label": condition,
        "severity": "HIGH",
        "severity_score": severity_score,
        "travel_time_min": travel_time,
        "resolution_time_min": resolution_time,
        "confidence": 1.0,
        "materials": materials,
        "instructions": [notes] if notes else ["Follow manual override instructions"],
        "reasoning": "Manager manual override",
        "source_chunks": [],
        "selected": True,
        "heap_key": heap_key,
    }

    override_request = {
        "request_id": new_request_id,
        "time_of_request": datetime.now().isoformat(),
        "transcript": src.get("transcript", ""),
        "is_vague": False,
        "situations": [override_situation],
        "status": "PENDING",
        "heap_key": heap_key,
        "escalation_stage": 0,
        "handoff_logs": [
            {
                "step": "manual_override",
                "reason": f"Created from {body.source_request_id}",
            }
        ],
    }

    # Reserve inventory for override materials if available.
    for mat in materials:
        if mat.get("available"):
            _inventory.reserve(mat["item"], mat["quantity"])

    request_store.add(override_request)
    request_store.update(body.source_request_id, {"status": "OVERRIDDEN"})
    priority_queue.push(request_store.get(new_request_id))
    dispatch(priority_queue)

    return OverrideResponse(
        request_id=new_request_id,
        source_request_id=body.source_request_id,
        queue=[r for r in priority_queue.get_sorted()],
        volunteers=[{"volunteer_id": vid, **info} for vid, info in VOLUNTEERS.items()],
    )
