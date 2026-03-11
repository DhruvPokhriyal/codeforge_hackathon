# backend/main.py
# FastAPI application entry point and Uvicorn runner.
# Bound ONLY to 127.0.0.1 — this API is not accessible from the network.
#
# Startup sequence:
#   1. Build LlamaIndex vector store from data/protocols/
#   2. Start APScheduler escalation job (every 60s)
#
# All models (Whisper, LLaMA) are loaded lazily on first pipeline request
# to keep startup time fast for the Electron health-check poll.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import pipeline, approve, queue, volunteers, volunteer_return, inventory
from core.escalation_scheduler import start_scheduler
from core.priority_queue import priority_queue
from agents.retrieval_agent import build_index
from config import API_HOST, API_PORT, PROTOCOLS_DIR

app = FastAPI(
    title="Offline Emergency Intelligence Hub",
    description="Offline AI triage and volunteer dispatch for disaster shelters.",
    version="1.0.0",
)

# Allow only localhost — security requirement for offline-only operation
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(pipeline.router)
app.include_router(approve.router)
app.include_router(queue.router)
app.include_router(volunteers.router)
app.include_router(volunteer_return.router)
app.include_router(inventory.router)


@app.on_event("startup")
async def on_startup():
    # Build vector index if protocols exist
    if any(PROTOCOLS_DIR.glob("*.pdf")):
        build_index(str(PROTOCOLS_DIR))
    # Start urgency escalation background job
    start_scheduler(priority_queue)


@app.get("/health")
async def health():
    """Health check polled by Electron main process every 500ms on startup."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=False)
