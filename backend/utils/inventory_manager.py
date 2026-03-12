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

# Configuration constants
REFILL_THRESHOLD = 0.60  # 60% - if stock falls below this, partial refill will restore it
_FUZZY_MIN_SCORE = 55     # Minimum similarity score for fuzzy matching (0-100)


class InventoryManager:
    """
    Manages inventory operations with a CSV file as the persistent storage.
    
    This class provides:
    1. Inventory tracking (Available, Reserved, Total quantities)
    2. Fuzzy matching for item names (handles typos/variations)
    3. Reservation and restoration of items for volunteer missions
    4. Automatic refill logic for low stock items
    
    The inventory CSV has columns: Item, Available, Reserved, Total, Bin Location, Category
    """
    
    def __init__(self, csv_path: str = str(INVENTORY_CSV)):
        """
        Initialize the inventory manager by loading data from CSV.
        
        If the CSV doesn't exist, create an empty DataFrame with the required columns.
        
        Args:
            csv_path: Path to the inventory CSV file (defaults to config setting)
        """
        self._path = csv_path  # Store path for saving later
        
        # Check if CSV file exists
        if INVENTORY_CSV.exists():
            # Load existing inventory data
            self.df = pd.read_csv(csv_path)
        else:
            # Create empty DataFrame with proper column structure
            self.df = pd.DataFrame(
                columns=[
                    "Item",           # Item name/description
                    "Available",       # Currently available quantity
                    "Reserved",        # Quantity reserved for active missions
                    "Total",           # Total stock (Available + Reserved + maybe buffer)
                    "Bin Location",    # Physical storage location
                    "Category",        # Item category (medical, food, tools, etc.)
                ]
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def reserve(self, item_name: str, quantity: int) -> bool:
        """
        Reserve items for a volunteer mission.
        
        This operation:
        1. Decreases Available quantity
        2. Increases Reserved quantity
        3. Prevents reserving more than what's available
        
        Args:
            item_name: Name of the item to reserve (fuzzy matched)
            quantity: Number of units to reserve
            
        Returns:
            bool: True if reservation successful, False if:
                 - Item not found (even with fuzzy matching)
                 - Insufficient available stock
        """
        # STEP 1: Find the item in inventory (fuzzy match)
        item_index = self._find(item_name)
        if item_index is None:
            return False  # Item not found
        
        # STEP 2: Check if we have enough stock
        if self.df.at[item_index, "Available"] < quantity:
            return False  # Insufficient stock
        
        # STEP 3: Update quantities
        self.df.at[item_index, "Available"] -= quantity  # Remove from available
        self.df.at[item_index, "Reserved"] += quantity    # Add to reserved
        
        # STEP 4: Save changes to disk
        self._save()
        
        return True  # Reservation successful

    def restore(self, item_name: str, quantity: int) -> None:
        """
        Return unused items from a completed mission back to inventory.
        
        This operation:
        1. Increases Available quantity
        2. Decreases Reserved quantity (can't go below 0)
        
        Args:
            item_name: Name of the item to restore (fuzzy matched)
            quantity: Number of units being returned
        """
        # STEP 1: Find the item in inventory
        item_index = self._find(item_name)
        if item_index is None:
            return  # Silently ignore if item not found
        
        # STEP 2: Update quantities
        self.df.at[item_index, "Available"] += quantity  # Add back to available
        
        # Calculate new reserved quantity (ensuring it doesn't go below zero)
        current_reserved = self.df.at[item_index, "Reserved"]
        self.df.at[item_index, "Reserved"] = max(0, current_reserved - quantity)
        
        # STEP 3: Save changes to disk
        self._save()

    def daily_refill(self) -> None:
        """
        Full overnight reset of inventory.
        
        This simulates restocking all items to their total capacity.
        Typically called once per day (e.g., at midnight).
        
        Effects:
        - Available = Total (fully restocked)
        - Reserved = 0 (all reservations cleared)
        """
        # Reset all items
        self.df["Available"] = self.df["Total"]  # Restore to full capacity
        self.df["Reserved"] = 0                   # Clear all reservations
        
        # Save changes
        self._save()

    def partial_refill(self) -> None:
        """
        Selective refill for items that are running low.
        
        Only refills items where Available / Total ≤ REFILL_THRESHOLD (60%).
        This is more realistic than full refill for during-the-day restocking.
        """
        # Iterate through each row in the DataFrame
        for index, row in self.df.iterrows():
            # Check if item has total stock (avoid division by zero)
            if row["Total"] > 0:
                # Calculate current availability ratio
                availability_ratio = row["Available"] / row["Total"]
                
                # If stock is at or below threshold, refill to full
                if availability_ratio <= REFILL_THRESHOLD:
                    self.df.at[index, "Available"] = row["Total"]
        
        # Save changes
        self._save()

    def get_all(self) -> list:
        """
        Return the entire inventory as a list of dictionaries.
        
        This is safe for JSON serialization and API responses.
        
        Returns:
            list: Each item as a dict with columns as keys
        """
        return self.df.to_dict(orient="records")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _find(self, item_name: str) -> int | None:
        """
        Find an item in inventory using fuzzy name matching.
        
        This handles typos, partial matches, and variations in item names.
        Uses rapidfuzz for efficient fuzzy string matching.
        
        Args:
            item_name: The item name to search for (may have typos)
            
        Returns:
            int: The row index of the best matching item
            None: If no match meets the minimum score threshold
        """
        # Get list of all item names from the inventory
        item_names = self.df["Item"].tolist()
        
        # If inventory is empty, return None
        if not item_names:
            return None
        
        # Find the best fuzzy match
        # extractOne returns: (matched_string, score, index)
        best_match, similarity_score, match_index = process.extractOne(
            item_name,           # The query string
            item_names,          # The list to search in
            scorer=fuzz.partial_ratio  # Scoring algorithm (good for partial matches)
        )
        
        # Only return index if score meets minimum threshold
        return match_index if similarity_score >= _FUZZY_MIN_SCORE else None

    def _save(self) -> None:
        """Save the current DataFrame to CSV file."""
        self.df.to_csv(self._path, index=False)