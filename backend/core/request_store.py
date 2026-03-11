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
    def __init__(self):
        self._store: dict[str, dict] = {}

    def add(self, request: dict) -> None:
        self._store[request["request_id"]] = request

    def get(self, request_id: str) -> dict | None:
        return self._store.get(request_id)

    def update(self, request_id: str, updates: dict) -> None:
        if request_id in self._store:
            self._store[request_id].update(updates)

    def filter_by_status(self, status: str) -> list:
        return [r for r in self._store.values() if r.get("status") == status]

    def all(self) -> list:
        return list(self._store.values())


# Singleton shared across all routers
request_store = RequestStore()
