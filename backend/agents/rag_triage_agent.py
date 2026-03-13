# backend/agents/rag_triage_agent.py
# STEP 5 — RAG LLM + Triage
#
# Core triage agent. Reads the transcript + retrieved PDF chunks and generates
# a structured multi-situation report via the local LLaMA 3.2 3B model.
#
# Public interface:
#   compute_heap_key(severity_score, travel_time, resolution_time) -> float
#     · Standalone utility — can be called without LLM
#
#   run_rag_triage(transcript: str, chunks: list, llm) -> list[dict]
#     · Returns list of Situation dicts (compatible with schemas.Situation)
#     · Each situation has: label, severity, severity_score, confidence,
#       travel_time_min, resolution_time_min, heap_key, materials,
#       instructions, reasoning, source_chunks, selected=False

import json

from llama_cpp import Llama

from config import SCALE_FACTOR, LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_CONTEXT_SIZE

RAG_TRIAGE_PROMPT = """You are an emergency medical AI at a disaster shelter.
You have received a distress call and retrieved relevant first-aid information.

TRANSCRIPT: "{transcript}"

RETRIEVED INFORMATION:
{chunks_text}

Generate a structured emergency response report.
List ALL plausible situations (2-4). For each situation provide:
- label: short name of the condition
- severity: CRITICAL, HIGH, MEDIUM, or LOW
- severity_score: CRITICAL=100, HIGH=75, MEDIUM=50, LOW=25
- travel_time_min: estimated minutes to reach person
- resolution_time_min: estimated minutes to resolve on-site
- confidence: float 0-1 representing certainty
- materials: list of {{"item": str, "quantity": int}}
- instructions: numbered step-by-step actions for the volunteer
- reasoning: why this severity level was chosen

Respond ONLY with valid JSON array. No extra text.
[
  {{
    "label":               "Cardiac Arrest",
    "severity":            "CRITICAL",
    "severity_score":      100,
    "travel_time_min":     8,
    "resolution_time_min": 20,
    "confidence":          0.91,
    "materials":           [{{"item": "AED", "quantity": 1}}, {{"item": "CPR Mask", "quantity": 1}}],
    "instructions":        ["Call for help immediately", "Begin CPR: 30 compressions, 2 breaths"],
    "reasoning":           "Unresponsive person with abnormal leg position suggests cardiac or neurological event"
  }}
]"""

_FALLBACK_SITUATION = {
    "label": "Unknown Emergency",
    "severity": "HIGH",
    "severity_score": 75,
    "travel_time_min": 10,
    "resolution_time_min": 20,
    "confidence": 0.5,
    "materials": [],
    "instructions": ["Assess situation carefully on arrival"],
    "reasoning": "JSON parse failed — defaulted to HIGH as safe upper bound",
}


def _safe_completion_budget(llm, prompt: str) -> int:
    """
    Compute a safe max_tokens for completion so prompt + completion fit in context.
    Returns at least 1 token when generation is possible.
    """
    # Keep a small reserve for BOS/EOS and internal separators in llama.cpp.
    safety_margin = 32

    try:
        # Preferred runtime context size from loaded model instance.
        runtime_ctx = llm.n_ctx() if callable(getattr(llm, "n_ctx", None)) else LLM_CONTEXT_SIZE
    except Exception:
        runtime_ctx = LLM_CONTEXT_SIZE

    try:
        prompt_tokens = len(llm.tokenize(prompt.encode("utf-8"), add_bos=False))
    except Exception:
        # If tokenization fails, fall back to configured budget.
        return max(1, LLM_MAX_TOKENS)

    available = runtime_ctx - prompt_tokens - safety_margin
    if available <= 0:
        return 1

    return max(1, min(LLM_MAX_TOKENS, available))


def compute_heap_key(
    severity_score: int, travel_time: int, resolution_time: int
) -> float:
    """
    Priority key formula: higher = more urgent.
    heap_key = severity_score × SCALE_FACTOR - (travel_time_min × 2) - resolution_time_min

    SCALE_FACTOR (1000) ensures time penalties are significant but cannot
    fully overshadow severity — a CRITICAL case always outranks a LOW one
    regardless of travel time.
    """
    return float(severity_score * SCALE_FACTOR - (travel_time * 2) - resolution_time)


