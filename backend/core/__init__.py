# backend/core/__init__.py
# Exports the singleton instances shared across all routers.
# Import singletons from here — never instantiate directly in routers.

from .priority_queue import priority_queue
from .request_store import request_store
from .dispatch_engine import (
    VOLUNTEERS,
    dispatch,
    dispatch_all,
    volunteer_return,
    get_free_volunteer,
    set_volunteer_count,
    get_volunteer_count,
    init_dispatch,
)
from utils.inventory_manager import InventoryManager

# Shared inventory singleton — all routers must use this instance so that
# reserve/restore operations are visible across the full request lifecycle.
inventory = InventoryManager()

__all__ = [
    "priority_queue",
    "request_store",
    "inventory",
    "VOLUNTEERS",
    "dispatch",
    "dispatch_all",
    "volunteer_return",
    "get_free_volunteer",
    "set_volunteer_count",
    "get_volunteer_count",
    "init_dispatch",
]
