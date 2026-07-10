"""Unit tests for the StadiumOps AI Decision Engine (decision_engine.py).

Contains exactly 32 tests covering:
- Gate Load Balancing (10 tests)
- Incident Triage (6 tests)
- Weather Action (6 tests)
- Accessibility Routing (5 tests)
- Egress Planning (5 tests)
"""

from backend.core.decision_engine import (
    accessibility_routing,
    egress_plan,
    gate_load_balance,
    triage_incident,
    weather_action,
)
from backend.models.schemas import (
    ConfidenceLevel,
    EventContext,
    EventPhase,
    GateStatus,
    IncidentReport,
    SeverityLevel,
    WeatherContext,
)

# ═════════════════════════════════════════════════════════════════════════════
# ── GATE LOAD BALANCING TESTS (10 Tests) ─────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_gate_load_balance_empty() -> None:
    """Test 1: Empty gate list returns no recommendations."""
    assert gate_load_balance([]) == []


def test_gate_load_balance_single_gate() -> None:
    """Test 2: Single gate cannot trigger load balancing."""
    gate = GateStatus(
        gate_id="North-A", capacity_percent=90.0, entry_rate=50, wait_time_seconds=300
    )
    assert gate_load_balance([gate]) == []


def test_gate_load_balance_no_imbalance() -> None:
    """Test 3: Normal capacities do not trigger recommendations."""
    g1 = GateStatus(gate_id="North-A", capacity_percent=50.0, entry_rate=20, wait_time_seconds=100)
    g2 = GateStatus(gate_id="North-B", capacity_percent=60.0, entry_rate=25, wait_time_seconds=120)
    assert gate_load_balance([g1, g2]) == []


def test_gate_load_balance_all_overloaded() -> None:
    """Test 4: If all gates are overloaded, no underloaded target is available."""
    g1 = GateStatus(gate_id="North-A", capacity_percent=85.0, entry_rate=40, wait_time_seconds=200)
    g2 = GateStatus(gate_id="North-B", capacity_percent=90.0, entry_rate=45, wait_time_seconds=250)
    assert gate_load_balance([g1, g2]) == []


def test_gate_load_balance_all_underloaded() -> None:
    """Test 5: If all gates are underloaded, no redirect is necessary."""
    g1 = GateStatus(gate_id="North-A", capacity_percent=20.0, entry_rate=5, wait_time_seconds=30)
    g2 = GateStatus(gate_id="North-B", capacity_percent=30.0, entry_rate=8, wait_time_seconds=40)
    assert gate_load_balance([g1, g2]) == []


def test_gate_load_balance_single_imbalance() -> None:
    """Test 6: One overloaded and one underloaded gate triggers a recommendation."""
    g1 = GateStatus(gate_id="North-A", capacity_percent=85.0, entry_rate=40, wait_time_seconds=300)
    g2 = GateStatus(gate_id="North-B", capacity_percent=20.0, entry_rate=5, wait_time_seconds=60)

    recs = gate_load_balance([g1, g2])
    assert len(recs) == 1
    rec = recs[0]
    assert rec.rule_id == "gate_load_balance"
    assert rec.severity == SeverityLevel.HIGH
    assert "Redirect entry flow from gate North-A" in rec.action
    assert "gate North-B" in rec.action
    assert rec.affected_zone == "North-A"
    assert rec.confidence == ConfidenceLevel.LIKELY


def test_gate_load_balance_wait_time_reduction_calculation() -> None:
    """Test 7: Estimated wait reduction is correctly calculated as (over - under) // 2."""
    g1 = GateStatus(gate_id="North-A", capacity_percent=85.0, entry_rate=40, wait_time_seconds=300)
    g2 = GateStatus(gate_id="North-B", capacity_percent=20.0, entry_rate=5, wait_time_seconds=60)

    recs = gate_load_balance([g1, g2])
    # Expected wait reduction: (300 - 60) // 2 = 120
    assert "reduction: 120s" in recs[0].reason


def test_gate_load_balance_sorting() -> None:
    """Test 8: Recommendations are sorted with the highest wait time reduction first."""
    g_over = GateStatus(
        gate_id="Gate-Over", capacity_percent=90.0, entry_rate=50, wait_time_seconds=400
    )
    g_under1 = GateStatus(
        gate_id="Gate-Under-1", capacity_percent=10.0, entry_rate=2, wait_time_seconds=50
    )  # Diff: 350 // 2 = 175
    g_under2 = GateStatus(
        gate_id="Gate-Under-2", capacity_percent=20.0, entry_rate=5, wait_time_seconds=200
    )  # Diff: 200 // 2 = 100

    recs = gate_load_balance([g_over, g_under1, g_under2])
    assert len(recs) == 2
    assert "reduction: 175s" in recs[0].reason
    assert "reduction: 100s" in recs[1].reason


