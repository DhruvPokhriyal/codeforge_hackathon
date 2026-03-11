# backend/routers/pipeline.py
# POST /pipeline — Full audio-to-report pipeline
#
# Step-by-step orchestration:
#   1. Decode base64 audio → save to temp/REQ-XXX_raw.wav
#   2. Denoise → temp/REQ-XXX_clean.wav
#   3. Transcribe (Whisper) → transcript string
#   4. Retrieve RAG chunks (LlamaIndex) → top-k chunks + is_vague flag
#   4b. If is_vague: expand with LLM hypotheses → retry retrieval
#   5. RAG triage (LLaMA 3.2 3B) → multi-situation JSON
#   6. Annotate each situation's materials with inventory availability
#   7. Store full request, return PipelineResponse

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from schemas import PipelineRequest, PipelineResponse
from agents import (
    denoise,
    transcribe,
    retrieve,
    resolve_and_retrieve,
    run_rag_triage,
    annotate_situations,
)
from core.priority_queue import priority_queue
from core.request_store import request_store
from utils.audio_utils import save_base64_wav, get_clean_path, cleanup_temp
from utils.logger import log_handoff

router = APIRouter()

# LLM instance — loaded lazily on first POST /pipeline call
_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from llama_cpp import Llama
        from config import LLAMA_MODEL_PATH, LLM_CONTEXT_SIZE
        _llm = Llama(model_path=LLAMA_MODEL_PATH, n_ctx=LLM_CONTEXT_SIZE, verbose=False)
    return _llm


@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(body: PipelineRequest):
    request_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"
    handoff_logs: list[dict] = []

    # Step 1 — Decode and save audio
    raw_path  = save_base64_wav(body.audio_b64, request_id)
    clean_path = get_clean_path(request_id)

    # Step 2 — Denoise
    log_handoff("AUDIO_INPUT", "DENOISER", "start pipeline", {"request_id": request_id})
    denoise(raw_path, clean_path)

    # Step 3 — Transcribe
    log_handoff("DENOISER", "INTAKE_AGENT", "audio cleaned", {"clean_path": clean_path})
    transcript = transcribe(clean_path)

    # Step 4 — Retrieve RAG chunks
    log_handoff("INTAKE_AGENT", "RETRIEVAL_AGENT", "transcribed", {"transcript": transcript})
    retrieval = retrieve(transcript)
    chunks    = retrieval["chunks"]

    # Step 4b — Vagueness resolution
    if retrieval["is_vague"]:
        log_handoff(
            "RETRIEVAL_AGENT", "VAGUENESS_AGENT",
            f"top_score={retrieval['top_score']:.2f} < threshold=0.8",
            {"transcript": transcript, "top_score": retrieval["top_score"]},
        )
        handoff_logs.append({
            "step": "vagueness_resolved",
            "reason": f"low confidence ({retrieval['top_score']:.2f})",
        })
        chunks = resolve_and_retrieve(transcript, _get_llm(), retrieve)

    # Step 5 — RAG triage
    log_handoff("RETRIEVAL_AGENT", "RAG_TRIAGE_AGENT", "chunks ready", {"chunk_count": len(chunks)})
    situations = run_rag_triage(transcript, chunks, _get_llm())

    # Step 6 — Inventory annotation
    log_handoff("RAG_TRIAGE_AGENT", "LOGISTICS_AGENT", "situations ready", {"count": len(situations)})
    situations = annotate_situations(situations)

    # Store request
    request = {
        "request_id":      request_id,
        "time_of_request": datetime.now().isoformat(),
        "transcript":      transcript,
        "is_vague":        retrieval["is_vague"],
        "situations":      situations,
        "status":          "PENDING",
        "heap_key":        max(s["heap_key"] for s in situations) if situations else 0,
        "escalation_stage": 0,
        "handoff_logs":    handoff_logs,
    }
    request_store.add(request)
    # Not pushed to priority_queue yet — waits for HITL approval (POST /approve)

    cleanup_temp(request_id)

    return PipelineResponse(
        request_id=request_id,
        transcript=transcript,
        is_vague=retrieval["is_vague"],
        situations=situations,
        handoff_logs=handoff_logs,
    )
