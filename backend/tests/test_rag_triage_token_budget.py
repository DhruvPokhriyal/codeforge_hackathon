from agents.rag_triage_agent import run_rag_triage


class _FakeLLM:
    def __init__(self, n_ctx=4096):
        self._n_ctx = n_ctx
        self.last_max_tokens = None

    def n_ctx(self):
        return self._n_ctx

    def tokenize(self, b, add_bos=False):
        # Approximate tokenizer: 1 token per byte for deterministic budgeting.
        return list(b)

    def __call__(self, prompt, max_tokens, temperature):
        self.last_max_tokens = max_tokens
        return {
            "choices": [
                {
                    "text": '[{"label":"X","severity":"HIGH","severity_score":75,"travel_time_min":5,"resolution_time_min":10,"confidence":0.7,"materials":[],"instructions":[],"reasoning":"ok"}]'
                }
            ]
        }


def test_rag_triage_clamps_max_tokens_to_context():
    llm = _FakeLLM(n_ctx=4096)
    long_transcript = "A" * 3800
    chunks = [
        {
            "source": "protocol.pdf",
            "page": 1,
            "score": 0.92,
            "text": "B" * 1200,
        }
    ]

    situations = run_rag_triage(long_transcript, chunks, llm)

    assert situations
    assert llm.last_max_tokens is not None
    assert 1 <= llm.last_max_tokens <= 1200