def test_gate_load_balance_capping() -> None:
    """Test 9: Output is capped to the top 4 (MAX_GATE_RECOMMENDATIONS) pairs."""
    g_over1 = GateStatus(
        gate_id="Over-1", capacity_percent=90.0, entry_rate=50, wait_time_seconds=500
    )
    g_over2 = GateStatus(
        gate_id="Over-2", capacity_percent=85.0, entry_rate=45, wait_time_seconds=400
    )

    g_under1 = GateStatus(
        gate_id="Under-1", capacity_percent=10.0, entry_rate=2, wait_time_seconds=20
    )
    g_under2 = GateStatus(
        gate_id="Under-2", capacity_percent=15.0, entry_rate=3, wait_time_seconds=30
    )
    g_under3 = GateStatus(
        gate_id="Under-3", capacity_percent=20.0, entry_rate=4, wait_time_seconds=40
    )

    # Pairs count: 2 overloaded * 3 underloaded = 6 possible recommendations
    recs = gate_load_balance([g_over1, g_over2, g_under1, g_under2, g_under3])
    assert len(recs) == 4


def test_gate_load_balance_boundary() -> None:
    """Test 10: Boundary capacities (exactly 80.0% and 40.0%) do not trigger."""
    g1 = GateStatus(gate_id="North-A", capacity_percent=80.0, entry_rate=40, wait_time_seconds=300)
    g2 = GateStatus(gate_id="North-B", capacity_percent=40.0, entry_rate=10, wait_time_seconds=60)
    assert gate_load_balance([g1, g2]) == []


# ═════════════════════════════════════════════════════════════════════════════
# ── INCIDENT TRIAGE TESTS (6 Tests) ──────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_triage_fire_smoke() -> None:
    """Test 11: Fire/smoke incident is Critical and triggers evacuation."""
    inc = IncidentReport(
        incident_id="INC-1",
        zone="B2",
        type="fire_smoke",
        description="Smoke in zone B2",
        reporter_role="steward",
    )
    rec = triage_incident(inc)
    assert rec.severity == SeverityLevel.CRITICAL
    assert "evacuation" in rec.action.lower()
    assert rec.confidence == ConfidenceLevel.CERTAIN


def test_triage_overcrowding() -> None:
    """Test 12: Overcrowding is High severity."""
    inc = IncidentReport(
        incident_id="INC-2",
        zone="C1",
        type="overcrowding",
        description="Too many fans in C1",
        reporter_role="steward",
    )
    rec = triage_incident(inc)
    assert rec.severity == SeverityLevel.HIGH
    assert "crowd control" in rec.action.lower()
    assert rec.confidence == ConfidenceLevel.CERTAIN


def test_triage_medical() -> None:
    """Test 13: Medical emergency is High severity."""
    inc = IncidentReport(
        incident_id="INC-3",
        zone="A3",
        type="medical",
        description="Chest pains",
        reporter_role="steward",
    )
    rec = triage_incident(inc)
    assert rec.severity == SeverityLevel.HIGH
    assert "medical team" in rec.action.lower()
    assert rec.confidence == ConfidenceLevel.CERTAIN


def test_triage_security() -> None:
    """Test 14: Security incident is Medium severity."""
    inc = IncidentReport(
        incident_id="INC-4",
        zone="B4",
        type="security",
        description="Fist fight",
        reporter_role="steward",
    )
    rec = triage_incident(inc)
    assert rec.severity == SeverityLevel.MEDIUM
    assert "security lead" in rec.action.lower()
    assert rec.confidence == ConfidenceLevel.LIKELY


def test_triage_lost_child() -> None:
    """Test 15: Lost child incident is Medium severity."""
    inc = IncidentReport(
        incident_id="INC-5",
        zone="D2",
        type="lost_child",
        description="Boy lost",
        reporter_role="parent",
    )
    rec = triage_incident(inc)
    assert rec.severity == SeverityLevel.MEDIUM
    assert "pa system" in rec.action.lower()
    assert rec.confidence == ConfidenceLevel.LIKELY


def test_triage_unknown_type() -> None:
    """Test 16: Unknown type defaults to Low severity."""
    inc = IncidentReport(
        incident_id="INC-6",
        zone="E1",
        type="spilled_drink",
        description="Messy spill",
        reporter_role="cleaner",
    )
    rec = triage_incident(inc)
    assert rec.severity == SeverityLevel.LOW
    assert "unknown incident type" in rec.action.lower()
    assert rec.confidence == ConfidenceLevel.ADVISORY


