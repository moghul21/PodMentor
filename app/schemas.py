"""Request and response Pydantic models for PodMentor."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status indicator")
    app: str = Field(..., description="Application name")
    environment: str = Field(..., description="Runtime environment")


class TokenUsage(BaseModel):
    prompt_tokens: int = Field(..., ge=0, description="Input/prompt tokens count")
    completion_tokens: int = Field(..., ge=0, description="Generated completion tokens count")
    total_tokens: int = Field(..., ge=0, description="Total tokens count")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Question or prompt sent to PodMentor")
    model: str | None = Field(default=None, description="Optional model override")
    stream: bool = Field(default=False, description="Set to true to stream response chunks as SSE")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=2048, ge=1, le=8192, description="Maximum tokens to generate")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Answer text from LLM")
    model_used: str = Field(..., description="The actual model that generated the answer")
    fallback_used: bool = Field(default=False, description="Whether fallback model was activated")
    tokens: TokenUsage = Field(..., description="Token usage details")
    cost_usd: float = Field(..., ge=0.0, description="Estimated cost in USD")
    latency_ms: float = Field(..., ge=0.0, description="Request execution latency in milliseconds")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")


class ModelUsageSummary(BaseModel):
    requests: int = Field(..., ge=0, description="Number of requests handled by this model")
    prompt_tokens: int = Field(..., ge=0, description="Total prompt tokens for this model")
    completion_tokens: int = Field(..., ge=0, description="Total completion tokens for this model")
    total_tokens: int = Field(..., ge=0, description="Total tokens for this model")
    cost_usd: float = Field(..., ge=0.0, description="Total cost in USD for this model")


class UsageLogEntry(BaseModel):
    id: int = Field(..., description="Log entry identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    model: str = Field(..., description="Model name")
    provider: str = Field(..., description="Provider name (e.g. gemini, mock)")
    prompt_tokens: int = Field(..., ge=0, description="Prompt tokens")
    completion_tokens: int = Field(..., ge=0, description="Completion tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens")
    cost_usd: float = Field(..., ge=0.0, description="Calculated cost in USD")
    latency_ms: float = Field(..., ge=0.0, description="Execution latency in ms")
    status: str = Field(..., description="Execution status ('success', 'fallback', 'failed')")
    fallback_used: bool = Field(..., description="Whether fallback was used")


class UsageResponse(BaseModel):
    total_requests: int = Field(..., ge=0, description="Total LLM requests recorded")
    total_prompt_tokens: int = Field(..., ge=0, description="Sum of prompt tokens across all calls")
    total_completion_tokens: int = Field(..., ge=0, description="Sum of completion tokens across all calls")
    total_tokens: int = Field(..., ge=0, description="Sum of all tokens consumed")
    total_cost_usd: float = Field(..., ge=0.0, description="Total cumulative cost in USD")
    by_model: dict[str, ModelUsageSummary] = Field(default_factory=dict, description="Breakdown by model")
    recent_requests: list[UsageLogEntry] = Field(default_factory=list, description="Recent request logs")
