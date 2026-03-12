# backend/routers/inventory.py
# GET  /inventory        — Full inventory with available/reserved/total
# PUT  /inventory/refill — Trigger manual refill (daily or partial)

from fastapi import APIRouter

from schemas import InventoryRefillRequest
from utils.inventory_manager import InventoryManager

# Create router instance for inventory endpoints
router = APIRouter()

# Initialize the inventory manager singleton
# This handles all CSV read/write operations and fuzzy matching
_inventory_manager = InventoryManager()


@router.get("/inventory")
async def get_inventory():
    """
    Retrieve the complete current inventory state.
    
    This endpoint returns all items in the inventory with their:
    - Available quantity (currently in stock)
    - Reserved quantity (allocated to active missions)
    - Total quantity (full capacity)
    - Bin location (physical storage location)
    - Category (item type classification)
    
    Used by:
    - Dashboard to display current stock levels
    - Approve flow to check item availability
    - Volunteer return to verify returned items
    
    Returns:
        dict: Contains 'inventory' key with list of all inventory items
    """
    # Get all inventory items as a list of dictionaries
    all_inventory_items = _inventory_manager.get_all()
    
    # Return wrapped in a response object
    return {"inventory": all_inventory_items}


@router.put("/inventory/refill")
async def refill_inventory(refill_request: InventoryRefillRequest):
    """
    Manually trigger an inventory refill operation.
    
    Two refill modes are available:
    
    1. "daily" - Full reset:
       - Sets Available = Total for ALL items
       - Resets Reserved = 0 for ALL items
       - Simulates overnight restocking
    
    2. "partial" - Selective refill:
       - Only refills items where Available/Total ≤ 60%
       - More realistic for during-the-day restocking
       - Preserves reserved quantities
    
    This endpoint is typically called:
    - Automatically by scheduler at midnight (daily)
    - Manually by staff when new supplies arrive (partial)
    
    Args:
        refill_request: InventoryRefillRequest with:
            - mode: Either "daily" or "partial"
    
    Returns:
        dict: Confirmation with:
            - status: "refilled"
            - mode: The mode that was used
            - inventory: Updated inventory state
    """
    # STEP 1: Execute the requested refill mode
    if refill_request.mode == "daily":
        # Full reset to total capacity
        _inventory_manager.daily_refill()
    else:  # mode == "partial"
        # Only refill items below threshold
        _inventory_manager.partial_refill()

    # STEP 2: Get the updated inventory state
    updated_inventory = _inventory_manager.get_all()

    # STEP 3: Return confirmation with new state
    return {
        "status": "refilled",
        "mode": refill_request.mode,
        "inventory": updated_inventory,
    }