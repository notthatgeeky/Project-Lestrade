"""
Sherlock Backend — Configuration
"""
import os
from pathlib import Path


# Base paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DB_PATH = os.getenv("SHERLOCK_DB_PATH", str(BASE_DIR / "sherlock.db"))

# Server
HOST = os.getenv("SHERLOCK_HOST", "0.0.0.0")
PORT = int(os.getenv("SHERLOCK_PORT", "8000"))

# CORS origins allowed
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
    "chrome-extension://*",
]

# Engine tuning
ENGINE_TICK_INTERVAL_S = 1.0  # Bayesian engine recalculates every N seconds
CONFIDENCE_BANDS = {
    "UNCERTAIN": (0.0, 0.40),
    "TENTATIVE": (0.40, 0.65),
    "PROBABLE": (0.65, 0.85),
    "HIGH": (0.85, 1.01),
}
SCORE_CHANGE_THRESHOLD = 0.01  # Minimum delta to emit an update
EXPLANATION_THRESHOLD = 0.05   # Minimum delta to generate an explanation

# Data retention
RAW_EVENT_TTL_DAYS = 7
