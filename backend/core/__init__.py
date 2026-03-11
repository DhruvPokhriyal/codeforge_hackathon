# backend/core/__init__.py
# Exports the singleton instances shared across all routers.
# Import singletons from here — never instantiate directly in routers.

from .priority_queue import priority_queue
from .request_store import request_store
from .dispatch_engine import VOLUNTEERS, dispatch, volunteer_return, get_free_volunteer

__all__ = [
    "priority_queue",
    "request_store",
    "VOLUNTEERS",
    "dispatch",
    "volunteer_return",
    "get_free_volunteer",
]
