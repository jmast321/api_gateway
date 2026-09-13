import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger("gateway.model_registry")


class FreeModelInfo(BaseModel):
    id: str
    name: str
    context_length: int = 4096
    has_vision: bool = False
    has_audio: bool = False
    has_video: bool = False
    has_tools: bool = False
    is_reasoning: bool = False
    is_coder: bool = False
    provider: str = ""
    description: Optional[str] = ""
    pricing: Dict[str, float] = Field(default_factory=dict)
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Static fallback list in case OpenRouter API is unreachable during initial cold boot
CURATED_DEFAULT_FREE_MODELS = [
    FreeModelInfo(
        id="google/gemini-2.0-flash-exp:free",
        name="Google: Gemini 2.0 Flash Experimental (free)",
        context_length=1048576,
        has_vision=True,
        has_audio=True,
        has_video=True,
        has_tools=True,
        is_reasoning=False,
        is_coder=True,
        provider="Google",
        description="Next-gen multimodal workhorse model with 1M context window and near-zero latency."
    ),
    FreeModelInfo(
        id="deepseek/deepseek-r1:free",
        name="DeepSeek: DeepSeek R1 (free)",
        context_length=65536,
        has_vision=False,
        has_audio=False,
        has_video=False,
        has_tools=False,
        is_reasoning=True,
        is_coder=True,
        provider="DeepSeek",
        description="State-of-the-art open reasoning model with step-by-step chain of thought."
    ),
    FreeModelInfo(
        id="meta-llama/llama-3.3-70b-instruct:free",
        name="Meta: Llama 3.3 70B Instruct (free)",
        context_length=131072,
        has_vision=False,
        has_audio=False,
        has_video=False,
        has_tools=True,
        is_reasoning=False,
        is_coder=True,
        provider="Meta",
        description="Flagship open weights 70B parameter model with robust reasoning and agent tool support."
    ),
    FreeModelInfo(
        id="qwen/qwen-2.5-coder-32b-instruct:free",
        name="Qwen: Qwen 2.5 Coder 32B Instruct (free)",
        context_length=32768,
        has_vision=False,
        has_audio=False,
        has_video=False,
        has_tools=True,
        is_reasoning=False,
        is_coder=True,
        provider="Qwen",
        description="Top-tier coding assistant specialized in code synthesis, debugging and refactoring."
    ),
    FreeModelInfo(
        id="mistralai/mistral-small-24b-instruct-2501:free",
        name="Mistral: Mistral Small 3 (24B) (free)",
        context_length=32768,
        has_vision=True,
        has_audio=False,
        has_video=False,
        has_tools=True,
        is_reasoning=False,
        is_coder=False,
        provider="Mistral",
        description="Versatile multimodal small model with low latency and high precision."
    )
]


class ModelRegistry:
    def __init__(self):
        self._models: Dict[str, FreeModelInfo] = {m.id: m for m in CURATED_DEFAULT_FREE_MODELS}
        self.last_refresh: Optional[datetime] = None
        self._lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task] = None

    def get_all(self) -> List[FreeModelInfo]:
        return list(self._models.values())

    def get_by_id(self, model_id: str) -> Optional[FreeModelInfo]:
        return self._models.get(model_id)

    def is_free_model(self, model_id: str) -> bool:
        return model_id in self._models or model_id.endswith(":free")

    async def refresh_models(self, force: bool = False) -> int:
        """Fetch models from OpenRouter API and filter for 100% free models."""
        async with self._lock:
            url = "https://openrouter.ai/api/v1/models"
            headers = {"Accept": "application/json"}
            if settings.OPENROUTER_API_KEY:
                headers["Authorization"] = f"Bearer {settings.OPENROUTER_API_KEY}"

            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url, headers=headers)
                    if response.status_code != 200:
                        logger.warning(
                            f"OpenRouter models endpoint returned {response.status_code}. Retaining cached models."
                        )
                        return len(self._models)

                    data = response.json()
                    raw_models = data.get("data", [])

                    new_models: Dict[str, FreeModelInfo] = {}
                    for item in raw_models:
                        model_id = item.get("id", "")
                        pricing = item.get("pricing", {}) or {}
                        prompt_price = float(pricing.get("prompt", 0) or 0)
                        completion_price = float(pricing.get("completion", 0) or 0)

                        is_free = (
                            model_id.endswith(":free")
                            or (prompt_price == 0.0 and completion_price == 0.0)
                        )

                        if not is_free:
                            continue

                        # Architecture & Modality detection
                        arch = item.get("architecture", {}) or {}
                        modality = str(arch.get("modality", "")).lower()
                        input_modalities = item.get("input_modalities", []) or []
                        input_mods = [str(m).lower() for m in input_modalities]

                        has_vision = (
                            "image" in modality
                            or "multimodal" in modality
                            or "image" in input_mods
                            or "vision" in model_id.lower()
                        )
                        has_audio = "audio" in modality or "audio" in input_mods
                        has_video = "video" in modality or "video" in input_mods

                        context_length = int(item.get("context_length", 4096) or 4096)

                        # Function calling / tools
                        supported_params = item.get("supported_parameters", []) or []
                        has_tools = "tools" in supported_params or "functions" in supported_params

                        # Heuristic tags from id/name/description
                        name = item.get("name", model_id)
                        desc = item.get("description", "")
                        text_for_tags = f"{model_id} {name} {desc}".lower()

                        is_reasoning = (
                            "reasoning" in text_for_tags
                            or "r1" in model_id.lower()
                            or "thinking" in model_id.lower()
                            or "o1" in model_id.lower()
                        )
                        is_coder = (
                            "coder" in text_for_tags
                            or "code" in text_for_tags
                            or "deepseek" in text_for_tags
                        )

                        provider = model_id.split("/")[0] if "/" in model_id else "OpenRouter"

                        info = FreeModelInfo(
                            id=model_id,
                            name=name,
                            context_length=context_length,
                            has_vision=has_vision,
                            has_audio=has_audio,
                            has_video=has_video,
                            has_tools=has_tools,
                            is_reasoning=is_reasoning,
                            is_coder=is_coder,
                            provider=provider.capitalize(),
                            description=desc,
                            pricing=pricing,
                            last_seen=datetime.now(timezone.utc)
                        )
                        new_models[model_id] = info

                    if new_models:
                        self._models = new_models
                        self.last_refresh = datetime.now(timezone.utc)
                        logger.info(f"Refreshed OpenRouter free models: {len(new_models)} active free models discovered.")
                        return len(new_models)

            except Exception as e:
                logger.error(f"Failed to refresh models from OpenRouter: {e}. Keeping existing cache.")

            return len(self._models)

    async def start_periodic_refresh(self):
        """Background loop to periodically refresh model registry."""
        while True:
            try:
                await asyncio.sleep(settings.MODEL_REFRESH_INTERVAL_MINUTES * 60)
                await self.refresh_models()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in model registry background refresh: {e}")


# Singleton instance
registry = ModelRegistry()
