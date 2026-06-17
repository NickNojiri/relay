from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt_key: str = Field(examples=["prompt.support-bot"])
    unit_id: str = Field(examples=["user-42"])
    input: str = Field(examples=["My order hasn't arrived yet."])


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class ChatResponse(BaseModel):
    variant: str | None
    provider: str
    model: str
    output: str
    usage: Usage
    latency_ms: int
