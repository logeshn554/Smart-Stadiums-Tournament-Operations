"""
Unit tests for the StadiumOps AI decision engine.

Every rule is tested for:
  • Happy-path (expected trigger)
  • Edge-case (boundary values)
  • No-trigger case (empty list / Low severity)
  • Invalid / adversarial inputs
"""

import pytest

from backend.core.decision_engine import (
    accessibility_routing,
    egress_plan,
    gate_load_balance,
    triage_incident,
    weather_action,
)
from backend.models.schemas import (
    EventContext,
    EventPhase,
    GateStatus,
    IncidentReport,
    Recommendation,
    WeatherContext,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_gate(
    gate_id: str = "G1",
    capacity_percent: float = 50.0,
    entry_rate: int = 20,
    wait_time_seconds: int = 60,
) -> GateStatus:
    """Create a GateStatus with sensible defaults for testing."""
    return GateStatus(
        gate_id=gate_id,
        capacity_percent=capacity_percent,
        entry_rate=entry_rate,
        wait_time_seconds=wait_time_seconds,
    )


def _make_incident(
    incident_id: str = "INC-001",
    zone: str = "A1",
    incident_type: str = "medical",
    description: str = "Test incident",
    reporter_role: str = "security_lead",
) -> IncidentReport:
    """Create an IncidentReport with sensible defaults for testing."""
    return IncidentReport(
        incident_id=incident_id,
        zone=zone,
        type=incident_type,
        description=description,
        reporter_role=reporter_role,
    )


def _make_weather(
    temperature_celsius: float = 30.0,
    heat_index: float = 32.0,
    lightning_detected: bool = False,
    lightning_radius_km: float = 50.0,
) -> WeatherContext:
    """Create a WeatherContext with sensible defaults for testing."""
    return WeatherContext(
        temperature_celsius=temperature_celsius,
        heat_index=heat_index,
        lightning_detected=lightning_detected,
        lightning_radius_km=lightning_radius_km,
    )


def _make_event(
    phase: EventPhase = EventPhase.HALFTIME,
    total_capacity: int = 50000,
    occupied_seats: int = 25000,
    accessible_seats_available: int = 20,
    concession_queue_avg_minutes: float = 5.0,
) -> EventContext:
    """Create an EventContext with sensible defaults for testing."""
    return EventContext(
        phase=phase,
        total_capacity=total_capacity,
        occupied_seats=occupied_seats,
        accessible_seats_available=accessible_seats_available,
        concession_queue_avg_minutes=concession_queue_avg_minutes,
    )


def _assert_recommendation_shape(rec: Recommendation) -> None:
    """Assert that a Recommendation has the expected field types and is non-empty."""
    assert isinstance(rec.rule_id, str) and rec.rule_id
    assert rec.severity in ("Low", "Medium", "High", "Critical")
    assert isinstance(rec.action, str) and rec.action
    assert isinstance(rec.reason, str) and rec.reason
    assert isinstance(rec.affected_zone, str) and rec.affected_zone
    assert rec.confidence in ("Certain", "Likely", "Advisory")


# ═══════════════════════════════════════════════════════════════════════════
# RULE 1 — gate_load_balance
# ═══════════════════════════════════════════════════════════════════════════


class TestGateLoadBalance:
    """Tests for the gate_load_balance rule."""

    def test_happy_path_overloaded_and_underloaded(self) -> None:
        """When one gate is >80% and another is <40% a High recommendation fires."""
        gates = [
            _make_gate("G1", capacity_percent=90, wait_time_seconds=300),
            _make_gate("G2", capacity_percent=30, wait_time_seconds=60),
        ]
        results = gate_load_balance(gates)
        assert len(results) == 1
        rec = results[0]
        _assert_recommendation_shape(rec)
        assert rec.severity == "High"
        assert rec.rule_id == "gate_load_balance"
        assert "120" in rec.reason  # (300 - 60) // 2 == 120

    def test_edge_case_exactly_80_percent(self) -> None:
        """A gate at exactly 80% should NOT be flagged as overloaded (>80 required)."""
        gates = [
            _make_gate("G1", capacity_percent=80, wait_time_seconds=200),
            _make_gate("G2", capacity_percent=30, wait_time_seconds=60),
        ]
        results = gate_load_balance(gates)
        assert results == []

    def test_edge_case_exactly_40_percent(self) -> None:
        """A gate at exactly 40% should NOT be flagged as underloaded (<40 required)."""
        gates = [
            _make_gate("G1", capacity_percent=90, wait_time_seconds=200),
            _make_gate("G2", capacity_percent=40, wait_time_seconds=60),
        ]
        results = gate_load_balance(gates)
        assert results == []

    def test_no_trigger_all_balanced(self) -> None:
        """When all gates are in the 40–80% range no recommendation is produced."""
        gates = [
            _make_gate("G1", capacity_percent=60),
            _make_gate("G2", capacity_percent=55),
        ]
        results = gate_load_balance(gates)
        assert results == []

    def test_empty_gate_list(self) -> None:
        """An empty gate list returns an empty recommendation list."""
        results = gate_load_balance([])
        assert results == []

    def test_adversarial_capacity_over_100(self) -> None:
        """Pydantic should reject capacity_percent > 100."""
        with pytest.raises(Exception):
            _make_gate("G1", capacity_percent=150)

    def test_multiple_pairs(self) -> None:
        """Two overloaded and one underloaded gate produce two recommendations."""
        gates = [
            _make_gate("G1", capacity_percent=85, wait_time_seconds=200),
            _make_gate("G2", capacity_percent=95, wait_time_seconds=400),
            _make_gate("G3", capacity_percent=20, wait_time_seconds=30),
        ]
        results = gate_load_balance(gates)
        assert len(results) == 2
        for rec in results:
            _assert_recommendation_shape(rec)
            assert rec.severity == "High"


# ═══════════════════════════════════════════════════════════════════════════
# RULE 2 — triage_incident
# ═══════════════════════════════════════════════════════════════════════════


class TestTriageIncident:
    """Tests for the triage_incident rule."""

    @pytest.mark.parametrize(
        "incident_type, expected_severity",
        [
            ("fire_smoke", "Critical"),
            ("overcrowding", "High"),
            ("medical", "High"),
            ("security", "Medium"),
            ("lost_child", "Medium"),
        ],
    )
    def test_happy_path_known_types(
        self, incident_type: str, expected_severity: str
    ) -> None:
        """Each known incident type maps to the correct severity."""
        report = _make_incident(incident_type=incident_type)
        rec = triage_incident(report)
        _assert_recommendation_shape(rec)
        assert rec.severity == expected_severity
        assert rec.rule_id == "triage_incident"
        assert report.zone in rec.reason
        assert report.reporter_role in rec.reason

    def test_unknown_type_returns_low(self) -> None:
        """An unknown incident type should produce a Low-severity recommendation."""
        report = _make_incident(incident_type="alien_invasion")
        rec = triage_incident(report)
        _assert_recommendation_shape(rec)
        assert rec.severity == "Low"
        assert "alien_invasion" in rec.action

    def test_html_stripped_from_description(self) -> None:
        """HTML tags in description should be stripped by the schema validator."""
        report = _make_incident(
            description="<script>alert('xss')</script>Man down near exit"
        )
        assert "<" not in report.description
        rec = triage_incident(report)
        _assert_recommendation_shape(rec)

    def test_reason_contains_zone_and_role(self) -> None:
        """The reason field must always mention the reporter role and zone."""
        report = _make_incident(zone="C5", reporter_role="gate_manager")
        rec = triage_incident(report)
        assert "C5" in rec.reason
        assert "gate_manager" in rec.reason


# ═══════════════════════════════════════════════════════════════════════════
# RULE 3 — weather_action
# ═══════════════════════════════════════════════════════════════════════════


class TestWeatherAction:
    """Tests for the weather_action rule."""

    def test_lightning_close_range(self) -> None:
        """Lightning ≤ 15 km triggers Critical shelter-in-place."""
        weather = _make_weather(lightning_detected=True, lightning_radius_km=10)
        results = weather_action(weather)
        assert len(results) >= 1
        critical_recs = [r for r in results if r.severity == "Critical"]
        assert len(critical_recs) == 1
        assert critical_recs[0].rule_id == "weather_action"

    def test_lightning_far_range(self) -> None:
        """Lightning > 15 km triggers High weather warning."""
        weather = _make_weather(lightning_detected=True, lightning_radius_km=20)
        results = weather_action(weather)
        assert len(results) >= 1
        high_recs = [r for r in results if r.severity == "High"]
        assert len(high_recs) == 1

    def test_edge_case_lightning_exactly_15_km(self) -> None:
        """Lightning at exactly 15 km is within the ≤15 threshold → Critical."""
        weather = _make_weather(lightning_detected=True, lightning_radius_km=15)
        results = weather_action(weather)
        critical_recs = [r for r in results if r.severity == "Critical"]
        assert len(critical_recs) == 1

    def test_heat_index_above_40(self) -> None:
        """Heat index ≥ 40 triggers hydration High recommendation."""
        weather = _make_weather(heat_index=42)
        results = weather_action(weather)
        assert len(results) == 1
        assert results[0].severity == "High"
        assert "hydration" in results[0].action.lower()

    def test_edge_case_heat_index_exactly_40(self) -> None:
        """Heat index at exactly 40 should trigger."""
        weather = _make_weather(heat_index=40)
        results = weather_action(weather)
        assert len(results) == 1

    def test_both_lightning_and_heat(self) -> None:
        """Both lightning and extreme heat can trigger simultaneously."""
        weather = _make_weather(
            lightning_detected=True, lightning_radius_km=10, heat_index=45
        )
        results = weather_action(weather)
        assert len(results) == 2

    def test_no_trigger_mild_weather(self) -> None:
        """Mild weather produces no recommendations."""
        weather = _make_weather()
        results = weather_action(weather)
        assert results == []

    def test_no_lightning_detected(self) -> None:
        """Lightning not detected, even at close radius, produces nothing."""
        weather = _make_weather(lightning_detected=False, lightning_radius_km=5)
        results = weather_action(weather)
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# RULE 4 — accessibility_routing
# ═══════════════════════════════════════════════════════════════════════════


class TestAccessibilityRouting:
    """Tests for the accessibility_routing rule."""

    def test_fire_smoke_with_available_seats(self) -> None:
        """fire_smoke with accessible seats available → Critical dispatch."""
        context = _make_event(accessible_seats_available=10)
        incident = _make_incident(incident_type="fire_smoke")
        results = accessibility_routing(context, incident)
        assert len(results) >= 1
        critical_recs = [r for r in results if r.severity == "Critical"]
        assert len(critical_recs) == 1
        assert "10" in critical_recs[0].reason

    def test_overcrowding_with_available_seats(self) -> None:
        """overcrowding with accessible seats → Critical dispatch."""
        context = _make_event(accessible_seats_available=5)
        incident = _make_incident(incident_type="overcrowding")
        results = accessibility_routing(context, incident)
        critical_recs = [r for r in results if r.severity == "Critical"]
        assert len(critical_recs) == 1

    def test_zero_accessible_seats_any_incident(self) -> None:
        """Zero accessible seats during any incident → High monitoring flag."""
        context = _make_event(accessible_seats_available=0)
        incident = _make_incident(incident_type="medical")
        results = accessibility_routing(context, incident)
        assert len(results) == 1
        assert results[0].severity == "High"
        assert results[0].rule_id == "accessibility_routing"

    def test_fire_smoke_zero_accessible_seats(self) -> None:
        """fire_smoke with zero accessible seats triggers both Critical-routing and High-monitoring."""
        context = _make_event(accessible_seats_available=0)
        incident = _make_incident(incident_type="fire_smoke")
        results = accessibility_routing(context, incident)
        # fire_smoke with 0 seats: the first condition (>0) is false, so no Critical
        # but the second condition (==0) is true, so High
        assert len(results) == 1
        assert results[0].severity == "High"

    def test_no_trigger_medical_with_seats(self) -> None:
        """Medical incident with available seats should not trigger Critical."""
        context = _make_event(accessible_seats_available=15)
        incident = _make_incident(incident_type="medical")
        results = accessibility_routing(context, incident)
        assert results == []

    def test_recommendation_shape(self) -> None:
        """Verify recommendation fields are correctly typed."""
        context = _make_event(accessible_seats_available=8)
        incident = _make_incident(incident_type="overcrowding", zone="D2")
        results = accessibility_routing(context, incident)
        for rec in results:
            _assert_recommendation_shape(rec)


# ═══════════════════════════════════════════════════════════════════════════
# RULE 5 — egress_plan
# ═══════════════════════════════════════════════════════════════════════════


class TestEgressPlan:
    """Tests for the egress_plan rule."""

    def test_high_occupancy_post_match(self) -> None:
        """≥ 90% occupancy in post_match → High staggered 3-wave exit."""
        context = _make_event(
            phase=EventPhase.POST_MATCH,
            total_capacity=50000,
            occupied_seats=46000,
        )
        gates = [
            _make_gate("G1", capacity_percent=70),
            _make_gate("G2", capacity_percent=30),
            _make_gate("G3", capacity_percent=50),
        ]
        results = egress_plan(context, gates)
        assert len(results) == 1
        rec = results[0]
        _assert_recommendation_shape(rec)
        assert rec.severity == "High"
        assert "3 waves" in rec.action
        assert "G2" in rec.action  # least loaded gate

    def test_medium_occupancy_overtime(self) -> None:
        """70–89% occupancy in overtime → Medium 2-wave exit."""
        context = _make_event(
            phase=EventPhase.OVERTIME,
            total_capacity=50000,
            occupied_seats=40000,
        )
        gates = [_make_gate("G1", capacity_percent=50)]
        results = egress_plan(context, gates)
        assert len(results) == 1
        assert results[0].severity == "Medium"
        assert "2 waves" in results[0].action

    def test_low_occupancy_post_match(self) -> None:
        """< 70% occupancy → Low standard exit."""
        context = _make_event(
            phase=EventPhase.POST_MATCH,
            total_capacity=50000,
            occupied_seats=20000,
        )
        gates = [_make_gate("G1", capacity_percent=20)]
        results = egress_plan(context, gates)
        assert len(results) == 1
        assert results[0].severity == "Low"

    def test_edge_case_exactly_90_percent(self) -> None:
        """Exactly 90% occupancy should trigger High."""
        context = _make_event(
            phase=EventPhase.POST_MATCH,
            total_capacity=10000,
            occupied_seats=9000,
        )
        gates = [_make_gate("G1"), _make_gate("G2")]
        results = egress_plan(context, gates)
        assert results[0].severity == "High"

    def test_edge_case_exactly_70_percent(self) -> None:
        """Exactly 70% occupancy should trigger Medium."""
        context = _make_event(
            phase=EventPhase.POST_MATCH,
            total_capacity=10000,
            occupied_seats=7000,
        )
        gates = [_make_gate("G1"), _make_gate("G2")]
        results = egress_plan(context, gates)
        assert results[0].severity == "Medium"

    def test_no_trigger_pre_match_phase(self) -> None:
        """Egress plan should not fire during pre_match."""
        context = _make_event(phase=EventPhase.PRE_MATCH)
        gates = [_make_gate("G1")]
        results = egress_plan(context, gates)
        assert results == []

    def test_no_trigger_halftime_phase(self) -> None:
        """Egress plan should not fire during halftime."""
        context = _make_event(phase=EventPhase.HALFTIME)
        gates = [_make_gate("G1")]
        results = egress_plan(context, gates)
        assert results == []

    def test_top_two_gates_listed(self) -> None:
        """The two least-congested gates should appear in the recommendation."""
        context = _make_event(
            phase=EventPhase.POST_MATCH,
            total_capacity=50000,
            occupied_seats=47000,
        )
        gates = [
            _make_gate("G1", capacity_percent=80),
            _make_gate("G2", capacity_percent=20),
            _make_gate("G3", capacity_percent=10),
            _make_gate("G4", capacity_percent=60),
        ]
        results = egress_plan(context, gates)
        rec = results[0]
        assert "G3" in rec.action
        assert "G2" in rec.action

    def test_adversarial_negative_wait_time(self) -> None:
        """Negative wait_time_seconds should be rejected by Pydantic."""
        with pytest.raises(Exception):
            _make_gate("G1", wait_time_seconds=-10)
