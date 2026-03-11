# backend/routers/inventory.py
# GET  /inventory        — Full inventory with available/reserved/total
# PUT  /inventory/refill — Trigger manual refill (daily or partial)

from fastapi import APIRouter

from schemas import InventoryRefillRequest
from utils.inventory_manager import InventoryManager

router = APIRouter()
_inventory = InventoryManager()


@router.get("/inventory")
async def get_inventory():
    return {"inventory": _inventory.get_all()}


@router.put("/inventory/refill")
async def refill_inventory(body: InventoryRefillRequest):
    if body.mode == "daily":
        _inventory.daily_refill()
    else:
        _inventory.partial_refill()
    return {"status": "refilled", "mode": body.mode, "inventory": _inventory.get_all()}
