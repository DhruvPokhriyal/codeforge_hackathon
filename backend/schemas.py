# backend/schemas.py
# Shared Pydantic data contracts used by ALL groups.
# NEVER define request/response shapes inline in routers or agents — import from here.
# This is the single source of truth for inter-module communication.

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Core domain objects
# ─────────────────────────────────────────────────────────────────────────────


class MaterialItem(BaseModel):
    """One supply/equipment item required for a situation."""

    item: str
    quantity: int
    available: bool = False  # annotated by logistics_agent
    available_qty: int = 0  # annotated by logistics_agent
    bin: str = "?"  # annotated by logistics_agent


class Situation(BaseModel):
    """
    One plausible emergency scenario produced by rag_triage_agent.
    Multiple situations are returned per request (multi-diagnostic output).
    """

    label: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    severity_score: int  # CRITICAL=100, HIGH=75, MEDIUM=50, LOW=25
    confidence: float = 0.5
    travel_time_min: int
    resolution_time_min: int
    heap_key: float = 0.0  # severity_score - (travel×2) - resolution_time
    materials: list[MaterialItem] = []
    instructions: list[str] = []
    reasoning: str = ""
    source_chunks: list[str] = []
    selected: bool = False  # set to True when HITL manager selects this situation


class EmergencyRequest(BaseModel):
    """
    Full request lifecycle object — created at POST /pipeline,
    updated through approve → dispatch → return.
    """

    request_id: str
    time_of_request: str
    transcript: str
    is_vague: bool = False
    situations: list[Situation] = []
    status: str = "PENDING"  # PENDING | ASSIGNED | RESOLVED
    heap_key: float = 0.0  # key of dominant (highest) situation
    assigned_volunteer: Optional[str] = None
    assigned_at: Optional[str] = None
    expected_return: Optional[str] = None
    actual_return: Optional[str] = None
    items_taken: list[dict] = []
    items_returned: list[dict] = []
    escalation_stage: int = 0
    handoff_logs: list[dict] = []


class VolunteerState(BaseModel):
    """Live state of one volunteer. Managed by dispatch_engine."""

    volunteer_id: str
    status: str = "AVAILABLE"  # AVAILABLE | BUSY
    request_id: Optional[str] = None
    assigned_at: Optional[str] = None
    expected_return: Optional[str] = None
    items_taken: list[dict] = []


class InventoryItem(BaseModel):
    """One row from data/inventory.csv."""

    Item: str
    Available: int
    Reserved: int
    Total: int
    bin_location: str = ""
    Category: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# API request bodies
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRequest(BaseModel):
    """POST /pipeline — incoming distress audio as base64 string."""

    audio_b64: str  # base64-encoded .wav


class ApproveRequest(BaseModel):
    """POST /approve — HITL manager selects situations and triggers dispatch."""

    request_id: str
    selected_indices: list[int]
    manual_override: Optional[dict] = None  # {"condition": str, "items": [str]}


class OverrideRequest(BaseModel):
    """POST /approve/override — create and enqueue a manual-override task."""

    source_request_id: str
    manual_override: dict  # {"condition": str, "resources": [{"item": str, "qty": int}], "notes": str}


class VolunteerReturnRequest(BaseModel):
    """POST /volunteer/return — volunteer back at base with returned items."""

    volunteer_id: str
    returned_items: list[dict]  # [{"item": str, "quantity": int}]


class InventoryRefillRequest(BaseModel):
    """PUT /inventory/refill — trigger a manual refill cycle."""

    mode: str = "partial"  # "partial" | "daily"


# ─────────────────────────────────────────────────────────────────────────────
# API response shapes
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResponse(BaseModel):
    request_id: str
    transcript: str
    is_vague: bool
    situations: list[Situation]
    handoff_logs: list[dict] = []


class ApproveResponse(BaseModel):
    request_id: str
    queue: list[dict]
    volunteers: list[dict]


class OverrideResponse(BaseModel):
    request_id: str
    source_request_id: str
    queue: list[dict]
    volunteers: list[dict]


class VolunteerReturnResponse(BaseModel):
    freed_volunteer: str
    queue: list[dict]
    volunteers: list[dict]
    inventory: list[dict]
