"""
FastAPI application entry point for StadiumOps AI.

Configures the application, loads environment variables, attaches CORS
middleware, and mounts the API router.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router

# ── Load environment variables ────────────────────────────────────────────
load_dotenv()

# ── Application factory ──────────────────────────────────────────────────

app = FastAPI(
    title="StadiumOps AI",
    description=(
        "Intelligent decision-support assistant for stadium control room "
        "staff during live sporting events."
    ),
    version="1.0.0",
)

# ── CORS middleware ───────────────────────────────────────────────────────

_raw_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)
allowed_origins = [origin.strip() for origin in _raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routes ──────────────────────────────────────────────────────────

app.include_router(router)
