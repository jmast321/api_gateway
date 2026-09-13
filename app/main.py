import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.openai_routes import router as openai_router
from app.api.telemetry_routes import router as telemetry_router
from app.config import settings
from app.core.model_registry import registry

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gateway.main")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting Hermes AI Gateway (OpenRouter Free Router)...")
    # Discover initial models
    try:
        await registry.refresh_models()
    except Exception as e:
        logger.warning(f"Initial model discovery failed: {e}. Fallback cache active.")

    # Start background refresh loop
    refresh_task = asyncio.create_task(registry.start_periodic_refresh())
    yield

    logger.info("Shutting down Hermes AI Gateway...")
    refresh_task.cancel()
    try:
        await refresh_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Hermes AI Gateway",
    description="Intelligent Free Tier Routing Proxy for AI Agents",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware (allow agents, web clients, local tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files & Web templates
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# Routers
app.include_router(openai_router)
app.include_router(telemetry_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the modern interactive visual dashboard."""
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestrators and agents."""
    return {
        "status": "healthy",
        "gateway": "Hermes AI Router",
        "active_mode": settings.DEFAULT_ROUTING_MODE.value,
        "free_models_cached": len(registry.get_all())
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.GATEWAY_HOST,
        port=settings.GATEWAY_PORT,
        reload=settings.DEBUG
    )
