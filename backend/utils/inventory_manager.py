# backend/utils/inventory_manager.py
# Inventory Manager — CRUD operations on data/inventory.csv
#
# Thread-safe read/write wrapper around the inventory CSV.
# Used by routers/approve.py (reserve) and routers/volunteer_return.py (restore).
# After any mutation, logistics_agent.reload_inventory() should be called so
# the in-memory DataFrame stays in sync.
#
# Public interface (class InventoryManager):
#   reserve(item_name, quantity) -> bool
#   restore(item_name, quantity) -> dict    — returns to inventory or buffer
#   update_item(item_name, quantity) -> dict — add stock respecting capacity
#   create_item(item_name, capacity, bin_location, category) -> dict
#   daily_refill() -> None
#   partial_refill() -> None
#   get_all() -> list[dict]
#   get_buffer() -> list[dict]

import pandas as pd
from rapidfuzz import process, fuzz

from config import INVENTORY_CSV

REFILL_THRESHOLD = 0.60
_FUZZY_MIN_SCORE = 55

# ── Buffer Inventory ──────────────────────────────────────────────────────────
# When returned items can't fit back into the main inventory (already at Total),
# they go here. Buffer starts at 100 capacity and expands dynamically.
_BUFFER: dict[str, dict] = {}   # { item_name: { "quantity": int, "capacity": int } }
_BUFFER_DEFAULT_CAP = 100


class InventoryManager:
    def __init__(self, csv_path: str = str(INVENTORY_CSV)):
        self._path = csv_path
        self.df = (
            pd.read_csv(csv_path)
            if INVENTORY_CSV.exists()
            else pd.DataFrame(
                columns=[
                    "Item",
                    "Available",
                    "Reserved",
                    "Total",
                    "Bin Location",
                    "Category",
                ]
            )
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def reserve(self, item_name: str, quantity: int) -> bool:
        """
        Decrement Available by quantity and increment Reserved.
        Returns False if item not found or insufficient stock.
        """
        idx = self._find(item_name)
        if idx is None:
            return False
        if self.df.at[idx, "Available"] < quantity:
            return False
        self.df.at[idx, "Available"] -= quantity
        self.df.at[idx, "Reserved"] += quantity
        self._save()
        return True

    def restore(self, item_name: str, quantity: int) -> dict:
        """Return items to inventory. If main inventory is full, overflow goes to buffer.
        Returns {"restored": int, "buffered": int}."""
        idx = self._find(item_name)
        if idx is None:
            # Unknown item — put everything in buffer
            self._add_to_buffer(item_name, quantity)
            return {"restored": 0, "buffered": quantity}

        available = int(self.df.at[idx, "Available"])
        total = int(self.df.at[idx, "Total"])
        reserved = int(self.df.at[idx, "Reserved"])

        space = total - available
        can_restore = min(quantity, space)
        overflow = quantity - can_restore

        if can_restore > 0:
            self.df.at[idx, "Available"] += can_restore
            self.df.at[idx, "Reserved"] = max(0, reserved - can_restore)
            self._save()

        if overflow > 0:
            self._add_to_buffer(item_name, overflow)

        return {"restored": can_restore, "buffered": overflow}

    def update_item(self, item_name: str, quantity: int) -> dict:
        """Add stock to an existing item, respecting capacity (Total).
        Returns {"ok": bool, "error": str|None, "available": int, "total": int}."""
        idx = self._find(item_name)
        if idx is None:
            # Item doesn't exist — create it as a new item
            return self.create_item(item_name, quantity)

        available = int(self.df.at[idx, "Available"])
        total = int(self.df.at[idx, "Total"])
        space = total - available

        if quantity > space:
            return {
                "ok": False,
                "error": f"Not enough space in inventory. {available}/{total} — only {space} free slots.",
                "available": available,
                "total": total,
            }

        self.df.at[idx, "Available"] += quantity
        self._save()
        return {
            "ok": True,
            "error": None,
            "available": int(self.df.at[idx, "Available"]),
            "total": total,
        }

    def create_item(self, item_name: str, capacity: int,
                     bin_location: str = "NEW", category: str = "General") -> dict:
        """Create a brand-new inventory item with Available = Total = capacity."""
        new_row = pd.DataFrame([{
            "Item": item_name,
            "Available": capacity,
            "Reserved": 0,
            "Total": capacity,
            "Bin Location": bin_location,
            "Category": category,
        }])
        self.df = pd.concat([self.df, new_row], ignore_index=True)
        self._save()
        return {
            "ok": True,
            "error": None,
            "available": capacity,
            "total": capacity,
        }

    def daily_refill(self) -> None:
        """Full overnight reset — Available = Total, Reserved = 0."""
        self.df["Available"] = self.df["Total"]
        self.df["Reserved"] = 0
        self._save()

    def partial_refill(self) -> None:
        """Refill only items whose Available / Total ≤ REFILL_THRESHOLD (60%)."""
        for idx, row in self.df.iterrows():
            if (
                row["Total"] > 0
                and (row["Available"] / row["Total"]) <= REFILL_THRESHOLD
            ):
                self.df.at[idx, "Available"] = row["Total"]
        self._save()

    def get_all(self) -> list:
        """Return inventory as a list of dicts (safe for JSON serialisation)."""
        import numpy as np
        return self.df.replace({np.nan: None}).to_dict(orient="records")

    def get_buffer(self) -> list:
        """Return buffer inventory as a list of dicts."""
        return [
            {"item": name, "quantity": info["quantity"], "capacity": info["capacity"]}
            for name, info in _BUFFER.items()
            if info["quantity"] > 0
        ]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _find(self, item_name: str) -> int | None:
        """Fuzzy-match item_name against the Item column. Returns row index or None."""
        names = self.df["Item"].tolist()
        if not names:
            return None
        _match, score, idx = process.extractOne(
            item_name, names, scorer=fuzz.partial_ratio
        )
        return idx if score >= _FUZZY_MIN_SCORE else None

    def _save(self) -> None:
        self.df.to_csv(self._path, index=False)

    @staticmethod
    def _add_to_buffer(item_name: str, quantity: int) -> None:
        """Add overflow items to the buffer. Capacity expands dynamically."""
        if item_name not in _BUFFER:
            _BUFFER[item_name] = {"quantity": 0, "capacity": _BUFFER_DEFAULT_CAP}
        buf = _BUFFER[item_name]
        buf["quantity"] += quantity
        # Expand capacity if needed
        if buf["quantity"] > buf["capacity"]:
            buf["capacity"] = buf["quantity"]
        print(f"[INVENTORY] Buffer: {item_name} now {buf['quantity']}/{buf['capacity']}")
