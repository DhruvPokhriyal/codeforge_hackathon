# backend/core/dispatch_engine.py
# Volunteer Dispatch Engine
#
# Manages the AVAILABLE → BUSY state machine for volunteers.
# Volunteer count is dynamic — controlled via POST /volunteers/count.
# Assigns the highest-priority PENDING request to the first free volunteer.
# Timer is set to travel_time + resolution_time but does NOT auto-reassign
# when it hits 0 — the shelter head must manually click "Back at Base".
#
# Public interface:
#   VOLUNTEERS — dict[str, dict]  (shared mutable state for GET /volunteers)
#   get_free_volunteer() -> str | None
#   dispatch(queue) -> dict | None         — assign free vol to top PENDING
#   volunteer_return(volunteer_id, returned_items, queue, inventory_mgr) -> None
#   set_volunteer_count(n) -> None         — resize the volunteer pool
#   get_volunteer_count() -> int

from datetime import datetime, timedelta

from config import VOLUNTEER_COUNT

def _new_vol() -> dict:
    """Create a fresh AVAILABLE volunteer dict (avoids shared mutable lists)."""
    return {
        "status": "AVAILABLE",
        "request_id": None,
        "assigned_at": None,
        "expected_return": None,
        "items_taken": [],
    }

# ── Volunteer state store ─────────────────────────────────────────────────────
VOLUNTEERS: dict[str, dict] = {
    f"V-{i:02d}": _new_vol()
    for i in range(1, VOLUNTEER_COUNT + 1)
}


def set_volunteer_count(n: int) -> None:
    """Resize the volunteer pool to exactly *n* slots.
    New slots are AVAILABLE. Existing BUSY volunteers are never removed."""
    current = len(VOLUNTEERS)
    if n > current:
        for i in range(current + 1, n + 1):
            vid = f"V-{i:02d}"
            if vid not in VOLUNTEERS:
                VOLUNTEERS[vid] = _new_vol()
    elif n < current:
        # Remove only AVAILABLE volunteers from the tail
        ids = sorted(VOLUNTEERS.keys(), reverse=True)
        removed = 0
        for vid in ids:
            if len(VOLUNTEERS) - removed <= n:
                break
            if VOLUNTEERS[vid]["status"] == "AVAILABLE":
                del VOLUNTEERS[vid]
                removed += 1
    print(f"[DISPATCH] Volunteer count set to {len(VOLUNTEERS)}")


def get_volunteer_count() -> int:
    return len(VOLUNTEERS)


def get_free_volunteer() -> str | None:
    """Return the ID of the first AVAILABLE volunteer, or None."""
    for vid, info in VOLUNTEERS.items():
        if info["status"] == "AVAILABLE":
            return vid
    return None


def dispatch(queue) -> dict | None:
    """
    Assign the highest-priority PENDING request to a free volunteer.
    Returns {volunteer, request_id} on success, None if no pending or no free vol.
    """
    top = queue.peek_top_pending()
    if not top:
        return None
    free = get_free_volunteer()
    if not free:
        return None

    now = datetime.now()

    # Use the dominant selected situation; fall back to first situation
    selected = [s for s in top["situations"] if s.get("selected")]
    if not selected:
        selected = top["situations"][:1]

    # Guard: if there are still no situations, use safe defaults
    if not selected:
        travel = 10
        resolve = 20
    else:
        travel = selected[0]["travel_time_min"]
        resolve = selected[0]["resolution_time_min"]
    exp_return = (now + timedelta(minutes=travel + resolve)).strftime("%H:%M:%S")

    # Collect items that are available in inventory
    items_taken = [
        {"item": mat["item"], "quantity": mat["quantity"]}
        for s in selected
        for mat in s.get("materials", [])
        if mat.get("available")
    ]

    VOLUNTEERS[free].update(
        {
            "status": "BUSY",
            "request_id": top["request_id"],
            "assigned_at": now.strftime("%H:%M:%S"),
            "expected_return": exp_return,
            "items_taken": items_taken,
        }
    )
    queue.update(
        top["request_id"],
        {
            "status": "ASSIGNED",
            "assigned_volunteer": free,
            "assigned_at": now.strftime("%H:%M:%S"),
            "expected_return": exp_return,
            "items_taken": items_taken,
        },
    )
    return {"volunteer": free, "request_id": top["request_id"]}


def volunteer_return(
    volunteer_id: str,
    returned_items: list,
    queue,
    inventory_mgr,
) -> None:
    """
    Shelter head clicked 'Back at Base'.
    · Restores returned items to inventory
    · Marks volunteer AVAILABLE
    · Marks request RESOLVED
    · Does NOT auto-dispatch — the shelter head triggers next assignment.
    """
    req_id = VOLUNTEERS[volunteer_id]["request_id"]
    now = datetime.now().strftime("%H:%M:%S")

    for item in returned_items:
        inventory_mgr.restore(item["item"], item["quantity"])

    queue.update(
        req_id,
        {
            "status": "RESOLVED",
            "actual_return": now,
            "items_returned": returned_items,
        },
    )

    VOLUNTEERS[volunteer_id] = {
        "status": "AVAILABLE",
        "request_id": None,
        "assigned_at": None,
        "expected_return": None,
        "items_taken": [],
    }

    # NOTE: We intentionally do NOT auto-dispatch here.
    # The shelter head must manually trigger the next assignment.
