# backend/utils/inventory_manager.py
# Inventory Manager — CRUD operations on data/inventory.csv
#
# Thread-safe read/write wrapper around the inventory CSV.
# Used by routers/approve.py (reserve) and routers/volunteer_return.py (restore).
# After any mutation, logistics_agent.reload_inventory() should be called so
# the in-memory DataFrame stays in sync.
#
# Public interface (class InventoryManager):
#   reserve(item_name, quantity) -> bool   — decrement Available, increment Reserved
#   restore(item_name, quantity) -> None   — increment Available, decrement Reserved
#   daily_refill() -> None                 — full reset: Available = Total, Reserved = 0
#   partial_refill() -> None               — refill items at ≤ 60% capacity
#   get_all() -> list[dict]                — serialisable snapshot of the CSV

import pandas as pd
from rapidfuzz import process, fuzz

from config import INVENTORY_CSV

REFILL_THRESHOLD = 0.60
_FUZZY_MIN_SCORE = 55


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

    def restore(self, item_name: str, quantity: int) -> None:
        """Increment Available, decrement Reserved (floor at 0)."""
        idx = self._find(item_name)
        if idx is None:
            return
        self.df.at[idx, "Available"] += quantity
        self.df.at[idx, "Reserved"] = max(0, self.df.at[idx, "Reserved"] - quantity)
        self._save()

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
        return self.df.to_dict(orient="records")

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
