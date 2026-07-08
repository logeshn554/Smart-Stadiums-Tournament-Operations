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
  - Role-based access control (admin / viewer)
  - In-memory sliding-window rate limiting per IP (intentional design choice
    for single-process control room deployments; swap in Redis-backed rate
    limiting for horizontal scaling without API contract changes)
  - HTML tag sanitisation on incident descriptions
  - Severity-sorted response output
"""

import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

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

# ── In-memory rate limiter ────────────────────────────────────────────────
# Design note: This sliding-window rate limiter is intentionally in-memory.
# Stadium control rooms run a single API process per venue, so in-memory
# state is sufficient. For multi-instance horizontal scaling, replace with
# Redis-backed counters (e.g. slowapi + redis) — no API changes needed.

RATE_LIMIT_MAX: Final[int] = 10
RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
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


def _check_rate_limit(client_ip: str) -> None:
    """Enforce per-IP rate limiting using an in-memory sliding window.

    Allows at most RATE_LIMIT_MAX requests within RATE_LIMIT_WINDOW_SECONDS.
    Old timestamps outside the window are cleaned up on each call to prevent
    unbounded memory growth.

    Args:
        client_ip: The IP address of the requesting client.

    Raises:
        HTTPException: 429 if the rate limit is exceeded.
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    # Clean up stale timestamps to prevent memory leak
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
async def analyze_endpoint(payload: AnalyzeRequest) -> dict[str, Any]:
    """Run all five decision-engine rules and return ranked recommendations.

    Accepts a combined payload containing gate statuses, an incident report,
    weather context, event context, and a caller role.  The role field acts
    as a mock authentication gate: viewers cannot submit fire_smoke or
    evacuation-level incidents.

    Args:
        payload: Validated AnalyzeRequest body.

    Returns:
        A dict with a 'recommendations' key containing a severity-sorted list.

    Raises:
        HTTPException 403: If a viewer attempts to submit a Critical incident.
    """
    # ── Mock auth: viewers cannot submit Critical-level incident types ──
    if (
        payload.role == CallerRole.VIEWER
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
        payload.role.value,
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
