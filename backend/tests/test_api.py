"""
Integration tests for the StadiumOps AI API layer.

Uses FastAPI TestClient to validate endpoint behaviour including
authentication, validation, response structure, security headers,
rate limiting, HTML sanitisation, and role-based access control.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.routes import _rate_limit_store

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
