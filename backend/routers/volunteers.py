# backend/routers/volunteers.py
# GET  /volunteers       — All volunteer statuses and countdown timers
# POST /volunteers/count — Dynamically set the number of active volunteers
#
# Returns the full VOLUNTEERS dict.
# Frontend polls this every 3 seconds to update Panel B (Volunteer Activity Board).

from fastapi import APIRouter, HTTPException

from schemas import VolunteerCountRequest
from core import VOLUNTEERS
from core.dispatch_engine import set_volunteer_count, get_volunteer_count

router = APIRouter()


@router.get("/volunteers")
async def get_volunteers():
    return {
        "volunteers": [
            {"volunteer_id": vid, **info} for vid, info in VOLUNTEERS.items()
        ]
    }


@router.post("/volunteers/count")
async def update_volunteer_count(body: VolunteerCountRequest):
    if body.count < 1:
        raise HTTPException(status_code=400, detail="Count must be >= 1")
    set_volunteer_count(body.count)
    return {
        "count": get_volunteer_count(),
        "volunteers": [
            {"volunteer_id": vid, **info} for vid, info in VOLUNTEERS.items()
        ],
    }
