import uuid
import time
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

# LLM via Ollama — wrapper that mimics the llama-cpp interface
_llm = None


class OllamaLLM:
    """Thin wrapper around Ollama's HTTP API.

    Callable interface matches llama-cpp-python so the rest of the codebase
    (rag_triage_agent, vagueness_agent) works unchanged:
        resp = llm(prompt, max_tokens=1200, temperature=0.15)
        text = resp["choices"][0]["text"]
    """

    def __init__(self, base_url: str, model: str, n_ctx: int = 8192):
        self._url = f"{base_url}/api/generate"
        self._model = model
        self._n_ctx = n_ctx

    def n_ctx(self) -> int:
        return self._n_ctx

    def tokenize(self, text: bytes, add_bos: bool = False) -> list:
        """Rough token estimate (≈4 chars per token). Ollama doesn't expose tokenize."""
        return [0] * (len(text) // 4)

    def __call__(self, prompt: str, max_tokens: int = 1200, temperature: float = 0.15, **_kw) -> dict:
        import requests
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        resp = requests.post(self._url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return {"choices": [{"text": data.get("response", "")}]}

    def __repr__(self):
        return f"OllamaLLM(model={self._model})"


class ONNXLLM:
    """ONNX Runtime implementation for Mac ANE"""
    def __init__(self, model_path: str, n_ctx: int = 8192):
        self._n_ctx = n_ctx
        import onnxruntime_genai as og
        print(f"[LLM] Loading ONNX model from {model_path} with CoreMLExecutionProvider")
        self.model = og.Model(model_path)
        self.tokenizer = og.Tokenizer(self.model)

    def n_ctx(self) -> int:
        return self._n_ctx

    def tokenize(self, text: bytes, add_bos: bool = False) -> list:
        return self.tokenizer.encode(text.decode("utf-8"))

    def __call__(self, prompt: str, max_tokens: int = 1200, temperature: float = 0.15, **_kw) -> dict:
        import onnxruntime_genai as og
        tokens = self.tokenizer.encode(prompt)
        params = og.GeneratorParams(self.model)
        params.set_search_options({"max_length": len(tokens) + max_tokens, "temperature": temperature})
        params.input_ids = tokens

        output_tokens = self.model.generate(params)
        generated_tokens = output_tokens[0][len(tokens):]
        text = self.tokenizer.decode(generated_tokens)
        return {"choices": [{"text": text}]}

    def __repr__(self):
        return "ONNXLLM(ANE)"


class OpenVINOLLM:
    """OpenVINO implementation for Intel Ultra Gen1 NPU"""
    def __init__(self, model_path: str, n_ctx: int = 8192):
        self._n_ctx = n_ctx
        import openvino_genai as ov_genai
        print(f"[LLM] Loading OpenVINO model from {model_path} on NPU")
        self.pipe = ov_genai.LLMPipeline(model_path, "NPU")

    def n_ctx(self) -> int:
        return self._n_ctx

    def tokenize(self, text: bytes, add_bos: bool = False) -> list:
        return [0] * (len(text) // 4)

    def __call__(self, prompt: str, max_tokens: int = 1200, temperature: float = 0.15, **_kw) -> dict:
        import openvino_genai as ov_genai
        config = ov_genai.GenerationConfig()
        config.max_new_tokens = max_tokens
        config.temperature = temperature

        output = self.pipe.generate(prompt, config)
        return {"choices": [{"text": output}]}

    def __repr__(self):
        return "OpenVINOLLM(NPU)"


_llm_npu = None

def _get_llm(npu_mode: bool = False):
    """Return an LLM instance. If npu_mode is True, use platform specific NPU inference."""
    global _llm, _llm_npu
    from config import OLLAMA_URL, OLLAMA_MODEL, LLM_CONTEXT_SIZE

    if npu_mode:
        if _llm_npu is None:
            import platform
            sys_os = platform.system()
            print(f"[LLM] NPU mode requested. Detected OS: {sys_os}")
            try:
                if sys_os == "Darwin":
                    print("[LLM] Initializing ONNX runtime for ANE...")
                    _llm_npu = ONNXLLM("models/onnx", n_ctx=LLM_CONTEXT_SIZE)
                else:
                    print("[LLM] Initializing OpenVINO for Intel NPU...")
                    _llm_npu = OpenVINOLLM("models/openvino", n_ctx=LLM_CONTEXT_SIZE)
            except Exception as e:
                print(f"[LLM] Error initializing NPU inference: {e}")
                print("[LLM] Falling back to OllamaLLM for development purposes...")
                import requests
                _llm_npu = OllamaLLM(base_url=OLLAMA_URL, model=OLLAMA_MODEL, n_ctx=LLM_CONTEXT_SIZE)
        return _llm_npu

    if _llm is None:
        import requests

        print(f"[LLM] Connecting to Ollama at {OLLAMA_URL}, model={OLLAMA_MODEL}")
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            if OLLAMA_MODEL not in models:
                # Try without tag
                base_names = [m.split(":")[0] for m in models]
                if OLLAMA_MODEL.split(":")[0] not in base_names:
                    print(f"[LLM] WARNING: {OLLAMA_MODEL} not found in Ollama. Available: {models}")
            print(f"[LLM] Ollama ready — using {OLLAMA_MODEL}")
        except Exception as e:
            print(f"[LLM] ERROR: Cannot reach Ollama at {OLLAMA_URL}: {e}")
            return None

        _llm = OllamaLLM(base_url=OLLAMA_URL, model=OLLAMA_MODEL, n_ctx=LLM_CONTEXT_SIZE)
    return _llm


@router.post("/pipeline", response_model=PipelineResponse)
async def run_pipeline(body: PipelineRequest):
    request_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"
    handoff_logs: list[dict] = []
    pipeline_start = time.time()
    print(f"\n[PIPELINE] ======= Starting pipeline for {request_id} =======")

    # Step 1 — Decode and save audio
    t0 = time.time()
    raw_path = save_base64_wav(body.audio_b64, request_id)
    clean_path = get_clean_path(request_id)
    print(f"[PIPELINE] Step 1 — Decode audio:       {time.time()-t0:.2f}s")

    # Step 2 — Denoise
    t0 = time.time()
    log_handoff("AUDIO_INPUT", "DENOISER", "start pipeline", {"request_id": request_id})
    denoise(raw_path, clean_path)
    print(f"[PIPELINE] Step 2 — Denoise:            {time.time()-t0:.2f}s")

    # Step 3 — Transcribe
    t0 = time.time()
    log_handoff("DENOISER", "INTAKE_AGENT", "audio cleaned", {"clean_path": clean_path})
    transcript = transcribe(clean_path)
    print(f"[PIPELINE] Step 3 — Transcribe:         {time.time()-t0:.2f}s  transcript='{transcript[:120]}'")

    # Step 4 — Retrieve RAG chunks
    t0 = time.time()
    log_handoff(
        "INTAKE_AGENT", "RETRIEVAL_AGENT", "transcribed", {"transcript": transcript}
    )
    retrieval = retrieve(transcript)
    chunks = retrieval["chunks"]
    print(f"[PIPELINE] Step 4 — RAG retrieval:      {time.time()-t0:.2f}s  chunks={len(chunks)}, is_vague={retrieval['is_vague']}, top_score={retrieval['top_score']:.2f}")

    # Step 4b — Vagueness resolution
    if retrieval["is_vague"]:
        t0 = time.time()
        log_handoff(
            "RETRIEVAL_AGENT",
            "VAGUENESS_AGENT",
            f"top_score={retrieval['top_score']:.2f} < threshold=0.8",
            {"transcript": transcript, "top_score": retrieval["top_score"]},
        )
        handoff_logs.append(
            {
                "step": "vagueness_resolved",
                "reason": f"low confidence ({retrieval['top_score']:.2f})",
            }
        )
        chunks = resolve_and_retrieve(transcript, _get_llm(body.npu_mode), retrieve)
        print(f"[PIPELINE] Step 4b — Vagueness resolve: {time.time()-t0:.2f}s  expanded to {len(chunks)} chunks")

    # Step 5 — RAG triage
    t0 = time.time()
    log_handoff(
        "RETRIEVAL_AGENT",
        "RAG_TRIAGE_AGENT",
        "chunks ready",
        {"chunk_count": len(chunks)},
    )
    llm = _get_llm(body.npu_mode)
    situations = run_rag_triage(transcript, chunks, llm)
    print(f"[PIPELINE] Step 5 — RAG triage (LLM):   {time.time()-t0:.2f}s  {len(situations)} situations")
    for i, s in enumerate(situations):
        print(f"[PIPELINE]   situation[{i}]: label={s.get('label')}, severity={s.get('severity')}, materials={len(s.get('materials', []))}")

    # Step 6 — Inventory annotation
    t0 = time.time()
    log_handoff(
        "RAG_TRIAGE_AGENT",
        "LOGISTICS_AGENT",
        "situations ready",
        {"count": len(situations)},
    )
    situations = annotate_situations(situations)
    print(f"[PIPELINE] Step 6 — Inventory annotate: {time.time()-t0:.2f}s")

    # Store request
    t0 = time.time()
    request = {
        "request_id": request_id,
        "time_of_request": datetime.now().isoformat(),
        "transcript": transcript,
        "is_vague": retrieval["is_vague"],
        "situations": situations,
        "status": "PENDING",
        "heap_key": max(s["heap_key"] for s in situations) if situations else 0,
        "escalation_stage": 0,
        "handoff_logs": handoff_logs,
    }
    request_store.add(request)

    cleanup_temp(request_id)

    response = PipelineResponse(
        request_id=request_id,
        transcript=transcript,
        is_vague=retrieval["is_vague"],
        situations=situations,
        handoff_logs=handoff_logs,
    )
    print(f"[PIPELINE] Step 7 — Store + serialize:  {time.time()-t0:.2f}s")

    total = time.time() - pipeline_start
    print(f"[PIPELINE] ======= TOTAL {request_id}: {total:.2f}s =======\n")
    return response
