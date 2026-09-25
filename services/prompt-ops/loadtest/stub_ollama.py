"""An instant, fake Ollama `/api/chat` for load tests.

The seeded demo prompts pin `ollama`, so a load test needs something answering
there. This stub replies immediately with a fixed completion, which makes the
measured latency the gateway's own work plus one real local HTTP hop to the
provider — not model inference.

    uv run uvicorn loadtest.stub_ollama:app --port 11434
"""

from fastapi import FastAPI

app = FastAPI()


@app.post("/api/chat")
async def chat() -> dict:
    return {
        "message": {"role": "assistant", "content": "stub reply"},
        "prompt_eval_count": 12,
        "eval_count": 2,
        "done": True,
    }
