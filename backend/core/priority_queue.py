# backend/core/priority_queue.py
# Max-heap priority queue for emergency requests.
#
# Key formula (computed by rag_triage_agent):
#   heap_key = severity_score - (travel_time × 2) - resolution_time
#   Higher key = higher urgency = served first
#
# The heap stores (-heap_key, timestamp, request_id) so Python's min-heap
# behaves as a max-heap on the positive heap_key values.
#
# Public interface (via singleton `priority_queue`):
#   push(request: dict) -> None
#   peek_top_pending() -> dict | None    — returns highest PENDING request
#   get_sorted() -> list[dict]           — all requests, highest key first
#   update_key(request_id, new_key)      — called by escalation_scheduler
#   update(request_id, updates)          — called by dispatch_engine / routers

import heapq
from datetime import datetime


class PriorityQueue:
    """
    A priority queue implementation for emergency requests using a max-heap.
    
    This data structure maintains:
    1. A heap for quick access to the highest priority request
    2. A dictionary store for complete request data by ID
    
    The heap stores tuples of (-priority, timestamp, request_id) to work with
    Python's min-heap implementation while maintaining max-heap behavior.
    """
    
    def __init__(self):
        """Initialize an empty priority queue."""
        # Heap stores tuples: (-heap_key, timestamp_string, request_id)
        # Using negative key makes Python's min-heap act like a max-heap
        self._heap: list = []  
        
        # Dictionary store: request_id → complete request data
        # This separates the heap ordering from the actual data
        self._store: dict = {}  

    def push(self, request: dict) -> None:
        """
        Add a new request to the priority queue.
        
        This method:
        1. Extracts the key, timestamp, and ID from the request
        2. Pushes a tuple onto the heap for ordering
        3. Stores the full request data in the dictionary
        
        Args:
            request: Complete request dictionary with all fields
        """
        # Extract the priority key (higher = more urgent)
        priority_key = request["heap_key"]
        
        # Get timestamp for tie-breaking (older requests get priority)
        timestamp = request["time_of_request"]
        
        # Get unique identifier
        request_id = request["request_id"]
        
        # Push to heap with negated key (for max-heap behavior)
        heapq.heappush(self._heap, (-priority_key, timestamp, request_id))
        
        # Store the complete request data
        self._store[request_id] = request

    def peek_top_pending(self) -> dict | None:
        """
        Return the highest-priority PENDING request without removing it.
        
        This method scans through the heap (which is ordered by priority)
        until it finds a request that is still in PENDING status.
        It skips any ASSIGNED or RESOLVED requests.
        
        Returns:
            dict: The highest priority pending request
            None: If no pending requests exist
        """
        # Iterate through heap entries in priority order
        for negated_key, timestamp, request_id in self._heap:
            # Get the full request data from the store
            request = self._store.get(request_id)
            
            # Check if request exists and is still pending
            if request and request.get("status") == "PENDING":
                return request  # Return the first (highest priority) pending request
                
        return None  # No pending requests found

    def get_sorted(self) -> list:
        """
        Return all requests sorted by heap_key descending (highest priority first).
        
        This is useful for:
        - Displaying all requests in priority order
        - The escalation scheduler to iterate through requests
        - Debugging and monitoring
        
        Returns:
            list: All requests in descending priority order
        """
        # Sort the heap (which is already partially ordered)
        sorted_entries = sorted(self._heap)
        
        # Extract request data for each entry, filtering out deleted requests
        return [
            self._store[request_id]
            for _, _, request_id in sorted_entries
            if request_id in self._store  # Skip if request was removed
        ]

    def update_key(self, request_id: str, new_priority: float) -> None:
        """
        Update the heap priority key for a request and rebuild the heap.
        
        This is called periodically by the escalation scheduler to increase
        priority of requests that have been waiting too long.
        
        Note: Python's heapq doesn't support efficient decrease-key operations,
        so we rebuild the entire heap from scratch. This is acceptable because:
        - The queue size is small (typical disaster scenarios)
        - Updates happen only every 60 seconds
        
        Args:
            request_id: The unique identifier of the request to update
            new_priority: The new heap_key value to assign
        """
        # Check if the request exists
        if request_id not in self._store:
            return  # Silently ignore non-existent requests
            
        # Update the stored request with the new priority
        self._store[request_id]["heap_key"] = new_priority
        
        # Rebuild the heap from existing store data
        # This is necessary because heapq doesn't support direct key updates
        self._heap = [
            # Recreate each heap entry with updated priority
            (-self._store[request_id]["heap_key"], timestamp, request_id)
            for _, timestamp, request_id in self._heap
            if request_id in self._store  # Skip any deleted requests
        ]
        
        # Re-heapify to maintain heap invariant
        heapq.heapify(self._heap)

    def update(self, request_id: str, updates: dict) -> None:
        """
        Apply a partial update to a stored request without rebuilding the heap.
        
        This is used by the dispatch engine to update request status
        (e.g., from PENDING to ASSIGNED to RESOLVED) and add metadata
        like assigned_volunteer, items_taken, etc.
        
        Note: This does NOT affect heap ordering - only the dispatch_engine
        and escalation_scheduler can change priority via update_key().
        
        Args:
            request_id: The unique identifier of the request to update
            updates: Dictionary of fields to update/add to the request
        """
        if request_id in self._store:
            # Apply all updates to the stored request
            self._store[request_id].update(updates)
            # No heap rebuild needed - priority didn't change


# Singleton instance - shared across all routers and the escalation scheduler
# This ensures consistent state across the entire application
priority_queue = PriorityQueue()