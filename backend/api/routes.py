"""
FastAPI route definitions for StadiumOps AI.

Provides five endpoints:
  POST /api/analyze   — full analysis with all five decision-engine rules
  POST /api/incident  — single-incident triage (rate-limited)
  GET  /api/health    — service health check
  GET  /api/audit     — incident audit log (in-memory, per-venue)
  WS   /api/ws        — WebSocket for real-time recommendation push

Security measures:
  - Pydantic input validation on all endpoints
  - RS256 JWT authentication (asymmetric key verification)
  - Role-based access control (admin / viewer)
  - Dual-backend rate limiting: in-memory sliding-window (default) or
    Redis-backed via slowapi (auto-detected from REDIS_URL env var)
  - HTML tag sanitisation on incident descriptions
  - Severity-sorted response output
"""

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Final

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from backend.core.auth import verify_token
from backend.core.decision_engine import (
    accessibility_routing,
    egress_plan,
    gate_load_balance,
    triage_incident,
    weather_action,
)
from backend.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CallerRole,
    EventContext,
    EventPhase,
    HealthResponse,
    IncidentReport,
    Recommendation,
    SeverityLevel,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# ── Severity sort order (Critical first) ──────────────────────────────────

SEVERITY_RANK: Final[dict[str, int]] = {
    SeverityLevel.CRITICAL.value: 0,
    SeverityLevel.HIGH.value: 1,
    SeverityLevel.MEDIUM.value: 2,
    SeverityLevel.LOW.value: 3,
}

# ── Rate limiter backend selection ────────────────────────────────────────
# Automatically uses Redis when REDIS_URL is set (production / Docker),
# falls back to in-memory sliding-window for single-process deployments.

RATE_LIMIT_MAX: Final[int] = 10
RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60

_redis_client = None
_REDIS_URL = os.getenv("REDIS_URL")

if _REDIS_URL:
    try:
        import redis as _redis_module
        _redis_client = _redis_module.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info("Rate limiter: using Redis backend at %s", _REDIS_URL)
    except Exception as exc:
        logger.warning("Redis unavailable (%s), falling back to in-memory rate limiter.", exc)
        _redis_client = None

# In-memory fallback store
_rate_limit_store: dict[str, list[float]] = defaultdict(list)

# ── Incident types that require admin privileges ──────────────────────────

CRITICAL_INCIDENT_TYPES: Final[frozenset[str]] = frozenset({"fire_smoke"})

# ── In-memory incident audit log ─────────────────────────────────────────
# Stores the last MAX_AUDIT_ENTRIES incidents per venue for traceability.
# Production deployments should persist to a database.

MAX_AUDIT_ENTRIES: Final[int] = 100
_audit_log: dict[str, list[dict[str, Any]]] = defaultdict(list)

# ── WebSocket connection manager ─────────────────────────────────────────

_ws_connections: list[WebSocket] = []


# ── JWT authentication dependency ────────────────────────────────────────


