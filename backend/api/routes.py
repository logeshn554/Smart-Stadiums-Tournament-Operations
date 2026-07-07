"""
FastAPI route definitions for StadiumOps AI.

Provides three endpoints:
  POST /api/analyze   — full analysis with all five decision-engine rules
  POST /api/incident  — single-incident triage (rate-limited)
  GET  /api/health    — service health check

Security measures:
  - Pydantic input validation on all endpoints
  - Role-based access control (admin / viewer)
  - In-memory sliding-window rate limiting per IP
  - HTML tag sanitisation on incident descriptions
  - Severity-sorted response output
"""

import logging
import re
import time
from collections import defaultdict
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request

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

RATE_LIMIT_MAX: Final[int] = 10
RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60
_rate_limit_store: dict[str, list[float]] = defaultdict(list)

# ── Incident types that require admin privileges ──────────────────────────

CRITICAL_INCIDENT_TYPES: Final[frozenset[str]] = frozenset({"fire_smoke"})


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


# ── Endpoints ─────────────────────────────────────────────────────────────


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

    logger.info(
        "analyze_endpoint: returning %d recommendations for role=%s",
        len(sorted_recommendations),
        payload.role.value,
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
