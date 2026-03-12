# backend/core/request_store.py
# In-memory request registry.
#
# All requests created by POST /pipeline are stored here.
# Priority queue separately tracks ordering; this store holds full request dicts.
#
# Public interface (via singleton `request_store`):
#   add(request: dict) -> None
#   get(request_id: str) -> dict | None
#   update(request_id: str, updates: dict) -> None
#   filter_by_status(status: str) -> list[dict]
#   all() -> list[dict]


class RequestStore:
    """
    In-memory storage for all emergency requests.
    
    This class serves as the single source of truth for request data.
    It works alongside the PriorityQueue:
    - PriorityQueue handles ordering (which request is most urgent)
    - RequestStore handles data persistence (full request details)
    
    The store is a simple key-value dictionary with request_id as the key.
    """
    
    def __init__(self):
        """Initialize an empty request store."""
        # Private dictionary: request_id → complete request data
        # Using underscore convention to indicate internal use
        self._store: dict[str, dict] = {}

    def add(self, request: dict) -> None:
        """
        Store a new request in the registry.
        
        This is called when a new request is created via the pipeline.
        The request must have a 'request_id' field.
        
        Args:
            request: Complete request dictionary with all fields
                    (must contain 'request_id')
        """
        # Extract the unique identifier
        request_id = request["request_id"]
        
        # Store the entire request object
        self._store[request_id] = request

    def get(self, request_id: str) -> dict | None:
        """
        Retrieve a specific request by its ID.
        
        Args:
            request_id: The unique identifier of the request
            
        Returns:
            dict: The complete request data if found
            None: If no request exists with that ID
        """
        # .get() safely returns None if key doesn't exist
        return self._store.get(request_id)

    def update(self, request_id: str, updates: dict) -> None:
        """
        Apply partial updates to an existing request.
        
        This is used throughout the system to:
        - Change request status (PENDING → ASSIGNED → RESOLVED)
        - Add assignment information (volunteer ID, items taken)
        - Add return information (actual return time, returned items)
        
        Args:
            request_id: The unique identifier of the request to update
            updates: Dictionary of fields to update or add
                    (e.g., {"status": "ASSIGNED", "assigned_volunteer": "V-01"})
        """
        # Only update if the request exists
        if request_id in self._store:
            # .update() merges the updates into the existing dictionary
            self._store[request_id].update(updates)

    def filter_by_status(self, status: str) -> list:
        """
        Return all requests with a specific status.
        
        Useful for:
        - Getting all PENDING requests for dispatch
        - Getting all RESOLVED requests for reporting
        - Monitoring current workload by status
        
        Args:
            status: The status to filter by (PENDING, ASSIGNED, or RESOLVED)
            
        Returns:
            list: All requests matching the given status
        """
        # List comprehension filters requests where status matches
        return [
            request 
            for request in self._store.values() 
            if request.get("status") == status
        ]

    def all(self) -> list:
        """
        Return all requests in the store.
        
        This is useful for:
        - Complete system state reporting
        - Debugging and monitoring
        - Exporting all data
        
        Returns:
            list: All requests in no particular order
        """
        # Convert dictionary values to a list
        return list(self._store.values())


# Singleton instance - shared across all routers
# This ensures that all parts of the application work with the same data
request_store = RequestStore()