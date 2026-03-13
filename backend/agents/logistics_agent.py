# backend/agents/logistics_agent.py
# STEP 6 — Inventory Availability Check
#
# Fuzzy-matches each required material against the inventory CSV and annotates
# each situation's material list with real-time availability data.
# Depends on: data/inventory.csv (loaded at module import)
#
# Public interface:
#   check_availability(item_name: str) -> dict
#     · Returns: {found, item, available, quantity, bin}
#
#   annotate_situations(situations: list) -> list
#     · Mutates each material entry in-place with availability fields
#     · Returns the same list (for pipeline chaining)

import pandas as pd
from rapidfuzz import process, fuzz

from config import INVENTORY_CSV

_FUZZY_THRESHOLD = 55  # minimum score to consider a match valid

# Load inventory at module level — shared across all requests
_df = (
    pd.read_csv(INVENTORY_CSV)
    if INVENTORY_CSV.exists()
    else pd.DataFrame(
        columns=["Item", "Available", "Reserved", "Total", "Bin Location", "Category"]
    )
)


def check_availability(item_name: str) -> dict:
    """
    Fuzzy-match item_name against inventory CSV.
    Returns availability dict with found/available/quantity/bin fields.
    """
    names = _df["Item"].tolist()
    if not names:
        return {"found": False, "available": False, "quantity": 0, "bin": "?"}

    match, score, idx = process.extractOne(item_name, names, scorer=fuzz.partial_ratio)
    if score < _FUZZY_THRESHOLD:
        return {"found": False, "available": False, "quantity": 0, "bin": "?"}

    row = _df.iloc[idx]
    avail = int(row["Available"])
    return {
        "found": True,
        "item": row["Item"],
        "available": avail > 0,
        "quantity": avail,
        "bin": row.get("Bin Location", "?"),
    }


def annotate_situations(situations: list) -> list:
    """
    Add inventory availability info to every material in every situation.
    Mutates in-place and returns the list for pipeline chaining.
    """
    for situation in situations:
        for mat in situation.get("materials", []):
            inv = check_availability(mat["item"])
            mat["available"] = inv["available"]
            mat["available_qty"] = inv.get("quantity", 0)
            mat["bin"] = inv.get("bin", "?")
    return situations


def reload_inventory() -> None:
    """Reload the CSV from disk — call after InventoryManager writes changes."""
    global _df
    if INVENTORY_CSV.exists():
        _df = pd.read_csv(INVENTORY_CSV)
