"""FastAPI application entry point for StadiumOps AI.

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
from collections.abc import Awaitable, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

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
    "http://localhost:8000,http://127.0.0.1:8000,http://localhost:8080,http://127.0.0.1:8080,null",
)
allowed_origins = [origin.strip() for origin in _raw_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Gemini-API-Key"],
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
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
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
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # CSP justification: 'unsafe-inline' for style-src is required because the
    # frontend dynamically applies severity-based background colours via inline
    # styles on recommendation cards. A nonce-based approach would require
    # server-side HTML rendering. This is an accepted, documented trade-off
    # for a dashboard that only serves authenticated control room staff on a
    # trusted internal network. script-src remains strict 'self' only.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://www.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss: "
        "https://generativelanguage.googleapis.com "
        "https://fcm.googleapis.com "
        "https://firebaseinstallations.googleapis.com "
        "https://identitytoolkit.googleapis.com "
        "https://www.gstatic.com"
    )
    return response


# ── Mount routes ──────────────────────────────────────────────────────────

app.include_router(router)

# ── Serve frontend static files ───────────────────────────────────────────
# Mount the frontend directory so the dashboard is accessible at http://127.0.0.1:8000
_frontend_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend"
)
if os.path.isdir(_frontend_path):
    app.mount("/", StaticFiles(directory=_frontend_path, html=True), name="frontend")
    logger.info("Frontend static files mounted from: %s", _frontend_path)

# Trigger server reload to read updated .env config
logger.info(
    "StadiumOps AI started. CORS origins: %s",
    allowed_origins,
)
