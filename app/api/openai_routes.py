import time
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.core.model_registry import registry
from app.core.openrouter_client import openrouter_client
from app.core.router_engine import router_engine

router = APIRouter(prefix="/v1", tags=["OpenAI Standard Compatibility"])


@router.get("/models")
async def list_models():
    """List available Free Tier models in standard OpenAI ModelList format."""
    models = registry.get_all()

    data = [
        {
            "id": "openrouter/auto",
            "object": "model",
            "created": 1700000000,
            "owned_by": "gateway",
            "permission": [],
            "root": "openrouter/auto",
            "parent": None,
            "description": "Smart Auto-Routing: Intelligently selects the best Free Tier model"
        },
        {
            "id": "hermes-router",
            "object": "model",
            "created": 1700000000,
            "owned_by": "gateway",
            "permission": [],
            "root": "hermes-router",
            "parent": None,
            "description": "Alias for Hermes agent dynamic free router"
        }
    ]

    for m in models:
        data.append({
            "id": m.id,
            "object": "model",
            "created": int(m.last_seen.timestamp()),
            "owned_by": m.provider.lower(),
            "permission": [],
            "root": m.id,
            "parent": None,
            "context_length": m.context_length,
            "has_vision": m.has_vision,
            "has_tools": m.has_tools,
            "is_reasoning": m.is_reasoning,
            "is_coder": m.is_coder
        })

    return {"object": "list", "data": data}


@router.post("/chat/completions")
async def chat_completions(request: Request, response: Response):
    """OpenAI standard Chat Completions endpoint with intelligent free model routing."""
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    requested_model = body.get("model", "openrouter/auto")
    is_stream = bool(body.get("stream", False))

    # Compute routing decision (Heuristic + LLM synergy)
    decision = await router_engine.decide_route(body, requested_model=requested_model)

    if is_stream:
        # Stream response directly via SSE
        return StreamingResponse(
            openrouter_client.execute_stream(body, decision),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Selected-Model": decision.primary_model,
                "X-Routing-Mode": decision.routing_mode
            }
        )
    else:
        # Standard non-streaming completion
        t_start = time.time()
        try:
            result = await openrouter_client.execute_completion(body, decision)
            latency_ms = round((time.time() - t_start) * 1000.0, 1)

            response.headers["X-Selected-Model"] = decision.primary_model
            response.headers["X-Routing-Mode"] = decision.routing_mode
            response.headers["X-Latency-Ms"] = str(latency_ms)

            return result
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
