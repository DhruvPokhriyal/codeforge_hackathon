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

from config import SCALE_FACTOR

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
    if llm is None:
        situations = [dict(_FALLBACK_SITUATION)]
    else:
        chunks_text = "\n\n".join(
            f"[Source: {c['source']} p.{c['page']} | Score: {c['score']:.2f}]\n{c['text']}"
            for c in chunks[:6]
        )
        prompt = RAG_TRIAGE_PROMPT.format(
            transcript=transcript,
            chunks_text=chunks_text,
        )
        resp = llm(prompt, max_tokens=1200, temperature=0.15)
        raw = resp["choices"][0]["text"].strip()

        try:
            start, end = raw.find("["), raw.rfind("]") + 1
            situations = json.loads(raw[start:end])
        except Exception:
            situations = [dict(_FALLBACK_SITUATION)]

    for s in situations:
        s["heap_key"] = compute_heap_key(
            s.get("severity_score", 75),
            s.get("travel_time_min", 10),
            s.get("resolution_time_min", 20),
        )
        s["source_chunks"] = [f"{c['source']} p.{c['page']}" for c in chunks[:3]]
        s["selected"] = False  # HITL manager sets this in POST /approve

    return situations
