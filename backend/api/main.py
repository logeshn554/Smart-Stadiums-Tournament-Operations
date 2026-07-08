"""
FastAPI application entry point for StadiumOps AI.

Configures the application, loads environment variables, attaches CORS
middleware with security headers, and mounts the API router.

Security configuration:
  - CORS restricted to configured origins (localhost-only in dev)
  - Security headers added via middleware (X-Content-Type-Options,
    X-Frame-Options, Content-Security-Policy, Referrer-Policy)
  - Environment variables loaded from .env (never committed)
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.api.routes import router

# ── Configure structured logging ──────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Load environment variables ────────────────────────────────────────────
load_dotenv()

# ── Application factory ──────────────────────────────────────────────────

app = FastAPI(
    title="StadiumOps AI",
    description=(
        "Intelligent decision-support assistant for stadium control room "
        "staff during live sporting events. Provides ranked, explainable "
        "action recommendations based on gate statuses, incidents, weather, "
        "and event context."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS middleware ───────────────────────────────────────────────────────

_raw_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000,null",
)
allowed_origins = [
    origin.strip() for origin in _raw_origins.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Security headers middleware ───────────────────────────────────────
#
# Design note — Rate limiting
# The in-memory sliding-window rate limiter (see routes.py) is an intentional
# design choice for single-process deployments typical of stadium control rooms.
# For multi-instance horizontal scaling, swap in Redis-backed rate limiting
# (e.g. slowapi + redis) without any API contract changes.


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Add security headers to every HTTP response.

    Applies defense-in-depth headers to mitigate common web attack vectors
    including clickjacking, MIME-sniffing, content injection, and
    transport-layer downgrade attacks.

    Headers applied:
        - X-Content-Type-Options: nosniff
        - X-Frame-Options: DENY
        - X-XSS-Protection: 1; mode=block
        - Referrer-Policy: strict-origin-when-cross-origin
        - Strict-Transport-Security: max-age=31536000; includeSubDomains
        - Content-Security-Policy (see inline justification below)

    Args:
        request: Incoming HTTP request.
        call_next: Next middleware or route handler in the chain.

    Returns:
        HTTP response with security headers injected.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    # CSP justification: 'unsafe-inline' for style-src is required because the
    # frontend dynamically applies severity-based background colours via inline
    # styles on recommendation cards. A nonce-based approach would require
    # server-side HTML rendering. This is an accepted, documented trade-off
    # for a dashboard that only serves authenticated control room staff on a
    # trusted internal network. script-src remains strict 'self' only.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "connect-src 'self' ws: wss:"
    )
    return response


# ── Mount routes ──────────────────────────────────────────────────────────

app.include_router(router)

logger.info(
    "StadiumOps AI started. CORS origins: %s",
    allowed_origins,
)
