# backend/agents/vagueness_agent.py
# STEP 4b — LLM Vagueness Resolver
#
# Triggered when retrieval_agent reports is_vague=True (top_score < 0.8).
# Generates 2-3 possible medical hypotheses per severity level, then retries
# retrieval for each hypothesis and merges the results into an enriched chunk set.
#
# Public interface:
#   resolve_and_retrieve(transcript: str, llm, retrieve_fn) -> list[dict]
#     · Returns merged, deduplicated, score-sorted chunks (max 10)
#     · Each chunk gains extra fields: "hypothesis", "hypothesis_severity"

import json

from llama_cpp import Llama

VAGUENESS_PROMPT = """You are an emergency medical AI.
The following distress report is unclear or ambiguous.
Generate 2-3 possible medical conditions for each severity level.

Report: "{transcript}"

Respond ONLY in JSON:
{{
  "CRITICAL": ["cardiac arrest", "stroke", "internal bleeding"],
  "HIGH":     ["fracture with shock", "spinal injury"],
  "MEDIUM":   ["seizure", "diabetic episode"],
  "LOW":      ["exhaustion", "dehydration"]
}}"""


def resolve_vagueness(transcript: str, llm: Llama) -> dict:
    """
    Ask LLM to generate plausible conditions per severity level for a vague transcript.
    Falls back to safe defaults if LLM output is unparseable.
    """
    prompt = VAGUENESS_PROMPT.format(transcript=transcript)
    resp = llm(prompt, max_tokens=400, temperature=0.2)
    raw = resp["choices"][0]["text"].strip()
    try:
        start, end = raw.find("{"), raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        return {
            "CRITICAL": ["cardiac arrest"],
            "HIGH": ["fracture"],
            "MEDIUM": ["fever"],
            "LOW": ["dehydration"],
        }


def resolve_and_retrieve(transcript: str, llm: Llama, retrieve_fn) -> list:
    """
    Full vagueness resolution pipeline:
      1. Generate per-severity hypotheses from LLM
      2. Call retrieve_fn for each hypothesis query (top_k=3)
      3. Merge chunks, deduplicate by text content, sort by score descending
    Returns top 10 unique chunks with hypothesis metadata attached.
    """
    hypotheses = resolve_vagueness(transcript, llm)
    all_chunks: list[dict] = []
    seen_texts: set[str] = set()

    for severity, conditions in hypotheses.items():
        for condition in conditions:
            query = f"{condition} first aid emergency treatment"
            result = retrieve_fn(query, top_k=3)
            for chunk in result["chunks"]:
                if chunk["text"] not in seen_texts:
                    seen_texts.add(chunk["text"])
                    chunk["hypothesis"] = condition
                    chunk["hypothesis_severity"] = severity
                    all_chunks.append(chunk)

    return sorted(all_chunks, key=lambda c: c["score"], reverse=True)[:10]