def run_rag_triage(transcript: str, chunks: list, llm) -> list:
    """
    Run the RAG triage prompt and parse the multi-situation JSON response.
    Attaches heap_key, source_chunks, and selected=False to each situation.
    Falls back to _FALLBACK_SITUATION if LLM is None or output cannot be parsed.
    """
    print(f"[RAG_TRIAGE] Called with transcript='{transcript[:100]}', {len(chunks)} chunks, llm={llm is not None}")
    if llm is None:
        print("[RAG_TRIAGE] LLM is None, using FALLBACK situation")
        situations = [dict(_FALLBACK_SITUATION)]
    else:
        # Progressively trim chunks until the prompt fits within context
        # with enough room for generation (at least 256 tokens)
        MIN_GENERATION_TOKENS = 256
        max_chunk_count = min(6, len(chunks))
        max_tokens = 0

        while max_chunk_count > 0:
            chunks_text = "\n\n".join(
                f"[Source: {c['source']} p.{c['page']} | Score: {c['score']:.2f}]\n{c['text']}"
                for c in chunks[:max_chunk_count]
            )
            prompt = RAG_TRIAGE_PROMPT.format(
                transcript=transcript,
                chunks_text=chunks_text,
            )
            max_tokens = _safe_completion_budget(llm, prompt)
            print(f"[RAG_TRIAGE] Trying {max_chunk_count} chunks, prompt={len(prompt)} chars, max_tokens={max_tokens}")
            if max_tokens >= MIN_GENERATION_TOKENS:
                break
            max_chunk_count -= 1
            print(f"[RAG_TRIAGE] Prompt too large, reducing to {max_chunk_count} chunks")

        if max_chunk_count == 0 or max_tokens < MIN_GENERATION_TOKENS:
            # Even with 0 chunks the prompt doesn't fit — use fallback
            print("[RAG_TRIAGE] Prompt too large even with 0 chunks, using FALLBACK")
            chunks_text = "(no context available)"
            prompt = RAG_TRIAGE_PROMPT.format(transcript=transcript, chunks_text=chunks_text)
            max_tokens = _safe_completion_budget(llm, prompt)
            if max_tokens < MIN_GENERATION_TOKENS:
                print(f"[RAG_TRIAGE] Cannot generate: max_tokens={max_tokens}, using FALLBACK situation")
                situations = [dict(_FALLBACK_SITUATION)]
                # skip the LLM call entirely
                max_tokens = 0

        print(f"[RAG_TRIAGE] Final: {max_chunk_count} chunks, prompt={len(prompt)} chars, max_tokens={max_tokens}")

        if max_tokens > 0:
            try:
                resp = llm(prompt, max_tokens=max_tokens, temperature=LLM_TEMPERATURE)
                raw = resp["choices"][0]["text"].strip()
                print(f"[RAG_TRIAGE] LLM raw output (first 1000 chars): {raw[:1000]}")
            except ValueError as e:
                print(f"[RAG_TRIAGE] ValueError: {e}")
                # Guard against rare off-by-one context checks in llama.cpp.
                if "exceed context window" in str(e).lower():
                    retry_tokens = max(1, max_tokens - 64)
                    try:
                        resp = llm(prompt, max_tokens=retry_tokens, temperature=LLM_TEMPERATURE)
                        raw = resp["choices"][0]["text"].strip()
                        print(f"[RAG_TRIAGE] Retry LLM raw output: {raw[:1000]}")
                    except Exception as e2:
                        print(f"[RAG_TRIAGE] Retry also failed: {e2}")
                        raw = "[]"
                else:
                    raw = "[]"
            except Exception as e:
                print(f"[RAG_TRIAGE] Exception: {e}")
                raw = "[]"

            try:
                start, end = raw.find("["), raw.rfind("]") + 1
                print(f"[RAG_TRIAGE] JSON slice: start={start}, end={end}")
                situations = json.loads(raw[start:end])
                print(f"[RAG_TRIAGE] Parsed {len(situations)} situations from LLM")
                if not situations:
                    print("[RAG_TRIAGE] Parsed list is empty, using FALLBACK")
                    situations = [dict(_FALLBACK_SITUATION)]
            except Exception as e:
                print(f"[RAG_TRIAGE] JSON parse failed: {e}, using FALLBACK")
                situations = [dict(_FALLBACK_SITUATION)]
        # else: situations already set to FALLBACK above

    for s in situations:
        s["heap_key"] = compute_heap_key(
            s.get("severity_score", 75),
            s.get("travel_time_min", 10),
            s.get("resolution_time_min", 20),
        )
        s["source_chunks"] = [f"{c['source']} p.{c['page']}" for c in chunks[:3]]
        s["selected"] = False  # HITL manager sets this in POST /approve

    print(f"[RAG_TRIAGE] Returning {len(situations)} situations")
    return situations
