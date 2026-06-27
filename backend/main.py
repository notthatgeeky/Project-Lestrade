"""
Sherlock Backend — FastAPI Application Entry Point
"""
import sys
import os

# Ensure backend directory is on the path for imports
sys.path.insert(0, os.path.dirname(__file__))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import init_db
from engine.session_manager import SessionManager
from routers import interviews, websocket
from config import CORS_ORIGINS
import logging

# ─── Logging ────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sherlock")

# ─── Session Manager (singleton) ────────────────────────────────────

session_manager = SessionManager()


# ─── Application Lifespan ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and session manager on startup."""
    logger.info("🔍 Sherlock backend starting...")
    await init_db()
    logger.info("✅ Database initialized")

    # Inject session manager into WebSocket router
    websocket.set_session_manager(session_manager)
    logger.info("✅ Session manager ready")

    logger.info("🚀 Sherlock backend is running")
    yield
    logger.info("👋 Sherlock backend shutting down")


# ─── FastAPI App ────────────────────────────────────────────────────

app = FastAPI(
    title="Sherlock",
    description="Real-time interview candidate identification and fraud detection",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permissive for dev — lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(interviews.router)
app.include_router(websocket.router)

# Serve dashboard static files if the directory exists
dashboard_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


from fastapi.responses import RedirectResponse

@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/dashboard/")


# ─── Health Check ───────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "sherlock",
        "version": "0.1.0",
        "active_sessions": len(session_manager.sessions),
    }


# ─── Run directly ──────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

# docs

# docs
