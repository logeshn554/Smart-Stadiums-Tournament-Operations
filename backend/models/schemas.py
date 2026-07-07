"""
Pydantic data models for StadiumOps AI.

Defines validated schemas for all inputs (gate status, incidents, weather,
event context) and the output Recommendation model used by the decision engine.
All models enforce strict type checking, range constraints, and input
sanitisation to prevent malformed or adversarial data from reaching
the decision engine.
"""

import logging
import re
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


class IncidentType(str, Enum):
    """Enumeration of recognised incident categories."""

    MEDICAL = "medical"
    SECURITY = "security"
    OVERCROWDING = "overcrowding"
    LOST_CHILD = "lost_child"
    FIRE_SMOKE = "fire_smoke"


class EventPhase(str, Enum):
    """Enumeration of match phases."""

    PRE_MATCH = "pre_match"
    HALFTIME = "halftime"
    POST_MATCH = "post_match"
    OVERTIME = "overtime"


class SeverityLevel(str, Enum):
    """Severity levels for recommendations, ordered from lowest to highest."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ConfidenceLevel(str, Enum):
    """Confidence qualifier attached to every recommendation."""

    CERTAIN = "Certain"
    LIKELY = "Likely"
    ADVISORY = "Advisory"


class CallerRole(str, Enum):
    """Roles for mock authentication on API endpoints."""

    ADMIN = "admin"
    VIEWER = "viewer"


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class GateStatus(BaseModel):
    """Real-time status of a single stadium entry/exit gate."""

    gate_id: str = Field(
        ..., min_length=1, max_length=50,
        description="Unique identifier for the gate",
    )
    capacity_percent: float = Field(
        ..., ge=0, le=100,
        description="Current capacity utilisation (0–100 %)",
    )
    entry_rate: int = Field(
        ..., ge=0,
        description="People entering per minute",
    )
    wait_time_seconds: int = Field(
        ..., ge=0,
        description="Estimated wait time in seconds",
    )


class IncidentReport(BaseModel):
    """A single incident reported by stadium staff."""

    incident_id: str = Field(
        ..., min_length=1, max_length=50,
        description="Unique incident identifier",
    )
    zone: str = Field(
        ..., min_length=1, max_length=50,
        description="Stadium zone where the incident occurred",
    )
    type: str = Field(
        ..., min_length=1, max_length=50,
        description="Incident category",
    )
    description: str = Field(
        ..., max_length=300,
        description="Free-text description (max 300 chars, HTML stripped)",
    )
    reporter_role: str = Field(
        ..., min_length=1, max_length=100,
        description="Role of the person reporting",
    )

    @field_validator("description", mode="before")
    @classmethod
    def strip_html_tags(cls, value: str) -> str:
        """Remove any HTML tags from the description before validation.

        Prevents stored XSS by stripping all angle-bracket markup from
        the user-supplied incident description.
        """
        if isinstance(value, str):
            sanitised = re.sub(r"<[^>]*>", "", value)
            if sanitised != value:
                logger.warning(
                    "HTML tags stripped from incident description input."
                )
            return sanitised
        return value

    @field_validator("type", mode="after")
    @classmethod
    def validate_incident_type(cls, value: str) -> str:
        """Log a warning for unknown incident types.

        Unknown types are still accepted — the decision engine will
        handle them as Low severity — but a log entry helps ops teams
        identify potential data-quality issues upstream.
        """
        known_types = {member.value for member in IncidentType}
        if value not in known_types:
            logger.warning(
                "Unknown incident type received: '%s'. "
                "Will be triaged as Low severity.",
                value,
            )
        return value


class WeatherContext(BaseModel):
    """Current weather conditions at the venue."""

    temperature_celsius: float = Field(
        ..., ge=-50, le=60,
        description="Ambient temperature in Celsius (-50 to 60)",
    )
    heat_index: float = Field(
        ..., ge=-50, le=80,
        description="Perceived temperature factoring humidity",
    )
    lightning_detected: bool = Field(
        ..., description="Whether lightning has been detected nearby",
    )
    lightning_radius_km: float = Field(
        ..., ge=0,
        description="Distance of closest detected lightning in km",
    )


class EventContext(BaseModel):
    """Snapshot of the current event / match state."""

    phase: EventPhase = Field(
        ..., description="Current match phase",
    )
    total_capacity: int = Field(
        ..., gt=0,
        description="Total venue seat capacity",
    )
    occupied_seats: int = Field(
        ..., ge=0,
        description="Currently occupied seats",
    )
    accessible_seats_available: int = Field(
        ..., ge=0,
        description="Remaining accessible seating slots",
    )
    concession_queue_avg_minutes: float = Field(
        ..., ge=0,
        description="Average concession queue wait in minutes",
    )

    @model_validator(mode="after")
    def validate_occupied_not_exceeding_capacity(self) -> "EventContext":
        """Ensure occupied seats do not exceed total venue capacity.

        This catches data-entry errors where an operator accidentally
        reports more attendees than the stadium can hold.
        """
        if self.occupied_seats > self.total_capacity:
            logger.warning(
                "Occupied seats (%d) exceed total capacity (%d). "
                "Capping to total capacity.",
                self.occupied_seats,
                self.total_capacity,
            )
            self.occupied_seats = self.total_capacity
        return self


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class Recommendation(BaseModel):
    """A single ranked, explainable action recommendation."""

    rule_id: str = Field(
        ..., min_length=1,
        description="Identifier of the rule that produced this",
    )
    severity: SeverityLevel = Field(
        ..., description="Urgency level",
    )
    action: str = Field(
        ..., min_length=1,
        description="Recommended action to take",
    )
    reason: str = Field(
        ..., min_length=1,
        description="Human-readable explanation",
    )
    affected_zone: str = Field(
        ..., min_length=1,
        description="Zone or gate affected",
    )
    confidence: ConfidenceLevel = Field(
        ..., description="Confidence qualifier",
    )


# ---------------------------------------------------------------------------
# Composite request / response schemas used by the API
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """Combined payload sent to the /api/analyze endpoint."""

    gates: list[GateStatus] = Field(
        ..., min_length=1,
        description="List of gate statuses (at least one required)",
    )
    incident: IncidentReport = Field(
        ..., description="Current incident report",
    )
    weather: WeatherContext = Field(
        ..., description="Current weather snapshot",
    )
    event_context: EventContext = Field(
        ..., description="Current event state",
    )
    role: CallerRole = Field(
        ..., description="Caller role — 'admin' or 'viewer'",
    )


class AnalyzeResponse(BaseModel):
    """Response from the /api/analyze endpoint."""

    recommendations: list[Recommendation] = Field(
        ..., description="Ranked list of recommendations (Critical first)",
    )


class HealthResponse(BaseModel):
    """Response from the /api/health endpoint."""

    status: str = Field(
        ..., description="Service status",
    )
    version: str = Field(
        ..., description="API version",
    )
