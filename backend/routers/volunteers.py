# backend/routers/volunteers.py
# GET /volunteers — All volunteer statuses and countdown timers
#
# Returns the full VOLUNTEERS dict.
# Frontend polls this every 3 seconds to update Panel B (Volunteer Activity Board).

from fastapi import APIRouter

from core.dispatch_engine import VOLUNTEERS

router = APIRouter()


@router.get("/volunteers")
async def get_volunteers():
    return {
        "volunteers": [
            {"volunteer_id": vid, **info} for vid, info in VOLUNTEERS.items()
        ]
    }
