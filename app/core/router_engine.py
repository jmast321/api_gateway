import asyncio
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.config import RoutingMode, settings
from app.core.heuristic_analyzer import HeuristicAnalyzer, HeuristicProfile
from app.core.llm_classifier import LLMClassification, LLMClassifier
from app.core.model_registry import FreeModelInfo, registry

logger = logging.getLogger("gateway.router_engine")


class RoutingDecision(BaseModel):
    primary_model: str
    fallback_models: List[str] = Field(default_factory=list)
    routing_mode: str
    heuristic_profile: HeuristicProfile
    llm_classification: Optional[LLMClassification] = None
    rationale: str = ""
    estimated_tokens: int = 0


class RouterEngine:
    def __init__(self):
        self.active_mode: RoutingMode = settings.DEFAULT_ROUTING_MODE

    def set_mode(self, mode: RoutingMode):
        self.active_mode = mode
        logger.info(f"Routing mode updated to: {self.active_mode.value}")

    async def decide_route(
        self,
        payload: Dict[str, Any],
        requested_model: Optional[str] = None
    ) -> RoutingDecision:
        """Determines the primary free model and fallback cascade for the request."""
        # 1. Zero-latency heuristic analysis
        heuristic = HeuristicAnalyzer.analyze(payload)

        # If user explicitly requested a valid specific free model and it's not a generic alias ("auto", "free", etc.)
        all_models = registry.get_all()
        generic_aliases = ["auto", "openrouter/auto", "free", "hermes", "hermes-router", ""]
        if requested_model and requested_model not in generic_aliases:
            if registry.is_free_model(requested_model):
                # Put user-requested free model first, with ranked fallbacks
                other_fallbacks = [m.id for m in all_models if m.id != requested_model][:settings.FALLBACK_CANDIDATES_COUNT]
                return RoutingDecision(
                    primary_model=requested_model,
                    fallback_models=other_fallbacks,
                    routing_mode="EXPLICIT_FREE_OVERRIDE",
                    heuristic_profile=heuristic,
                    rationale=f"User explicitly requested verified free model: {requested_model}",
                    estimated_tokens=heuristic.estimated_tokens
                )

        llm_class: Optional[LLMClassification] = None

        # 2. Routing mode logic
        if self.active_mode == RoutingMode.HEURISTIC_ONLY:
            pass  # purely heuristic, zero network call

        elif self.active_mode == RoutingMode.SHADOW_TEST:
            # Launch LLM classifier asynchronously in background without waiting
            asyncio.create_task(self._run_shadow_classification(payload, heuristic))

        elif self.active_mode == RoutingMode.SYNERGY:
            # Run quick classification with short timeout
            llm_class = await LLMClassifier.classify(payload, timeout_seconds=2.0)

        # 3. Filter hard constraints
        candidate_models: List[FreeModelInfo] = []
        for m in all_models:
            # Check context length
            if heuristic.estimated_tokens > m.context_length:
                continue
            # Check vision
            if heuristic.requires_vision and not m.has_vision:
                continue
            # Check audio
            if heuristic.requires_audio and not m.has_audio:
                continue
            # Check video
            if heuristic.requires_video and not m.has_video:
                continue
            # Check tools
            if heuristic.requires_tools and not m.has_tools:
                continue

            candidate_models.append(m)

        # Fallback if hard constraints filtered everything out (relax tools first)
        if not candidate_models:
            candidate_models = [m for m in all_models if not heuristic.requires_vision or m.has_vision]
        if not candidate_models:
            candidate_models = all_models

        # 4. Score and Rank candidates
        scored_models = []
        for m in candidate_models:
            score = 100.0

            # Specialization weights
            if heuristic.is_coding:
                if m.is_coder:
                    score += 60.0
                if "coder" in m.id.lower():
                    score += 40.0

            if heuristic.is_reasoning:
                if m.is_reasoning:
                    score += 70.0
                if "r1" in m.id.lower() or "thinking" in m.id.lower():
                    score += 40.0

            if heuristic.requires_vision and m.has_vision:
                score += 50.0

            # LLM classification synergy adjustments
            if llm_class:
                if llm_class.category == "coding" and m.is_coder:
                    score += 40.0
                elif llm_class.category == "reasoning" and m.is_reasoning:
                    score += 50.0
                elif llm_class.category == "multimodal" and m.has_vision:
                    score += 40.0

            # Context window bonus
            if m.context_length >= 65536:
                score += 15.0
            if m.context_length >= 131072:
                score += 10.0

            scored_models.append((score, m))

        # Sort descending by score
        scored_models.sort(key=lambda x: x[0], reverse=True)

        primary = scored_models[0][1].id if scored_models else "google/gemini-2.0-flash-exp:free"
        fallbacks = [m[1].id for m in scored_models[1: 1 + settings.FALLBACK_CANDIDATES_COUNT]]

        rationale = f"Selected {primary} based on {self.active_mode.value} (Tags: {', '.join(heuristic.detected_tags) or 'general'})"
        if llm_class:
            rationale += f" | LLM Category: {llm_class.category} (Complexity: {llm_class.complexity}/5)"

        return RoutingDecision(
            primary_model=primary,
            fallback_models=fallbacks,
            routing_mode=self.active_mode.value,
            heuristic_profile=heuristic,
            llm_classification=llm_class,
            rationale=rationale,
            estimated_tokens=heuristic.estimated_tokens
        )

    async def _run_shadow_classification(self, payload: Dict[str, Any], heuristic: HeuristicProfile):
        """Background logger for Shadow Test mode."""
        try:
            shadow_class = await LLMClassifier.classify(payload, timeout_seconds=4.0)
            if shadow_class:
                logger.info(
                    f"[SHADOW_TEST] Heuristic: {heuristic.detected_tags} vs LLM: {shadow_class.category} "
                    f"(Complexity {shadow_class.complexity}/5, Explanation: {shadow_class.explanation})"
                )
        except Exception as e:
            logger.debug(f"Shadow classification error: {e}")


router_engine = RouterEngine()
