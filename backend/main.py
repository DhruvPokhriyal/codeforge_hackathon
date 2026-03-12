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

# ── Route Handlers ────────────────────────────────────────────────────────────
# Import all API endpoint routers
from routers import pipeline, approve, queue, volunteers, volunteer_return, inventory

# ── Core Components ───────────────────────────────────────────────────────────
# Import background services and shared state
from core.escalation_scheduler import start_scheduler
from core.priority_queue import priority_queue

# ── Agent Utilities ───────────────────────────────────────────────────────────
# Import vector store builder for RAG
from agents.retrieval_agent import build_index

# ── Configuration ─────────────────────────────────────────────────────────────
# Import application settings
from config import API_HOST, API_PORT, PROTOCOLS_DIR


# ── FastAPI Application Initialization ────────────────────────────────────────
# Create the main FastAPI application instance with metadata
# This metadata appears in the auto-generated API docs at /docs
app = FastAPI(
    title="Offline Emergency Intelligence Hub",
    description="Offline AI triage and volunteer dispatch for disaster shelters.",
    version="1.0.0",
)


# ── CORS Middleware Configuration ─────────────────────────────────────────────
# Security requirement: Only allow connections from localhost
# This ensures the API remains offline and inaccessible from the network
# The Electron frontend runs on localhost, so this is sufficient
app.add_middleware(
    CORSMiddleware,
    # Only these origins are permitted (Electron app runs on localhost)
    # No external network access allowed - critical for offline security
    allow_origins=["http://localhost", "http://127.0.0.1"],
    
    # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    # The frontend needs various methods for different operations
    allow_methods=["*"],
    
    # Allow all headers (for authentication, content-type, etc.)
    allow_headers=["*"],
)


# ── Route Registration ────────────────────────────────────────────────────────
# Register all API endpoint routers with the main application
# Each router handles a specific domain of the application
app.include_router(pipeline.router)           # POST /pipeline - Main triage pipeline (speech/text → assessment)
app.include_router(approve.router)             # POST /approve - Approve/reject triage results
app.include_router(queue.router)                # GET /queue - View and manage request queue
app.include_router(volunteers.router)           # GET /volunteers - Volunteer status and assignment
app.include_router(volunteer_return.router)     # POST /volunteer/return - Process volunteer returns
app.include_router(inventory.router)            # GET /inventory, PUT /inventory/refill - Inventory management


# ── Startup Event Handler ─────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    """
    Initialize background services when the FastAPI application starts.
    
    This function runs automatically when uvicorn starts the server.
    It performs two critical initialization tasks that need to happen
    before the system can handle requests:
    
    ──────────────────────────────────────────────────────────────────────────
    Task 1: Build Vector Index (RAG Knowledge Base)
    ──────────────────────────────────────────────────────────────────────────
    - Scans the data/protocols/ directory for PDF files
    - Creates a LlamaIndex vector store for semantic search
    - This index powers the retrieval_agent to find relevant protocols
    - Only builds if PDFs exist (skips silently if directory is empty)
    - Without this, the RAG system cannot retrieve protocol information
    
    ──────────────────────────────────────────────────────────────────────────
    Task 2: Start Escalation Scheduler
    ──────────────────────────────────────────────────────────────────────────
    - Launches APScheduler background job
    - Runs every 60 seconds (configurable via ESCALATION_INTERVAL_SECS)
    - Increases priority of pending requests based on wait time
    - Ensures old requests don't get forgotten (fairness)
    - Critical for the priority escalation feature
    
    Note: Heavy models (Whisper for transcription, LLaMA for triage) are NOT
    loaded here. They are loaded lazily on the first POST /pipeline request.
    This keeps startup time under 1 second for the Electron health-check poll.
    """
    # STEP 1: Build vector index from protocol PDFs (if any exist)
    # Check if there are any PDF files in the protocols directory
    pdf_files_exist = any(PROTOCOLS_DIR.glob("*.pdf"))
    
    if pdf_files_exist:
        # Convert directory path to string and build the vector index
        # This may take a few seconds but only happens once at startup
        build_index(str(PROTOCOLS_DIR))
        # No return value needed - index is saved to disk
    
    # STEP 2: Start the urgency escalation background job
    # Pass the priority queue instance so scheduler can update request priorities
    # This starts a background thread that runs independently of requests
    start_scheduler(priority_queue)


# ── Health Check Endpoint ─────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """
    Simple health check endpoint for the Electron app.
    
    The Electron main process polls this endpoint every 500ms during startup
    to determine when the backend is ready to accept requests.
    
    This is critical for the user experience because:
    1. Electron starts the backend as a subprocess
    2. It needs to know when the FastAPI server is fully initialized
    3. Only then does it enable the UI and allow audio recording
    
    The endpoint is intentionally lightweight - it doesn't check model loading
    or database connections. It just confirms the server is running.
    
    Returns:
        dict: Always {"status": "ok"} when server is running
              If server is down, the connection will fail/timeout
    """
    return {"status": "ok"}


# ── Direct Execution Entry Point ─────────────────────────────────────────────
if __name__ == "__main__":
    """
    Run the FastAPI application with Uvicorn server when script is executed directly.
    
    This block only runs when you execute `python main.py` directly.
    When imported by another module (like during testing), this block is skipped.
    
    Usage in development:
        python main.py
    
    Usage in production:
        The Electron app runs this command automatically on startup
    
    Configuration Details:
    ──────────────────────────────────────────────────────────────────────────
    Host: 127.0.0.1 (localhost only)
        - Binds only to loopback interface
        - Not accessible from other machines on the network
        - Critical for offline security requirement
    
    Port: From config (default: 8000)
        - Configurable via API_PORT in config.py or .env
        - Must match the port Electron expects (hardcoded in Electron)
    
    Reload: Disabled (False)
        - Auto-reload would restart server on code changes
        - Useful in development but dangerous in production
        - Production uses manual restarts only
    ──────────────────────────────────────────────────────────────────────────
    """
    import uvicorn

    # Start the Uvicorn ASGI server with configuration from config.py
    uvicorn.run(
        # ASGI application identifier: "module_name:app_instance_name"
        # Tells uvicorn to look for 'app' in the 'main' module
        "main:app",
        
        # Bind address - MUST be localhost for security
        host=API_HOST,          # From config (should be "127.0.0.1")
        
        # Port number - must match Electron frontend configuration
        port=API_PORT,          # From config (default: 8000)
        
        # Disable auto-reload for production stability
        # In development, you can manually enable by changing to True
        reload=False            # Must manually restart after code changes
    )