from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt_key: str = Field(examples=["prompt.support-bot"])
    unit_id: str = Field(examples=["user-42"])
    input: str = Field(examples=["My order hasn't arrived yet."])


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class RoutingAttempt(BaseModel):
    provider: str
    outcome: str  # ok | failed | circuit_open
    error: str | None = None


class ChatResponse(BaseModel):
    variant: str | None
    provider: str
    model: str
    output: str
    usage: Usage
    latency_ms: int
    # Providers tried, in order; more than one entry means a failover happened.
    routing: list[RoutingAttempt] = []
