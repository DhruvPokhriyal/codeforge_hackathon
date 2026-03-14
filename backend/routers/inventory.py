# backend/routers/inventory.py
# GET  /inventory        — Full inventory with available/reserved/total
# GET  /inventory/buffer — Buffer inventory (overflow from returns)
# PUT  /inventory/refill — Trigger manual refill (daily or partial)
# POST /inventory/update — Add stock for an existing item (capacity enforced)
# POST /inventory/create — Create a new inventory item

from fastapi import APIRouter, HTTPException

from schemas import InventoryRefillRequest, InventoryUpdateRequest
from core import inventory as _inventory
from agents.logistics_agent import reload_inventory

router = APIRouter()


@router.get("/inventory")
async def get_inventory():
    return {"inventory": _inventory.get_all()}


@router.get("/inventory/buffer")
async def get_buffer():
    return {"buffer": _inventory.get_buffer()}


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
    result = _inventory.update_item(body.item, body.quantity)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    reload_inventory()
    return {
        "status": "updated",
        "item": body.item,
        "quantity": body.quantity,
        "inventory": _inventory.get_all(),
    }


@router.post("/inventory/create")
async def create_inventory_item(body: InventoryUpdateRequest):
    """Create a brand-new item with item as name and quantity as capacity (Available = Total = quantity)."""
    result = _inventory.create_item(body.item, body.quantity)
    reload_inventory()
    return {
        "status": "created",
        "item": body.item,
        "capacity": body.quantity,
        "inventory": _inventory.get_all(),
    }