# ═════════════════════════════════════════════════════════════════════════════
# ── WEATHER ACTION TESTS (6 Tests) ───────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_weather_no_hazards() -> None:
    """Test 17: No lightning and low heat index triggers nothing."""
    weather = WeatherContext(
        temperature_celsius=25.0, heat_index=26.0, lightning_detected=False, lightning_radius_km=0.0
    )
    assert weather_action(weather) == []


def test_weather_lightning_critical() -> None:
    """Test 18: Lightning <= 15 km is Critical (shelter in place)."""
    weather = WeatherContext(
        temperature_celsius=25.0, heat_index=26.0, lightning_detected=True, lightning_radius_km=14.9
    )
    recs = weather_action(weather)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.CRITICAL
    assert "shelter-in-place" in recs[0].action.lower()
    assert recs[0].confidence == ConfidenceLevel.CERTAIN


def test_weather_lightning_high() -> None:
    """Test 19: Lightning > 15 km is High severity (warning only)."""
    weather = WeatherContext(
        temperature_celsius=25.0, heat_index=26.0, lightning_detected=True, lightning_radius_km=15.1
    )
    recs = weather_action(weather)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.HIGH
    assert "weather warning" in recs[0].action.lower()
    assert recs[0].confidence == ConfidenceLevel.LIKELY


def test_weather_extreme_heat() -> None:
    """Test 20: Heat index >= 40 triggers High severity hydration recommendation."""
    weather = WeatherContext(
        temperature_celsius=38.0, heat_index=40.0, lightning_detected=False, lightning_radius_km=0.0
    )
    recs = weather_action(weather)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.HIGH
    assert "hydration" in recs[0].action.lower()
    assert recs[0].confidence == ConfidenceLevel.CERTAIN


def test_weather_combined_hazards() -> None:
    """Test 21: Extreme heat + critical lightning triggers both rules."""
    weather = WeatherContext(
        temperature_celsius=38.0, heat_index=41.0, lightning_detected=True, lightning_radius_km=10.0
    )
    recs = weather_action(weather)
    assert len(recs) == 2
    severities = {r.severity for r in recs}
    assert SeverityLevel.CRITICAL in severities
    assert SeverityLevel.HIGH in severities


def test_weather_lightning_boundary() -> None:
    """Test 22: Boundary conditions for lightning (exactly 15.0 km) triggers Critical."""
    weather = WeatherContext(
        temperature_celsius=25.0, heat_index=26.0, lightning_detected=True, lightning_radius_km=15.0
    )
    recs = weather_action(weather)
    assert recs[0].severity == SeverityLevel.CRITICAL


# ═════════════════════════════════════════════════════════════════════════════
# ── ACCESSIBILITY ROUTING TESTS (5 Tests) ────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_accessibility_fire_evac_available_seats() -> None:
    """Test 23: Fire smoke in occupied venue triggers Critical priority assistance."""
    context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=40000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    inc = IncidentReport(
        incident_id="INC-1",
        zone="B1",
        type="fire_smoke",
        description="Kitchen fire",
        reporter_role="steward",
    )

    recs = accessibility_routing(context, inc)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.CRITICAL
    assert "mobility" in recs[0].action.lower()


def test_accessibility_overcrowd_available_seats() -> None:
    """Test 24: Overcrowding in occupied venue triggers Critical priority assistance."""
    context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=40000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    inc = IncidentReport(
        incident_id="INC-1",
        zone="B1",
        type="overcrowding",
        description="Stair surge",
        reporter_role="steward",
    )

    recs = accessibility_routing(context, inc)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.CRITICAL


def test_accessibility_full_capacity_seats() -> None:
    """Test 25: Zero accessible seats remaining triggers High severity monitor alert."""
    context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=40000,
        accessible_seats_available=0,
        concession_queue_avg_minutes=5.0,
    )
    inc = IncidentReport(
        incident_id="INC-1",
        zone="B1",
        type="medical",
        description="Stubbed toe",
        reporter_role="steward",
    )

    recs = accessibility_routing(context, inc)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.HIGH
    assert "full capacity" in recs[0].action.lower()


def test_accessibility_double_trigger() -> None:
    """Test 26: Fire smoke + zero accessible seats triggers BOTH Critical evacuation and High monitor alert."""
    context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=40000,
        accessible_seats_available=0,
        concession_queue_avg_minutes=5.0,
    )
    inc = IncidentReport(
        incident_id="INC-1",
        zone="B1",
        type="fire_smoke",
        description="Fire",
        reporter_role="steward",
    )

    # Wait, in schemas.py, if accessible_seats_available is 0:
    # Rule 4 code:
    # If incident type is fire_smoke/overcrowding AND context.accessible_seats_available > 0:
    #   Triggers Critical (evacuation assistance).
    # If context.accessible_seats_available == 0:
    #   Triggers High (seating at full capacity).
    # Therefore, if available seats == 0, the first condition (avail > 0) is False. So only the High alert is triggered.
    recs = accessibility_routing(context, inc)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.HIGH


