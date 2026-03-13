# backend/routers/queue.py
# GET /queue — Live heap-sorted request list
#
# Returns all requests in priority order (highest heap_key first).
# Frontend polls this endpoint every 3 seconds to refresh the queue panel.

from fastapi import APIRouter

from core import priority_queue

router = APIRouter()


@router.get("/queue")
async def get_queue():
    return {"queue": priority_queue.get_sorted()}
