# backend/main.py
# FastAPI application entry point and Uvicorn runner.
# Bound ONLY to 127.0.0.1 — this API is not accessible from the network.
#
# Startup sequence:
#   1. Build LlamaIndex vector store from data/protocols/ (skipped if no PDFs)
#   2. Start APScheduler escalation job (every 60s)
#
# All models (Whisper, LLaMA) are loaded lazily on first pipeline request
# to keep startup time fast for the Electron health-check poll.

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import all route handlers
from routers import (
    pipeline,
    approve,
    queue,
    volunteers,
    volunteer_return,
    inventory,
    settings,
)

# Import core components
from core.escalation_scheduler import start_scheduler
from core.priority_queue import priority_queue

# Import agent utilities
from agents.retrieval_agent import build_index

# Import configuration
from config import API_HOST, API_PORT, PROTOCOLS_DIR

# ── FastAPI Application Initialization ─────────────────────────────────────────


app = FastAPI(
    title="Offline Emergency Intelligence Hub",
    description="Offline AI triage and volunteer dispatch for disaster shelters.",
    version="1.0.0",
)

# ── CORS Middleware Configuration ─────────────────────────────────────────────
# Security requirement: Only allow connections from localhost
# This ensures the API remains offline and inaccessible from the network
app.add_middleware(
    CORSMiddleware,
    # Only these origins are permitted (Electron app runs on localhost)
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, etc.)
    allow_headers=["*"],  # Allow all headers
)

# ── Route Registration ────────────────────────────────────────────────────────
# Register all API endpoint routers with the main application
app.include_router(pipeline.router)         # Main triage pipeline (speech/text → assessment)
app.include_router(approve.router)          # Approve/reject triage results
app.include_router(queue.router)            # View and manage request queue
app.include_router(volunteers.router)       # Volunteer status and assignment
app.include_router(volunteer_return.router) # Process volunteer returns
app.include_router(inventory.router)        # Inventory management
app.include_router(settings.router)         # Frontend configuration


# ── Startup Event Handler ─────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """
    Initialize background services when the FastAPI application starts.
    
    This runs automatically when uvicorn starts the server.
    Two main initialization tasks:
    
    1. Build Vector Index:
       - Scans data/protocols/ directory for PDF files
       - Creates LlamaIndex vector store for semantic search
       - Used by retrieval_agent to find relevant protocols
       - Only builds if PDFs exist (skips if directory empty)
    
    2. Start Escalation Scheduler:
       - Launches APScheduler background job
       - Runs every 60 seconds (configurable)
       - Increases priority of pending requests over time
       - Ensures old requests don't get forgotten
    """
    # STEP 1: Build vector index from protocol PDFs (if any exist)
    if any(PROTOCOLS_DIR.glob("*.pdf")):
        # Convert directory path to string and build the index
        build_index(str(PROTOCOLS_DIR))
    
    # STEP 2: Start the urgency escalation background job
    # Pass the priority queue instance so scheduler can update request priorities
    start_scheduler(priority_queue)


# ── Health Check Endpoint ─────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """
    Simple health check endpoint for the Electron app.
    
    The Electron main process polls this endpoint every 500ms during startup
    to determine when the backend is ready to accept requests.
    
    Returns:
        dict: Always {"status": "ok"} when server is running
    """
    return {"status": "ok"}


# ── Direct Execution Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    """
    Run the FastAPI application with Uvicorn server when script is executed directly.
    
    This is used during development and when starting from the command line:
        python main.py
    
    Configuration:
    - Host: 127.0.0.1 (localhost only - secure offline operation)
    - Port: From config (default: 8000)
    - Reload: Disabled (must be manually restarted after code changes)
    """
    import uvicorn

    # Start the Uvicorn server with configuration from config.py
    uvicorn.run(
        "main:app",          # ASGI application: "module:app_instance"
        host=API_HOST,        # Bind address (127.0.0.1 from config)
        port=API_PORT,        # Port number (from config)
        reload=False          # Disable auto-reload for production stability
    )