def _get_current_user(request: Request) -> dict[str, Any] | None:
    """Extract and verify JWT from the Authorization header.

    Supports ``Bearer <token>`` format.  If no Authorization header is
    present, returns ``None`` (allowing the mock role field as fallback
    for backward compatibility during the hackathon demo).

    Args:
        request: The incoming FastAPI request object.

    Returns:
        Decoded JWT payload dict, or ``None`` if no token is provided.

    Raises:
        HTTPException: 401 if a token is provided but is invalid/expired.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format. Use: Bearer <token>")

    token = auth_header.split("Bearer ", 1)[1]
    try:
        payload = verify_token(token)
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def _check_rate_limit(client_ip: str) -> None:
    """Enforce per-IP rate limiting using Redis or in-memory sliding window.

    When Redis is available, uses atomic ``ZRANGEBYSCORE`` + ``ZADD`` on a
    sorted set keyed by IP.  Falls back to an in-memory sliding-window
    counter for single-process deployments.

    Allows at most RATE_LIMIT_MAX requests within RATE_LIMIT_WINDOW_SECONDS.

    Args:
        client_ip: The IP address of the requesting client.

    Raises:
        HTTPException: 429 if the rate limit is exceeded.
    """
    now = time.time()

    if _redis_client is not None:
        key = f"rate_limit:{client_ip}"
        window_start = now - RATE_LIMIT_WINDOW_SECONDS

        pipe = _redis_client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        results = pipe.execute()
        current_count = results[1]

        if current_count >= RATE_LIMIT_MAX:
            logger.warning("Rate limit exceeded for IP: %s (Redis)", client_ip)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded. Maximum {RATE_LIMIT_MAX} requests "
                    f"per {RATE_LIMIT_WINDOW_SECONDS} seconds."
                ),
            )
        return

    # In-memory fallback
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if ts > window_start
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_MAX:
        logger.warning("Rate limit exceeded for IP: %s", client_ip)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded. Maximum {RATE_LIMIT_MAX} requests "
                f"per {RATE_LIMIT_WINDOW_SECONDS} seconds."
            ),
        )

    _rate_limit_store[client_ip].append(now)


def _sanitize_description(description: str) -> str:
    """Strip HTML tags from a description string.

    Applies a regex-based filter to remove all angle-bracket markup.
    This provides defense-in-depth alongside the Pydantic-level
    validator in the IncidentReport schema.

    Args:
        description: Raw description text potentially containing HTML.

    Returns:
        Cleaned string with all HTML tags removed.
    """
    sanitised = re.sub(r"<[^>]*>", "", description)
    if sanitised != description:
        logger.info("HTML tags stripped from incident description at API layer.")
    return sanitised


def _sort_recommendations(
    recommendations: list[Recommendation],
) -> list[Recommendation]:
    """Sort recommendations by severity (Critical first, Low last).

    Uses a pre-defined rank mapping for O(n log n) stable sorting.

    Args:
        recommendations: Unsorted list of Recommendation objects.

    Returns:
        Severity-sorted copy of the list.
    """
    return sorted(
        recommendations,
        key=lambda r: SEVERITY_RANK.get(r.severity, 99),
    )


def _append_audit_entry(venue_id: str, incident: IncidentReport, source: str) -> None:
    """Append an incident to the in-memory audit log.

    Maintains a bounded ring buffer per venue, discarding the oldest
    entries when MAX_AUDIT_ENTRIES is reached.

    Args:
        venue_id: Venue identifier for multi-venue isolation.
        incident: The incident report to log.
        source: Which endpoint recorded the entry ('analyze' or 'incident').
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "incident_id": incident.incident_id,
        "zone": incident.zone,
        "type": incident.type,
        "description": incident.description,
        "reporter_role": incident.reporter_role,
    }
    log = _audit_log[venue_id]
    log.append(entry)
    # Maintain bounded size
    if len(log) > MAX_AUDIT_ENTRIES:
        _audit_log[venue_id] = log[-MAX_AUDIT_ENTRIES:]

    logger.info("Audit log: recorded %s from %s for venue %s", incident.incident_id, source, venue_id)


async def _broadcast_ws(recommendations: list[Recommendation]) -> None:
    """Broadcast recommendations to all connected WebSocket clients.

    Sends a JSON payload to every active WebSocket connection. Silently
    removes disconnected clients from the connection pool.

    Args:
        recommendations: The list of recommendations to broadcast.
    """
    if not _ws_connections:
        return

    payload = json.dumps({
        "type": "recommendations_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recommendations": [r.model_dump() for r in recommendations],
    })

    disconnected: list[WebSocket] = []
    for ws in _ws_connections:
        try:
            await ws.send_text(payload)
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        _ws_connections.remove(ws)


