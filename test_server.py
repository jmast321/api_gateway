"""Integration test for FastAPI endpoints using in-process ASGI Transport."""

import asyncio
import sys
import httpx
from app.main import app


async def test_all_endpoints():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("--- 1. Testing /health ---")
        res_health = await client.get("/health")
        assert res_health.status_code == 200
        health_data = res_health.json()
        assert health_data["status"] == "healthy"
        print(f"  [PASS] /health: {health_data}")

        print("\n--- 2. Testing /v1/models (OpenAI Standard Format) ---")
        res_models = await client.get("/v1/models")
        assert res_models.status_code == 200
        models_data = res_models.json()
        assert "data" in models_data
        model_ids = [m["id"] for m in models_data["data"]]
        assert "openrouter/auto" in model_ids
        print(f"  [PASS] /v1/models returned {len(model_ids)} models. Sample IDs: {model_ids[:3]}")

        print("\n--- 3. Testing /api/telemetry/stats ---")
        res_stats = await client.get("/api/telemetry/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        print(f"  [PASS] /api/telemetry/stats: {stats}")

        print("\n--- 4. Testing /api/test/classify (Playground endpoint) ---")
        res_classify = await client.post("/api/test/classify", json={
            "prompt": "Write a python function to compute factorial recursively",
            "has_image": False,
            "has_tools": False
        })
        assert res_classify.status_code == 200
        classify_data = res_classify.json()
        dec = classify_data["decision"]
        print(f"  [PASS] /api/test/classify: Primary Model chosen -> {dec['primary_model']}")
        print(f"  [PASS] Decision rationale: {dec['rationale']}")

        print("\n--- 5. Testing Dashboard HTML render ---")
        res_html = await client.get("/")
        assert res_html.status_code == 200
        assert "Hermes AI Gateway" in res_html.text
        print("  [PASS] Dashboard HTML loaded successfully.")

    print("\nAll ASGI integration tests PASSED! [OK]")


if __name__ == "__main__":
    asyncio.run(test_all_endpoints())
