# backend/core/priority_queue.py
# Max-heap priority queue for emergency requests.
#
# Key formula (computed by rag_triage_agent):
#   heap_key = severity_score - (travel_time × 2) - resolution_time
#   Higher key = higher urgency = served first
#
# The heap stores (-heap_key, timestamp, request_id) so Python's min-heap
# behaves as a max-heap on the positive heap_key values.
#
# Public interface (via singleton `priority_queue`):
#   push(request: dict) -> None
#   peek_top_pending() -> dict | None    — returns highest PENDING request
#   get_sorted() -> list[dict]           — all requests, highest key first
#   update_key(request_id, new_key)      — called by escalation_scheduler
#   update(request_id, updates)          — called by dispatch_engine / routers

import heapq
from datetime import datetime


class PriorityQueue:
    def __init__(self):
        self._heap: list = []  # [(-heap_key, timestamp_str, request_id)]
        self._store: dict = {}  # request_id → request dict

    def push(self, request: dict) -> None:
        """Add a new request to the heap."""
        key = request["heap_key"]
        ts = request["time_of_request"]
        req_id = request["request_id"]
        heapq.heappush(self._heap, (-key, ts, req_id))
        self._store[req_id] = request

    def peek_top_pending(self) -> dict | None:
        """
        Return the highest-priority PENDING request without removing it.
        Skips ASSIGNED / RESOLVED requests in the heap.
        """
        for _neg_key, _ts, req_id in self._heap:
            req = self._store.get(req_id)
            if req and req.get("status") == "PENDING":
                return req
        return None

    def get_sorted(self) -> list:
        """Return all requests sorted by heap_key descending."""
        return [
            self._store[req_id]
            for _, _, req_id in sorted(self._heap)
            if req_id in self._store
        ]

    def update_key(self, request_id: str, new_key: float) -> None:
        """
        Update the heap key for a request and rebuild the heap.
        Called by escalation_scheduler every 60 seconds.
        Python's heapq has no decrease-key, so we rebuild from _store.
        """
        if request_id not in self._store:
            return
        self._store[request_id]["heap_key"] = new_key
        self._heap = [
            (-self._store[rid]["heap_key"], ts, rid)
            for _, ts, rid in self._heap
            if rid in self._store
        ]
        heapq.heapify(self._heap)

    def update(self, request_id: str, updates: dict) -> None:
        """Apply a partial dict update to a stored request (no heap rebuild)."""
        if request_id in self._store:
            self._store[request_id].update(updates)


# Singleton — share across all routers and the escalation scheduler
priority_queue = PriorityQueue()
