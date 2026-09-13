from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import RoutingMode
from app.core.heuristic_analyzer import heuristic_analyzer
from app.core.model_registry import registry
from app.core.openrouter_client import telemetry_store
from app.core.router_engine import router_engine

router = APIRouter(prefix="/api", tags=["Gateway Telemetry & Admin"])


class ModeChangeRequest(BaseModel):
    mode: RoutingMode


class ClassifyTestRequest(BaseModel):
    prompt: str
    has_image: bool = False
    has_tools: bool = False


@router.get("/telemetry/stats")
async def get_stats():
    """Retrieve runtime performance, latency and fallback statistics."""
    stats = telemetry_store.get_stats()
    stats["active_mode"] = router_engine.active_mode.value
    stats["total_free_models"] = len(registry.get_all())
    return stats


@router.get("/telemetry/logs")
async def get_logs(limit: int = 50):
    """Retrieve recent routing telemetry events."""
    return telemetry_store.get_recent(limit=limit)


@router.get("/models/free")
async def get_free_models():
    """Retrieve full metadata for all discovered Free Tier models."""
    return {
        "count": len(registry.get_all()),
        "last_refresh": registry.last_refresh,
        "models": registry.get_all()
    }


@router.post("/models/refresh")
async def refresh_models():
    """Trigger manual discovery of OpenRouter free tier models."""
    count = await registry.refresh_models(force=True)
    return {"status": "ok", "message": f"Successfully refreshed models registry: {count} free models available."}


@router.post("/config/mode")
async def set_mode(payload: ModeChangeRequest):
    """Switch routing strategy mode in real-time."""
    router_engine.set_mode(payload.mode)
    return {"status": "ok", "active_mode": router_engine.active_mode.value}


@router.post("/test/classify")
async def test_classify(payload: ClassifyTestRequest):
    """Playground route: test routing decision on simulated user prompt without calling completion."""
    simulated_payload: Dict[str, Any] = {
        "messages": [{"role": "user", "content": payload.prompt}]
    }
    if payload.has_image:
        simulated_payload["messages"][0]["content"] = [
            {"type": "text", "text": payload.prompt},
            {"type": "image_url", "image_url": {"url": "https://example.com/test.jpg"}}
        ]
    if payload.has_tools:
        simulated_payload["tools"] = [{"type": "function", "function": {"name": "sample_tool"}}]

    decision = await router_engine.decide_route(simulated_payload)

    return {
        "decision": decision,
        "primary_model_details": registry.get_by_id(decision.primary_model)
    }
