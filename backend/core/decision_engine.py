"""
StadiumOps AI — Decision Engine.

Pure, stateless, rule-based functions that accept typed domain objects and
return ranked Recommendation lists.  This module has zero knowledge of HTTP,
FastAPI, or any web framework and can be imported and tested in isolation.

Design Rationale
----------------
A rule-based engine was chosen over ML for several critical reasons:
  1. **Auditability** — every output traces to a named rule and stated reason.
  2. **Predictability** — identical inputs always produce identical outputs.
  3. **Zero cold-start** — no training data, model drift, or GPU needed.
  4. **Regulatory compliance** — stadium safety requires justifiable decisions.
"""

import logging
from typing import Final

from backend.models.schemas import (
    ConfidenceLevel,
    EventContext,
    EventPhase,
    GateStatus,
    IncidentReport,
    Recommendation,
    SeverityLevel,
    WeatherContext,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

GATE_OVERLOAD_THRESHOLD: Final[float] = 80.0
GATE_UNDERLOAD_THRESHOLD: Final[float] = 40.0
LIGHTNING_CRITICAL_RADIUS_KM: Final[float] = 15.0
HEAT_INDEX_DANGER_THRESHOLD: Final[float] = 40.0
HIGH_OCCUPANCY_RATIO: Final[float] = 0.9
MODERATE_OCCUPANCY_RATIO: Final[float] = 0.7


# ── RULE 1 — Gate Load Balancing ─────────────────────────────────────────


def gate_load_balance(gates: list[GateStatus]) -> list[Recommendation]:
    """Detect gate-capacity imbalances and recommend crowd redirection.

    Identifies gates above 80 % capacity and gates below 40 % capacity.
    When both exist simultaneously a High-severity recommendation is
    produced for every overloaded→underloaded pair, including the
    estimated wait-time reduction.

    Args:
        gates: Current status snapshots of all stadium gates.

    Returns:
        A list of Recommendation objects (empty when no imbalance is found).
    """
    if not gates:
        logger.debug("gate_load_balance: no gates provided, returning empty.")
        return []

    overloaded_gates = [
        g for g in gates if g.capacity_percent > GATE_OVERLOAD_THRESHOLD
    ]
    underloaded_gates = [
        g for g in gates if g.capacity_percent < GATE_UNDERLOAD_THRESHOLD
    ]

    if not overloaded_gates or not underloaded_gates:
        return []

    recommendations: list[Recommendation] = []

    for over_gate in overloaded_gates:
        for under_gate in underloaded_gates:
            estimated_wait_reduction = (
                over_gate.wait_time_seconds - under_gate.wait_time_seconds
            ) // 2
            recommendations.append(
                Recommendation(
                    rule_id="gate_load_balance",
                    severity=SeverityLevel.HIGH,
                    action=(
                        f"Redirect entry flow from gate {over_gate.gate_id} "
                        f"(at {over_gate.capacity_percent:.0f}% capacity) to "
                        f"gate {under_gate.gate_id} "
                        f"(at {under_gate.capacity_percent:.0f}% capacity)."
                    ),
                    reason=(
                        f"Gate {over_gate.gate_id} is overloaded at "
                        f"{over_gate.capacity_percent:.0f}% while gate "
                        f"{under_gate.gate_id} is underutilised at "
                        f"{under_gate.capacity_percent:.0f}%. Estimated wait "
                        f"reduction: {estimated_wait_reduction}s."
                    ),
                    affected_zone=over_gate.gate_id,
                    confidence=ConfidenceLevel.LIKELY,
                )
            )

    logger.info(
        "gate_load_balance: generated %d recommendation(s).",
        len(recommendations),
    )
    return recommendations


# ── RULE 2 — Incident Triage ─────────────────────────────────────────────


def triage_incident(report: IncidentReport) -> Recommendation:
    """Classify an incident and produce the appropriate response recommendation.

    Severity mapping:
        fire_smoke   → Critical
        overcrowding → High
        medical      → High
        security     → Medium
        lost_child   → Medium
        <unknown>    → Low

    Args:
        report: The incoming incident report.

    Returns:
        A single Recommendation object.
    """
    triage_map: dict[str, tuple[SeverityLevel, str, ConfidenceLevel]] = {
        "fire_smoke": (
            SeverityLevel.CRITICAL,
            "Initiate immediate evacuation protocol. Notify fire team and security.",
            ConfidenceLevel.CERTAIN,
        ),
        "overcrowding": (
            SeverityLevel.HIGH,
            "Dispatch crowd control team. Close nearest entry gates to prevent further inflow.",
            ConfidenceLevel.CERTAIN,
        ),
        "medical": (
            SeverityLevel.HIGH,
            "Dispatch medical team to the zone. Keep nearby paths clear for stretcher access.",
            ConfidenceLevel.CERTAIN,
        ),
        "security": (
            SeverityLevel.MEDIUM,
            "Alert security lead for the affected zone.",
            ConfidenceLevel.LIKELY,
        ),
        "lost_child": (
            SeverityLevel.MEDIUM,
            "Alert security team and broadcast a description on the PA system.",
            ConfidenceLevel.LIKELY,
        ),
    }

    severity, action, confidence = triage_map.get(
        report.type,
        (
            SeverityLevel.LOW,
            f"Unknown incident type '{report.type}'. Log for manual review.",
            ConfidenceLevel.ADVISORY,
        ),
    )

    logger.info(
        "triage_incident: type=%s severity=%s zone=%s",
        report.type,
        severity.value,
        report.zone,
    )

    return Recommendation(
        rule_id="triage_incident",
        severity=severity,
        action=action,
        reason=(
            f"Incident reported by {report.reporter_role} in zone {report.zone}. "
            f"Type: {report.type}. Description: {report.description}"
        ),
        affected_zone=report.zone,
        confidence=confidence,
    )


# ── RULE 3 — Weather Action ──────────────────────────────────────────────


def weather_action(weather: WeatherContext) -> list[Recommendation]:
    """Evaluate current weather conditions and produce safety recommendations.

    Triggers:
        - Lightning ≤ 15 km  → Critical (shelter-in-place)
        - Lightning > 15 km  → High (weather warning)
        - Heat index ≥ 40 °C → High (hydration + medical alert)

    Multiple recommendations can fire simultaneously.

    Args:
        weather: Current weather context snapshot.

    Returns:
        A list of triggered Recommendation objects (may be empty).
    """
    recommendations: list[Recommendation] = []

    if weather.lightning_detected and weather.lightning_radius_km <= LIGHTNING_CRITICAL_RADIUS_KM:
        recommendations.append(
            Recommendation(
                rule_id="weather_action",
                severity=SeverityLevel.CRITICAL,
                action=(
                    "Suspend all outdoor activity immediately. "
                    "Initiate shelter-in-place protocol."
                ),
                reason=(
                    f"Lightning detected within {weather.lightning_radius_km:.1f} km "
                    f"of the venue. Immediate shelter required."
                ),
                affected_zone="ALL",
                confidence=ConfidenceLevel.CERTAIN,
            )
        )
    elif weather.lightning_detected and weather.lightning_radius_km > LIGHTNING_CRITICAL_RADIUS_KM:
        recommendations.append(
            Recommendation(
                rule_id="weather_action",
                severity=SeverityLevel.HIGH,
                action=(
                    "Issue public weather warning via PA and displays. "
                    "Monitor lightning position every 5 minutes."
                ),
                reason=(
                    f"Lightning detected at {weather.lightning_radius_km:.1f} km. "
                    f"Not yet at critical range but requires active monitoring."
                ),
                affected_zone="ALL",
                confidence=ConfidenceLevel.LIKELY,
            )
        )

    if weather.heat_index >= HEAT_INDEX_DANGER_THRESHOLD:
        recommendations.append(
            Recommendation(
                rule_id="weather_action",
                severity=SeverityLevel.HIGH,
                action=(
                    "Activate hydration stations near high-occupancy sections. "
                    "Alert medical team to standby for heat-related incidents."
                ),
                reason=(
                    f"Heat index is {weather.heat_index:.1f} °C, exceeding the "
                    f"40 °C safety threshold. Risk of heat exhaustion and heatstroke."
                ),
                affected_zone="ALL",
                confidence=ConfidenceLevel.CERTAIN,
            )
        )

    if recommendations:
        logger.info(
            "weather_action: %d recommendation(s) triggered.", len(recommendations),
        )
    return recommendations


# ── RULE 4 — Accessibility Routing ───────────────────────────────────────


def accessibility_routing(
    context: EventContext, incident: IncidentReport
) -> list[Recommendation]:
    """Ensure accessible-seating zones receive priority attention during incidents.

    Triggers:
        - fire_smoke / overcrowding with available accessible seats
          → Critical: dispatch accessibility support staff first.
        - Any incident when accessible seats are at zero capacity
          → High: flag for monitoring.

    Args:
        context: Current event state including accessible seat counts.
        incident: The current incident report.

    Returns:
        A list of triggered Recommendation objects (may be empty).
    """
    recommendations: list[Recommendation] = []

    if incident.type in ("fire_smoke", "overcrowding") and context.accessible_seats_available > 0:
        recommendations.append(
            Recommendation(
                rule_id="accessibility_routing",
                severity=SeverityLevel.CRITICAL,
                action=(
                    "Dispatch accessibility support staff to accessible seating "
                    "zones first. Prioritise evacuation assistance for mobility-"
                    "impaired attendees."
                ),
                reason=(
                    f"Incident type '{incident.type}' in zone {incident.zone} "
                    f"requires priority accessible-seating response. "
                    f"{context.accessible_seats_available} accessible seats "
                    f"currently occupied and require attention."
                ),
                affected_zone=incident.zone,
                confidence=ConfidenceLevel.CERTAIN,
            )
        )

    if context.accessible_seats_available == 0:
        recommendations.append(
            Recommendation(
                rule_id="accessibility_routing",
                severity=SeverityLevel.HIGH,
                action=(
                    "Accessible seating zones are at full capacity. "
                    "Request on-ground monitoring and standby support."
                ),
                reason=(
                    f"All accessible seats are occupied (0 remaining). "
                    f"Any incident may disproportionately impact mobility-"
                    f"impaired attendees. Current incident: {incident.type} "
                    f"in zone {incident.zone}."
                ),
                affected_zone="Accessible Zones",
                confidence=ConfidenceLevel.LIKELY,
            )
        )

    if recommendations:
        logger.info(
            "accessibility_routing: %d recommendation(s) triggered.",
            len(recommendations),
        )
    return recommendations


# ── RULE 5 — Egress Plan ─────────────────────────────────────────────────


def egress_plan(
    context: EventContext, gates: list[GateStatus]
) -> list[Recommendation]:
    """Generate post-match or overtime egress recommendations.

    Only activates during post_match or overtime phases.  Recommends
    staggered exit waves based on occupancy ratio and identifies the
    two least-congested exit gates.

    Args:
        context: Current event state (phase, occupancy).
        gates: Current status of all stadium gates.

    Returns:
        A list of Recommendation objects (empty if phase is not applicable).
    """
    if context.phase not in (EventPhase.POST_MATCH, EventPhase.OVERTIME):
        return []

    if context.total_capacity == 0:
        return []

    occupancy_ratio = context.occupied_seats / context.total_capacity

    sorted_gates = sorted(gates, key=lambda g: g.capacity_percent)
    top_two_gates = sorted_gates[:2] if len(sorted_gates) >= 2 else sorted_gates
    gate_list_text = ", ".join(
        f"{g.gate_id} ({g.capacity_percent:.0f}%)" for g in top_two_gates
    )

    recommendations: list[Recommendation] = []

    if occupancy_ratio >= HIGH_OCCUPANCY_RATIO:
        recommendations.append(
            Recommendation(
                rule_id="egress_plan",
                severity=SeverityLevel.HIGH,
                action=(
                    "Initiate staggered exit: release sections in 3 waves, "
                    "5 minutes apart. Direct crowd flow toward least-loaded "
                    f"exit gates: {gate_list_text}."
                ),
                reason=(
                    f"Occupancy ratio is {occupancy_ratio:.0%} (≥ 90%). "
                    f"High density requires controlled, phased egress to "
                    f"prevent crushing and bottlenecks."
                ),
                affected_zone="ALL",
                confidence=ConfidenceLevel.CERTAIN,
            )
        )
    elif occupancy_ratio >= MODERATE_OCCUPANCY_RATIO:
        recommendations.append(
            Recommendation(
                rule_id="egress_plan",
                severity=SeverityLevel.MEDIUM,
                action=(
                    "Initiate standard staggered exit in 2 waves. "
                    f"Recommended exit gates: {gate_list_text}."
                ),
                reason=(
                    f"Occupancy ratio is {occupancy_ratio:.0%} (70–89%). "
                    f"Moderate density; standard phased exit is advised."
                ),
                affected_zone="ALL",
                confidence=ConfidenceLevel.LIKELY,
            )
        )
    else:
        recommendations.append(
            Recommendation(
                rule_id="egress_plan",
                severity=SeverityLevel.LOW,
                action=(
                    "Standard exit procedures. Monitor gate queues. "
                    f"Recommended exit gates: {gate_list_text}."
                ),
                reason=(
                    f"Occupancy ratio is {occupancy_ratio:.0%} (< 70%). "
                    f"Low density; routine egress monitoring is sufficient."
                ),
                affected_zone="ALL",
                confidence=ConfidenceLevel.ADVISORY,
            )
        )

    logger.info(
        "egress_plan: occupancy=%.0f%% severity=%s",
        occupancy_ratio * 100,
        recommendations[0].severity.value,
    )
    return recommendations