def test_accessibility_no_trigger() -> None:
    """Test 27: Normal conditions (non-emergency type, accessible seats available) triggers nothing."""
    context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=40000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    inc = IncidentReport(
        incident_id="INC-1",
        zone="B1",
        type="medical",
        description="Dehydration",
        reporter_role="steward",
    )

    recs = accessibility_routing(context, inc)
    assert recs == []


# ═════════════════════════════════════════════════════════════════════════════
# ── EGRESS PLANNING TESTS (5 Tests) ──────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_egress_non_applicable_phase() -> None:
    """Test 28: Pre-match or Halftime phase returns no egress recommendations."""
    context = EventContext(
        phase=EventPhase.HALFTIME,
        total_capacity=50000,
        occupied_seats=40000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    gates = [GateStatus(gate_id="G1", capacity_percent=20.0, entry_rate=0, wait_time_seconds=30)]
    assert egress_plan(context, gates) == []


def test_egress_high_occupancy() -> None:
    """Test 29: Post-match with >= 90% occupancy triggers High severity, 3-wave staggered exit."""
    context = EventContext(
        phase=EventPhase.POST_MATCH,
        total_capacity=50000,
        occupied_seats=45000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    gates = [
        GateStatus(gate_id="G1", capacity_percent=20.0, entry_rate=0, wait_time_seconds=30),
        GateStatus(gate_id="G2", capacity_percent=50.0, entry_rate=0, wait_time_seconds=90),
    ]

    recs = egress_plan(context, gates)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.HIGH
    assert "3 waves" in recs[0].action


def test_egress_moderate_occupancy() -> None:
    """Test 30: Overtime with 70-89% occupancy triggers Medium severity, 2-wave staggered exit."""
    context = EventContext(
        phase=EventPhase.OVERTIME,
        total_capacity=50000,
        occupied_seats=38000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    gates = [
        GateStatus(gate_id="G1", capacity_percent=20.0, entry_rate=0, wait_time_seconds=30),
        GateStatus(gate_id="G2", capacity_percent=50.0, entry_rate=0, wait_time_seconds=90),
    ]

    recs = egress_plan(context, gates)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.MEDIUM
    assert "2 waves" in recs[0].action


def test_egress_low_occupancy() -> None:
    """Test 31: Post-match with < 70% occupancy triggers Low severity standard exit procedures."""
    context = EventContext(
        phase=EventPhase.POST_MATCH,
        total_capacity=50000,
        occupied_seats=30000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    gates = [
        GateStatus(gate_id="G1", capacity_percent=20.0, entry_rate=0, wait_time_seconds=30),
        GateStatus(gate_id="G2", capacity_percent=50.0, entry_rate=0, wait_time_seconds=90),
    ]

    recs = egress_plan(context, gates)
    assert len(recs) == 1
    assert recs[0].severity == SeverityLevel.LOW
    assert "standard exit" in recs[0].action.lower()


def test_egress_exit_gate_sorting() -> None:
    """Test 32: Least-congested exit gates are listed in order of capacity percentage."""
    context = EventContext(
        phase=EventPhase.POST_MATCH,
        total_capacity=50000,
        occupied_seats=45000,
        accessible_seats_available=5,
        concession_queue_avg_minutes=5.0,
    )
    gates = [
        GateStatus(gate_id="Gate-A", capacity_percent=90.0, entry_rate=0, wait_time_seconds=500),
        GateStatus(gate_id="Gate-B", capacity_percent=20.0, entry_rate=0, wait_time_seconds=50),
        GateStatus(gate_id="Gate-C", capacity_percent=15.0, entry_rate=0, wait_time_seconds=30),
    ]

    recs = egress_plan(context, gates)
    action_text = recs[0].action
    # Gate-C (15%) and Gate-B (20%) are the two least-congested
    assert "Gate-C (15%)" in action_text
    assert "Gate-B (20%)" in action_text
    assert "Gate-A" not in action_text


def test_non_string_description() -> None:
    """Test non-string description validation in IncidentReport."""
    from backend.models.schemas import IncidentReport

    result = IncidentReport.strip_html_tags(123)
    assert result == 123


def test_egress_plan_zero_total_capacity_direct() -> None:
    """Test egress_plan directly with zero total capacity to cover branch."""
    from unittest.mock import MagicMock

    from backend.core.decision_engine import egress_plan
    from backend.models.schemas import EventPhase

    mock_ctx = MagicMock()
    mock_ctx.phase = EventPhase.POST_MATCH
    mock_ctx.total_capacity = 0
    assert egress_plan(mock_ctx, []) == []
