import asyncio
import collections
from datetime import datetime, timezone
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.core.router_engine import RoutingDecision

logger = logging.getLogger("gateway.client")


class TelemetryEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    requested_model: Optional[str] = None
    selected_model: str
    fallback_used: bool = False
    retries_count: int = 0
    latency_ms: float = 0.0
    status_code: int = 200
    routing_mode: str = "SYNERGY"
    tags: List[str] = Field(default_factory=list)
    tokens_estimated: int = 0
    prompt_snippet: str = ""
    error: Optional[str] = None


class TelemetryStore:
    def __init__(self, maxlen: int = 100):
        self.events: collections.deque[TelemetryEvent] = collections.deque(maxlen=maxlen)
        self.total_requests: int = 0
        self.total_fallbacks: int = 0
        self.total_retries: int = 0

    def record(self, event: TelemetryEvent):
        self.events.appendleft(event)
        self.total_requests += 1
        if event.fallback_used:
            self.total_fallbacks += 1
        self.total_retries += event.retries_count

    def get_recent(self, limit: int = 50) -> List[TelemetryEvent]:
        return list(self.events)[:limit]

    def get_stats(self) -> Dict[str, Any]:
        avg_latency = (
            sum(e.latency_ms for e in self.events) / len(self.events)
            if self.events else 0.0
        )
        return {
            "total_requests": self.total_requests,
            "total_fallbacks": self.total_fallbacks,
            "total_retries": self.total_retries,
            "average_latency_ms": round(avg_latency, 1),
            "recent_count": len(self.events)
        }


telemetry_store = TelemetryStore()


class OpenRouterClient:
    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

    @classmethod
    def _extract_prompt_snippet(cls, payload: Dict[str, Any]) -> str:
        messages = payload.get("messages", [])
        if messages:
            last_msg = messages[-1]
            content = last_msg.get("content", "")
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = " ".join(parts)
            return str(content)[:80]
        return ""

    @classmethod
    async def execute_completion(
        cls,
        payload: Dict[str, Any],
        decision: RoutingDecision
    ) -> Dict[str, Any]:
        """Execute non-streaming completion with exponential backoff retry and fallback cascade."""
        models_to_try = [decision.primary_model] + decision.fallback_models
        start_time = time.time()
        total_retries = 0
        prompt_snippet = cls._extract_prompt_snippet(payload)

        last_error = None
        last_status = 500

        for attempt_idx, candidate_model in enumerate(models_to_try):
            fallback_used = (attempt_idx > 0)
            req_body = dict(payload)
            req_body["model"] = candidate_model

            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/jmast321/api_gateway",
                "X-Title": "Hermes AI Router"
            }

            # Retry loop on current candidate model
            for retry in range(settings.MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
                        resp = await client.post(cls.OPENROUTER_URL, headers=headers, json=req_body)
                        last_status = resp.status_code

                        # Successful response
                        if resp.status_code == 200:
                            elapsed_ms = (time.time() - start_time) * 1000.0
                            data = resp.json()

                            # Record telemetry
                            telemetry_store.record(TelemetryEvent(
                                requested_model=payload.get("model"),
                                selected_model=candidate_model,
                                fallback_used=fallback_used,
                                retries_count=total_retries,
                                latency_ms=round(elapsed_ms, 1),
                                status_code=200,
                                routing_mode=decision.routing_mode,
                                tags=decision.heuristic_profile.detected_tags,
                                tokens_estimated=decision.estimated_tokens,
                                prompt_snippet=prompt_snippet
                            ))
                            return data

                        # Rate limit (429) or Server error (502, 503, 504) -> Backoff retry
                        if resp.status_code in (429, 500, 502, 503, 504):
                            total_retries += 1
                            wait_seconds = settings.BACKOFF_FACTOR ** (retry + 1)
                            logger.warning(
                                f"Model {candidate_model} returned {resp.status_code}. "
                                f"Backing off for {wait_seconds:.1f}s (retry {retry + 1}/{settings.MAX_RETRIES})..."
                            )
                            await asyncio.sleep(wait_seconds)
                            continue

                        # Other client error (e.g. 400 Bad Request, context too long, etc.) -> Cascade immediately to next model
                        error_text = resp.text
                        logger.warning(f"Model {candidate_model} returned {resp.status_code}: {error_text}. Cascading to fallback...")
                        last_error = error_text
                        break

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    total_retries += 1
                    wait_seconds = settings.BACKOFF_FACTOR ** (retry + 1)
                    logger.warning(f"Network exception on {candidate_model}: {e}. Retrying in {wait_seconds:.1f}s...")
                    await asyncio.sleep(wait_seconds)

        elapsed_ms = (time.time() - start_time) * 1000.0
        telemetry_store.record(TelemetryEvent(
            requested_model=payload.get("model"),
            selected_model=decision.primary_model,
            fallback_used=True,
            retries_count=total_retries,
            latency_ms=round(elapsed_ms, 1),
            status_code=last_status,
            routing_mode=decision.routing_mode,
            tags=decision.heuristic_profile.detected_tags,
            tokens_estimated=decision.estimated_tokens,
            prompt_snippet=prompt_snippet,
            error=last_error or "All free models in fallback chain were exhausted."
        ))

        raise RuntimeError(f"OpenRouter Gateway Error: All models exhausted. Last error: {last_error}")

    @classmethod
    async def execute_stream(
        cls,
        payload: Dict[str, Any],
        decision: RoutingDecision
    ) -> AsyncGenerator[bytes, None]:
        """Execute streaming SSE completion with model fallback."""
        models_to_try = [decision.primary_model] + decision.fallback_models
        start_time = time.time()
        prompt_snippet = cls._extract_prompt_snippet(payload)

        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jmast321/api_gateway",
            "X-Title": "Hermes AI Router"
        }

        for attempt_idx, candidate_model in enumerate(models_to_try):
            fallback_used = (attempt_idx > 0)
            req_body = dict(payload)
            req_body["model"] = candidate_model
            req_body["stream"] = True

            try:
                client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS)
                async with client.stream("POST", cls.OPENROUTER_URL, headers=headers, json=req_body) as response:
                    if response.status_code == 200:
                        elapsed_ms = (time.time() - start_time) * 1000.0
                        telemetry_store.record(TelemetryEvent(
                            requested_model=payload.get("model"),
                            selected_model=candidate_model,
                            fallback_used=fallback_used,
                            retries_count=0,
                            latency_ms=round(elapsed_ms, 1),
                            status_code=200,
                            routing_mode=decision.routing_mode,
                            tags=decision.heuristic_profile.detected_tags,
                            tokens_estimated=decision.estimated_tokens,
                            prompt_snippet=prompt_snippet
                        ))

                        async for chunk in response.aiter_bytes():
                            yield chunk
                        await client.aclose()
                        return
                    else:
                        logger.warning(
                            f"Streaming on {candidate_model} returned {response.status_code}. Cascading..."
                        )
                        await client.aclose()
                        continue
            except Exception as e:
                logger.warning(f"Streaming error on {candidate_model}: {e}. Cascading...")
                continue

        # If all stream attempts fail
        err_msg = json.dumps({"error": {"message": "All free model stream fallbacks failed."}})
        yield f"data: {err_msg}\n\ndata: [DONE]\n\n".encode("utf-8")


openrouter_client = OpenRouterClient()
