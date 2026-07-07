"""
Integration tests for the StadiumOps AI API layer.

Uses FastAPI TestClient to validate endpoint behaviour including
authentication, validation, and response structure.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Fixture payloads
# ═══════════════════════════════════════════════════════════════════════════


def _full_valid_payload() -> dict:
    """Return a complete, valid payload for the /api/analyze endpoint."""
    return {
        "gates": [
            {
                "gate_id": "G1",
                "capacity_percent": 85,
                "entry_rate": 40,
                "wait_time_seconds": 300,
            },
            {
                "gate_id": "G2",
                "capacity_percent": 30,
                "entry_rate": 10,
                "wait_time_seconds": 60,
            },
            {
                "gate_id": "G3",
                "capacity_percent": 55,
                "entry_rate": 25,
                "wait_time_seconds": 120,
            },
        ],
        "incident": {
            "incident_id": "INC-100",
            "zone": "B3",
            "type": "medical",
            "description": "Fan collapsed near concession stand",
            "reporter_role": "medical_officer",
        },
        "weather": {
            "temperature_celsius": 35,
            "heat_index": 41,
            "lightning_detected": False,
            "lightning_radius_km": 50,
        },
        "event_context": {
            "phase": "halftime",
            "total_capacity": 50000,
            "occupied_seats": 42500,
            "accessible_seats_available": 12,
            "concession_queue_avg_minutes": 8.5,
        },
        "role": "admin",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Test 1 — Full valid analyze
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeEndpoint:
    """Tests for POST /api/analyze."""

    def test_valid_payload_returns_recommendations(self) -> None:
        """A full valid payload should return 200 with at least one recommendation."""
        response = client.post("/api/analyze", json=_full_valid_payload())
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) >= 1

        # Verify severity ordering: first recommendation should be the
        # highest severity present
        severities = [r["severity"] for r in data["recommendations"]]
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        sorted_severities = sorted(severities, key=lambda s: severity_order[s])
        assert severities == sorted_severities

    def test_viewer_cannot_submit_fire_smoke(self) -> None:
        """A viewer submitting a fire_smoke incident should receive 403."""
        payload = _full_valid_payload()
        payload["role"] = "viewer"
        payload["incident"]["type"] = "fire_smoke"
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 403

    def test_malformed_payload_returns_422(self) -> None:
        """A payload missing required fields should return 422."""
        incomplete_payload = {
            "gates": [],
            # Missing: incident, weather, event_context, role
        }
        response = client.post("/api/analyze", json=incomplete_payload)
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Test 4 — Incident endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestIncidentEndpoint:
    """Tests for POST /api/incident."""

    def test_valid_medical_incident(self) -> None:
        """A valid medical incident should return 200 with High severity."""
        incident = {
            "incident_id": "INC-200",
            "zone": "A2",
            "type": "medical",
            "description": "Spectator experiencing chest pain",
            "reporter_role": "first_aid",
        }
        response = client.post("/api/incident", json=incident)
        assert response.status_code == 200
        data = response.json()
        assert "recommendations" in data
        assert len(data["recommendations"]) >= 1
        # The triage_incident for medical returns High
        severities = [r["severity"] for r in data["recommendations"]]
        assert "High" in severities


# ═══════════════════════════════════════════════════════════════════════════
# Test 5 — Health endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint should return 200 with status ok and version."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
