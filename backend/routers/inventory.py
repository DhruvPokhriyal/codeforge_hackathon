# backend/routers/inventory.py
# GET  /inventory        — Full inventory with available/reserved/total
# PUT  /inventory/refill — Trigger manual refill (daily or partial)
# POST /inventory/update — Add stock for an item (or create new item)

from fastapi import APIRouter

from schemas import InventoryRefillRequest, InventoryUpdateRequest
from core import inventory as _inventory
from agents.logistics_agent import reload_inventory

router = APIRouter()


@router.get("/inventory")
async def get_inventory():
    return {"inventory": _inventory.get_all()}


@router.put("/inventory/refill")
async def refill_inventory(body: InventoryRefillRequest):
    if body.mode == "daily":
        _inventory.daily_refill()
    else:
        _inventory.partial_refill()
    reload_inventory()
    return {"status": "refilled", "mode": body.mode, "inventory": _inventory.get_all()}


@router.post("/inventory/update")
async def update_inventory(body: InventoryUpdateRequest):
    _inventory.update_item(body.item, body.quantity)
    reload_inventory()
    return {"status": "updated", "item": body.item, "quantity": body.quantity, "inventory": _inventory.get_all()}
