from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.db import UsageDatabase, get_db
from app.llm import LLMService
from app.schemas import (
    ChatRequest,
    HealthResponse,
    UsageResponse,
)

app = FastAPI(
    title="PodMentor",
    description="Cost-aware Kubernetes SRE code assistant with resilient LLM routing and usage tracking.",
    version="0.2.0",
)

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_configured_db(settings: SettingsDep) -> UsageDatabase:
    return get_db(settings.database_path)


DBDep = Annotated[UsageDatabase, Depends(get_configured_db)]


def get_configured_llm(settings: SettingsDep, db: DBDep) -> LLMService:
    return LLMService(settings=settings, db=db)


LLMDep = Annotated[LLMService, Depends(get_configured_llm)]


@app.get("/health", response_model=HealthResponse)
def health(settings: SettingsDep) -> dict:
    """Liveness probe: process is up. Fast, no external calls or DB connections."""
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.post("/chat")
async def chat(request: ChatRequest, llm_service: LLMDep):
    """Handle chat queries with retry, timeout, fallback model routing, and streaming support."""
    if request.stream:
        return StreamingResponse(
            llm_service.stream_chat(
                message=request.message,
                model_override=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    response = await llm_service.generate_chat(
        message=request.message,
        model_override=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    return response


@app.get("/usage", response_model=UsageResponse)
def get_usage(
    db: DBDep,
    limit: Annotated[int, Query(ge=1, le=500, description="Max recent requests to return")] = 50,
) -> dict:
    """Return aggregated token metrics, cumulative cost in USD, and breakdown by model."""
    return db.get_usage_summary(limit=limit)


@app.delete("/usage")
def clear_usage(db: DBDep) -> dict:
    """Clear usage history (primarily for automated testing and administrative resets)."""
    db.clear_all()
    return {"status": "cleared"}
