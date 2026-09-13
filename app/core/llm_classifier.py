import asyncio
import json
import logging
from typing import Any, Dict, Optional
import httpx
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("gateway.llm_classifier")


class LLMClassification(BaseModel):
    category: str  # coding, reasoning, multimodal, agent_tool, general_chat
    complexity: int = 1  # 1 to 5
    explanation: str = ""
    suggested_specialization: str = "general"


CLASSIFIER_PROMPT = """You are an ultra-fast AI query classifier for an API Gateway.
Classify the user request into exactly one JSON object with:
- "category": one of ["coding", "reasoning", "multimodal", "agent_tool", "general_chat"]
- "complexity": integer from 1 (trivial) to 5 (extremely complex multi-step task)
- "suggested_specialization": one of ["coder", "reasoner", "vision", "fast", "general"]
- "explanation": max 10 words summary

Output ONLY the raw JSON object, no markdown, no quotes around JSON."""


class LLMClassifier:
    FAST_FREE_CLASSIFIER_MODELS = [
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "mistralai/mistral-small-24b-instruct-2501:free"
    ]

    @classmethod
    async def classify(cls, payload: Dict[str, Any], timeout_seconds: float = 2.5) -> Optional[LLMClassification]:
        """Runs a fast structured classification using an available free model."""
        if not settings.OPENROUTER_API_KEY:
            return None

        # Extract last user message or last 2 messages for quick context
        messages = payload.get("messages", [])
        if not messages:
            return None

        recent_msgs = messages[-2:] if len(messages) >= 2 else messages
        sample_text = ""
        for m in recent_msgs:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):
                text_items = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = " ".join(text_items)
            sample_text += f"{role}: {str(content)[:300]}\n"

        if not sample_text.strip():
            return None

        classifier_request = {
            "model": cls.FAST_FREE_CLASSIFIER_MODELS[0],
            "messages": [
                {"role": "system", "content": CLASSIFIER_PROMPT},
                {"role": "user", "content": f"Request sample:\n{sample_text}"}
            ],
            "max_tokens": 100,
            "temperature": 0.0
        }

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/jmast321/api_gateway",
            "X-Title": "Hermes AI Router"
        }

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=classifier_request)
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        content_str = choices[0].get("message", {}).get("content", "").strip()
                        # Clean potential code fences
                        if content_str.startswith("```"):
                            content_str = content_str.split("\n", 1)[-1]
                        if content_str.endswith("```"):
                            content_str = content_str.rsplit("\n", 1)[0]

                        parsed = json.loads(content_str.strip())
                        return LLMClassification(
                            category=parsed.get("category", "general_chat"),
                            complexity=int(parsed.get("complexity", 1)),
                            explanation=parsed.get("explanation", ""),
                            suggested_specialization=parsed.get("suggested_specialization", "general")
                        )
        except asyncio.TimeoutError:
            logger.debug("LLM classification timed out; falling back to heuristic decision.")
        except Exception as e:
            logger.debug(f"LLM classifier exception: {e}")

        return None


llm_classifier = LLMClassifier()
