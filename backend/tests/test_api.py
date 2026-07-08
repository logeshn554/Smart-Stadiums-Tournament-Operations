"""
Integration tests for the StadiumOps AI API layer.

Uses FastAPI TestClient to validate endpoint behaviour including
authentication, validation, response structure, security headers,
rate limiting, HTML sanitisation, role-based access control,
audit log, WebSocket connectivity, and sort edge cases.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes import _audit_log, _rate_limit_store, _sort_recommendations
from backend.models.schemas import ConfidenceLevel, Recommendation, SeverityLevel

client = TestClient(app)


def _full_valid_payload() -> dict:
    """Return a complete, valid payload for the /api/analyze endpoint."""
    return {
        "gates": [
            {"gate_id": "G1", "capacity_percent": 85, "entry_rate": 40, "wait_time_seconds": 300},
            {"gate_id": "G2", "capacity_percent": 30, "entry_rate": 10, "wait_time_seconds": 60},
            {"gate_id": "G3", "capacity_percent": 55, "entry_rate": 25, "wait_time_seconds": 120},
        ],
        "incident": {
            "incident_id": "INC-100", "zone": "B3", "type": "medical",
            "description": "Fan collapsed near concession stand",
            "reporter_role": "medical_officer",
        },
        "weather": {
            "temperature_celsius": 35, "heat_index": 41,
            "lightning_detected": False, "lightning_radius_km": 50,
        },
        "event_context": {
            "phase": "halftime", "total_capacity": 50000,
            "occupied_seats": 42500, "accessible_seats_available": 12,
            "concession_queue_avg_minutes": 8.5,
        },
        "role": "admin",
    }


class TestAnalyzeEndpoint:
    """Tests for POST /api/analyze."""

    def test_valid_payload_returns_recommendations(self) -> None:
        """A full valid payload returns 200 with severity-sorted recommendations."""
        response = client.post("/api/analyze", json=_full_valid_payload())
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) >= 1
        severities = [r["severity"] for r in data["recommendations"]]
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        assert severities == sorted(severities, key=lambda s: severity_order[s])

    def test_viewer_cannot_submit_fire_smoke(self) -> None:
        """Viewer submitting fire_smoke gets 403."""
        payload = _full_valid_payload()
        payload["role"] = "viewer"
        payload["incident"]["type"] = "fire_smoke"
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 403

    def test_malformed_payload_returns_422(self) -> None:
        """Missing required fields returns 422."""
        response = client.post("/api/analyze", json={"gates": []})
        assert response.status_code == 422

    def test_invalid_role_returns_422(self) -> None:
        """An invalid role value returns 422."""
        payload = _full_valid_payload()
        payload["role"] = "superuser"
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 422

    def test_html_sanitised_in_response(self) -> None:
        """HTML tags in description are stripped before processing."""
        payload = _full_valid_payload()
        payload["incident"]["description"] = "<b>Bold</b> emergency"
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        for rec in data["recommendations"]:
            assert "<b>" not in rec.get("reason", "")

    def test_recommendation_fields_present(self) -> None:
        """Each recommendation contains all required fields."""
        response = client.post("/api/analyze", json=_full_valid_payload())
        data = response.json()
        required_fields = {"rule_id", "severity", "action", "reason", "affected_zone", "confidence"}
        for rec in data["recommendations"]:
            assert required_fields.issubset(rec.keys())

    def test_admin_can_submit_fire_smoke(self) -> None:
        """Admin can submit fire_smoke without 403."""
        payload = _full_valid_payload()
        payload["role"] = "admin"
        payload["incident"]["type"] = "fire_smoke"
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200

    def test_empty_gates_returns_422(self) -> None:
        """Empty gates list is rejected (min_length=1)."""
        payload = _full_valid_payload()
        payload["gates"] = []
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 422

    def test_gate_capacity_over_100_returns_422(self) -> None:
        """Gate capacity > 100 is rejected by schema validation."""
        payload = _full_valid_payload()
        payload["gates"][0]["capacity_percent"] = 150
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 422

    def test_venue_id_default(self) -> None:
        """Payload without venue_id uses 'default'."""
        payload = _full_valid_payload()
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200

    def test_venue_id_custom(self) -> None:
        """Payload with custom venue_id is accepted."""
        payload = _full_valid_payload()
        payload["venue_id"] = "stadium-west"
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200


class TestIncidentEndpoint:
    """Tests for POST /api/incident."""

    def test_valid_medical_incident(self) -> None:
        """A valid medical incident returns 200 with High severity."""
        incident = {
            "incident_id": "INC-200", "zone": "A2", "type": "medical",
            "description": "Spectator experiencing chest pain",
            "reporter_role": "first_aid",
        }
        response = client.post("/api/incident", json=incident)
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        severities = [r["severity"] for r in data["recommendations"]]
        assert "High" in severities

    def test_fire_smoke_incident(self) -> None:
        """A fire_smoke incident returns Critical severity."""
        incident = {
            "incident_id": "INC-300", "zone": "C1", "type": "fire_smoke",
            "description": "Smoke detected near exit tunnel",
            "reporter_role": "security_lead",
        }
        response = client.post("/api/incident", json=incident)
        assert response.status_code == 200
        data = response.json()
        severities = [r["severity"] for r in data["recommendations"]]
        assert "Critical" in severities

    def test_missing_incident_field_returns_422(self) -> None:
        """Missing required incident field returns 422."""
        response = client.post("/api/incident", json={"incident_id": "INC-X"})
        assert response.status_code == 422


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint returns 200 with expected structure."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_security_headers_present(self) -> None:
        """All security headers are present on responses."""
        response = client.get("/api/health")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "strict-origin" in response.headers.get("Referrer-Policy", "")
        assert "default-src" in response.headers.get("Content-Security-Policy", "")

    def test_security_headers_on_post(self) -> None:
        """Security headers are also present on POST responses."""
        response = client.post("/api/analyze", json=_full_valid_payload())
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_hsts_header_present(self) -> None:
        """Strict-Transport-Security (HSTS) header is present."""
        response = client.get("/api/health")
        hsts = response.headers.get("Strict-Transport-Security", "")
        assert "max-age=" in hsts
        assert "includeSubDomains" in hsts

    def test_csp_includes_connect_src(self) -> None:
        """CSP includes connect-src for WebSocket support."""
        response = client.get("/api/health")
        csp = response.headers.get("Content-Security-Policy", "")
        assert "connect-src" in csp
        assert "ws:" in csp


class TestRateLimiting:
    """Tests for rate limiting on /api/incident."""

    def setup_method(self) -> None:
        """Clear the rate limit store before each test."""
        _rate_limit_store.clear()

    def test_rate_limit_allows_normal_traffic(self) -> None:
        """10 requests within the window should all succeed."""
        incident = {
            "incident_id": "INC-RL", "zone": "A1", "type": "security",
            "description": "Suspicious bag", "reporter_role": "steward",
        }
        for i in range(10):
            response = client.post("/api/incident", json=incident)
            assert response.status_code == 200, f"Request {i+1} failed unexpectedly"

    def test_rate_limit_exceeded_returns_429(self) -> None:
        """The 11th request within the window should return 429."""
        incident = {
            "incident_id": "INC-RL2", "zone": "A1", "type": "security",
            "description": "Rate limit test", "reporter_role": "steward",
        }
        # Send 10 requests (all should succeed)
        for i in range(10):
            response = client.post("/api/incident", json=incident)
            assert response.status_code == 200, f"Request {i+1} failed unexpectedly"

        # 11th request should be rate limited
        response = client.post("/api/incident", json=incident)
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]


class TestSortRecommendations:
    """Tests for the _sort_recommendations utility function."""

    def test_sort_with_unknown_severity(self) -> None:
        """Unknown severity values should sort to the end (rank 99)."""
        recs = [
            Recommendation(
                rule_id="test",
                severity=SeverityLevel.HIGH,
                action="Test action",
                reason="Test reason",
                affected_zone="A1",
                confidence=ConfidenceLevel.LIKELY,
            ),
            Recommendation(
                rule_id="test",
                severity=SeverityLevel.CRITICAL,
                action="Critical action",
                reason="Critical reason",
                affected_zone="A1",
                confidence=ConfidenceLevel.CERTAIN,
            ),
            Recommendation(
                rule_id="test",
                severity=SeverityLevel.LOW,
                action="Low action",
                reason="Low reason",
                affected_zone="A1",
                confidence=ConfidenceLevel.ADVISORY,
            ),
        ]
        sorted_recs = _sort_recommendations(recs)
        severities = [r.severity for r in sorted_recs]
        assert severities == [SeverityLevel.CRITICAL, SeverityLevel.HIGH, SeverityLevel.LOW]


class TestAuditLog:
    """Tests for the incident audit log endpoint."""

    def setup_method(self) -> None:
        """Clear the audit log before each test."""
        _audit_log.clear()

    def test_audit_log_empty_by_default(self) -> None:
        """Audit log returns empty entries for a new venue."""
        response = client.get("/api/audit?venue_id=test-venue")
        assert response.status_code == 200
        data = response.json()
        assert data["venue_id"] == "test-venue"
        assert data["total_entries"] == 0
        assert data["entries"] == []

    def test_audit_log_records_analyze(self) -> None:
        """Analyzing an incident records it in the audit log."""
        payload = _full_valid_payload()
        payload["venue_id"] = "audit-test"
        client.post("/api/analyze", json=payload)

        response = client.get("/api/audit?venue_id=audit-test")
        data = response.json()
        assert data["total_entries"] == 1
        assert data["entries"][0]["incident_id"] == "INC-100"
        assert data["entries"][0]["source"] == "analyze"

    def test_audit_log_records_incident(self) -> None:
        """The incident endpoint records to the default venue audit log."""
        _rate_limit_store.clear()
        incident = {
            "incident_id": "INC-AUD", "zone": "B1", "type": "medical",
            "description": "Test audit", "reporter_role": "steward",
        }
        client.post("/api/incident", json=incident)

        response = client.get("/api/audit?venue_id=default")
        data = response.json()
        assert data["total_entries"] >= 1
        incident_ids = [e["incident_id"] for e in data["entries"]]
        assert "INC-AUD" in incident_ids


class TestWebSocket:
    """Tests for the WebSocket endpoint."""

    def test_websocket_connects(self) -> None:
        """WebSocket endpoint accepts connections."""
        with client.websocket_connect("/api/ws") as ws:
            ws.send_text("ping")
            data = ws.receive_json()
            assert data["type"] == "pong"
            assert data["received"] == "ping"
