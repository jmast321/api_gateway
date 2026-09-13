"""Test suite for Hermes AI Gateway routing and heuristics."""

import asyncio
import sys
from app.config import RoutingMode
from app.core.heuristic_analyzer import heuristic_analyzer
from app.core.model_registry import registry
from app.core.router_engine import router_engine


def test_heuristic_analysis():
    print("--- 1. Testing Heuristic Analyzer ---")

    # Coding query
    code_payload = {
        "messages": [
            {"role": "user", "content": "def fibonacci(n):\n    if n <= 1: return n\n    return fibonacci(n-1) + fibonacci(n-2)"}
        ]
    }
    profile_code = heuristic_analyzer.analyze(code_payload)
    assert profile_code.is_coding, "Should detect coding from python function definition"
    assert "coding" in profile_code.detected_tags
    print("  [PASS] Coding intent detected successfully.")

    # Vision query
    vision_payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe what is in this image:"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/photo.png"}}
                ]
            }
        ]
    }
    profile_vision = heuristic_analyzer.analyze(vision_payload)
    assert profile_vision.requires_vision, "Should detect vision requirement from image_url"
    assert "vision" in profile_vision.detected_tags
    print("  [PASS] Multimodal vision requirement detected successfully.")

    # Reasoning query
    math_payload = {
        "messages": [
            {"role": "user", "content": "Prove that the sum of the first n odd integers is n^2 step by step"}
        ]
    }
    profile_math = heuristic_analyzer.analyze(math_payload)
    assert profile_math.is_reasoning, "Should detect reasoning requirement"
    assert "reasoning" in profile_math.detected_tags
    print("  [PASS] Mathematical reasoning detected successfully.")


async def test_routing_engine():
    print("\n--- 2. Testing Router Engine Decisions ---")
    router_engine.set_mode(RoutingMode.HEURISTIC_ONLY)

    # Test coding route selection
    code_query = {
        "messages": [{"role": "user", "content": "class DatabaseConnection:\n    def __init__(self): pass"}]
    }
    dec_code = await router_engine.decide_route(code_query)
    print(f"  Coding route decision: Primary -> {dec_code.primary_model} (Fallbacks: {dec_code.fallback_models})")
    assert dec_code.primary_model, "Must select a valid primary model"

    # Test vision route selection
    vision_query = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Inspect this screenshot"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA"}}
            ]
        }]
    }
    dec_vision = await router_engine.decide_route(vision_query)
    print(f"  Vision route decision: Primary -> {dec_vision.primary_model} (Fallbacks: {dec_vision.fallback_models})")
    selected_model_info = registry.get_by_id(dec_vision.primary_model)
    assert selected_model_info.has_vision, "Vision task MUST be assigned to a model with vision support"
    print("  [PASS] Vision constraint correctly enforced on model selection.")


async def main():
    try:
        test_heuristic_analysis()
        await test_routing_engine()
        print("\nAll gateway core tests completed successfully! [OK]")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