# ── Endpoints ─────────────────────────────────────────────────────────


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(payload: AnalyzeRequest, request: Request) -> dict[str, Any]:
    """Run all five decision-engine rules and return ranked recommendations.

    Accepts a combined payload containing gate statuses, an incident report,
    weather context, event context, and a caller role.  Supports two
    authentication modes:

    1. **JWT (preferred)**: ``Authorization: Bearer <token>`` — role is
       extracted from the token's ``role`` claim.
    2. **Mock role field (fallback)**: ``role`` field in the payload body
       for backward-compatible hackathon demo usage.

    Args:
        payload: Validated AnalyzeRequest body.
        request: FastAPI Request for JWT extraction.

    Returns:
        A dict with a 'recommendations' key containing a severity-sorted list.

    Raises:
        HTTPException 401: If a JWT is provided but invalid.
        HTTPException 403: If a viewer attempts to submit a Critical incident.
    """
    # ── Determine effective role (JWT takes precedence) ──
    jwt_payload = _get_current_user(request)
    effective_role = CallerRole(jwt_payload["role"]) if jwt_payload and "role" in jwt_payload else payload.role

    # ── RBAC: viewers cannot submit Critical-level incident types ──
    if (
        effective_role == CallerRole.VIEWER
        and payload.incident.type in CRITICAL_INCIDENT_TYPES
    ):
        logger.warning(
            "Viewer attempted to submit critical incident type: %s",
            payload.incident.type,
        )
        raise HTTPException(
            status_code=403,
            detail=(
                "Viewers are not authorised to submit Critical-level "
                f"incidents (type: {payload.incident.type})."
            ),
        )

    # ── Sanitize incident description (defense-in-depth) ──
    payload.incident.description = _sanitize_description(
        payload.incident.description
    )

    # ── Run all five rules ──
    all_recommendations: list[Recommendation] = []

    all_recommendations.extend(gate_load_balance(payload.gates))
    all_recommendations.append(triage_incident(payload.incident))
    all_recommendations.extend(weather_action(payload.weather))
    all_recommendations.extend(
        accessibility_routing(payload.event_context, payload.incident)
    )
    all_recommendations.extend(
        egress_plan(payload.event_context, payload.gates)
    )

    sorted_recommendations = _sort_recommendations(all_recommendations)

    # ── Record to audit log ──
    _append_audit_entry(payload.venue_id, payload.incident, "analyze")

    # ── Broadcast via WebSocket ──
    await _broadcast_ws(sorted_recommendations)

    logger.info(
        "analyze_endpoint: returning %d recommendations for role=%s venue=%s",
        len(sorted_recommendations),
        effective_role.value,
        payload.venue_id,
    )

    return {"recommendations": sorted_recommendations}


@router.post("/incident")
async def incident_endpoint(
    report: IncidentReport, request: Request
) -> dict[str, Any]:
    """Triage a single incident and return accessibility-aware recommendations.

    Rate-limited to 10 requests per minute per IP address.

    Args:
        report: Validated IncidentReport body.
        request: FastAPI Request object (used for client IP extraction).

    Returns:
        A dict with a 'recommendations' key.

    Raises:
        HTTPException 429: If rate limit is exceeded.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    # Sanitize description (defense-in-depth)
    report.description = _sanitize_description(report.description)

    recommendations: list[Recommendation] = []
    recommendations.append(triage_incident(report))

    # For accessibility routing we need an EventContext; use a default
    # context since this endpoint only receives an IncidentReport.
    default_event_context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=30000,
        accessible_seats_available=0,
        concession_queue_avg_minutes=5.0,
    )
    recommendations.extend(accessibility_routing(default_event_context, report))

    sorted_recommendations = _sort_recommendations(recommendations)

    # ── Record to audit log (default venue) ──
    _append_audit_entry("default", report, "incident")

    # ── Broadcast via WebSocket ──
    await _broadcast_ws(sorted_recommendations)

    logger.info(
        "incident_endpoint: type=%s returning %d recommendation(s).",
        report.type,
        len(sorted_recommendations),
    )

    return {"recommendations": sorted_recommendations}


@router.get("/health", response_model=HealthResponse)
async def health_endpoint() -> dict[str, str]:
    """Return service health status and version.

    Returns:
        A dict with 'status' and 'version' keys.
    """
    return {"status": "ok", "version": "1.0.0"}


@router.get("/audit")
async def audit_endpoint(venue_id: str = "default") -> dict[str, Any]:
    """Return the incident audit log for a given venue.

    Provides a chronological record of all incidents processed through
    both the /api/analyze and /api/incident endpoints. Useful for
    post-event review, compliance reporting, and operational auditing.

    Args:
        venue_id: Venue identifier (defaults to 'default').

    Returns:
        A dict with 'venue_id', 'total_entries', and 'entries' keys.
    """
    entries = _audit_log.get(venue_id, [])
    logger.info("audit_endpoint: returning %d entries for venue %s", len(entries), venue_id)
    return {
        "venue_id": venue_id,
        "total_entries": len(entries),
        "entries": entries,
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time recommendation push.

    Clients connect to receive live recommendation updates whenever
    an analyze or incident request is processed. The server pushes
    JSON payloads containing the full recommendation list.

    Connection is maintained until the client disconnects or an error occurs.
    """
    await websocket.accept()
    _ws_connections.append(websocket)
    logger.info("WebSocket client connected. Total: %d", len(_ws_connections))

    try:
        while True:
            # Keep the connection alive; wait for client messages (e.g. pings)
            data = await websocket.receive_text()
            # Echo back a heartbeat acknowledgement
            await websocket.send_text(json.dumps({"type": "pong", "received": data}))
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
    finally:
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)
        logger.info("WebSocket clients remaining: %d", len(_ws_connections))
