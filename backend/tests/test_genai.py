"""Unit and integration tests for the StadiumOps AI GenAI features.

Validates GenAI playbook generation, chat assistant responses, fallback mock generators,
API endpoints, rate limiting, and header authentication.
"""

from typing import Never

import httpx
import pytest
from fastapi.testclient import TestClient

import backend.api.routes as _routes_module
from backend.api.main import app
from backend.api.routes import RATE_LIMIT_MAX
from backend.core.genai import (
    chat_with_assistant,
    generate_briefing_and_playbook,
)
from backend.models.schemas import (
    EventContext,
    GateStatus,
    IncidentReport,
    WeatherContext,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def _valid_gates() -> list[GateStatus]:
    return [
        GateStatus(gate_id="North-A", capacity_percent=85.0, entry_rate=45, wait_time_seconds=340),
        GateStatus(gate_id="South-A", capacity_percent=25.0, entry_rate=8, wait_time_seconds=45),
    ]


def _valid_incident(incident_type: str = "medical") -> IncidentReport:
    return IncidentReport(
        incident_id="INC-100",
        zone="B3",
        type=incident_type,
        description="Spectator collapsed near Row 14",
        reporter_role="steward",
    )


def _valid_weather(lightning: bool = False, radius: float = 50.0) -> WeatherContext:
    return WeatherContext(
        temperature_celsius=38.0,
        heat_index=41.0,
        lightning_detected=lightning,
        lightning_radius_km=radius,
    )


def _valid_event() -> EventContext:
    return EventContext(
        phase="halftime",
        total_capacity=60000,
        occupied_seats=51000,
        accessible_seats_available=12,
        concession_queue_avg_minutes=9.2,
    )


def _valid_payload() -> dict:
    return {
        "gates": [
            {"gate_id": "North-A", "capacity_percent": 85.0, "entry_rate": 45, "wait_time_seconds": 340},
            {"gate_id": "South-A", "capacity_percent": 25.0, "entry_rate": 8, "wait_time_seconds": 45},
        ],
        "incident": {
            "incident_id": "INC-100",
            "zone": "B3",
            "type": "medical",
            "description": "Spectator collapsed near Row 14",
            "reporter_role": "steward",
        },
        "weather": {
            "temperature_celsius": 38.0,
            "heat_index": 41.0,
            "lightning_detected": False,
            "lightning_radius_km": 50.0,
        },
        "event_context": {
            "phase": "halftime",
            "total_capacity": 60000,
            "occupied_seats": 51000,
            "accessible_seats_available": 12,
            "concession_queue_avg_minutes": 9.2,
        },
        "role": "admin",
    }


class TestGenAICoreMockFallback:
    """Validate core GenAI functions fall back to custom context-aware mock generators."""

    @pytest.mark.anyio
    async def test_mock_playbook_fire_smoke(self) -> None:
        gates = _valid_gates()
        incident = _valid_incident("fire_smoke")
        weather = _valid_weather()
        event = _valid_event()

        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key=None)
        assert "CRITICAL ALERT" in res["summary"]
        assert "fire" in res["summary"].lower()
        assert len(res["steps"]) >= 3
        assert "en" in res["announcements"]
        assert "es" in res["announcements"]
        assert "fr" in res["announcements"]

    @pytest.mark.anyio
    async def test_mock_playbook_lightning(self) -> None:
        gates = _valid_gates()
        incident = _valid_incident("medical")
        weather = _valid_weather(lightning=True, radius=8.0)
        event = _valid_event()

        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key=None)
        assert "CRITICAL WEATHER ALERT" in res["summary"]
        assert "lightning" in res["summary"].lower()

    @pytest.mark.anyio
    async def test_mock_playbook_medical(self) -> None:
        gates = _valid_gates()
        incident = _valid_incident("medical")
        weather = _valid_weather()
        event = _valid_event()

        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key=None)
        assert "HIGH INCIDENT ALERT" in res["summary"]
        assert "medical" in res["summary"].lower()

    @pytest.mark.anyio
    async def test_mock_playbook_gate_imbalance(self) -> None:
        gates = _valid_gates()
        incident = _valid_incident("security")
        weather = _valid_weather()
        event = _valid_event()

        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key=None)
        assert "OPERATIONAL BOTTLENECK" in res["summary"]

    @pytest.mark.anyio
    async def test_mock_playbook_default(self) -> None:
        gates = [GateStatus(gate_id="G1", capacity_percent=50, entry_rate=20, wait_time_seconds=100)]
        incident = _valid_incident("security")
        weather = _valid_weather()
        event = _valid_event()

        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key=None)
        assert "NORMAL OPERATIONS" in res["summary"]

    @pytest.mark.anyio
    async def test_mock_chat_scenarios(self) -> None:
        gates = _valid_gates()
        incident = _valid_incident("medical")
        weather = _valid_weather()
        event = _valid_event()

        # Lost child
        reply = await chat_with_assistant("Draft alert for lost child", [], gates, incident, weather, event, None)
        assert "Lost Child Protocol" in reply

        # Fire
        reply = await chat_with_assistant("fire in B3!", [], gates, incident, weather, event, None)
        assert "Fire/Evacuation Protocol" in reply

        # Lightning
        reply = await chat_with_assistant("What is the weather warning?", [], gates, incident, weather, event, None)
        assert "Weather Protocol" in reply

        # Gate redirection
        reply = await chat_with_assistant("How are gate lines?", [], gates, incident, weather, event, None)
        assert "Crowd Redirection" in reply

        # Greetings
        reply = await chat_with_assistant("hello", [], gates, incident, weather, event, None)
        assert "GenAI Control Room Assistant" in reply

        # Default
        reply = await chat_with_assistant("What is our capacity?", [], gates, incident, weather, event, None)
        assert "Operational Guidance" in reply


class TestGenAIEndpoints:
    """Validate POST /api/genai/playbook and POST /api/genai/chat endpoints."""

    def test_playbook_endpoint_succeeds(self) -> None:
        response = client.post("/api/genai/playbook", json=_valid_payload())
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "steps" in data
        assert "announcements" in data
        assert "en" in data["announcements"]

    def test_chat_endpoint_succeeds(self) -> None:
        chat_payload = {
            "message": "Hello assistance",
            "history": [],
            "gates": _valid_payload()["gates"],
            "incident": _valid_payload()["incident"],
            "weather": _valid_payload()["weather"],
            "event_context": _valid_payload()["event_context"],
        }
        response = client.post("/api/genai/chat", json=chat_payload)
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 0

    def test_playbook_rate_limiting(self) -> None:
        _routes_module._rate_limit_store.clear()
        assert len(_routes_module._rate_limit_store) == 0
        # Trigger RATE_LIMIT_MAX allowed requests
        for i in range(RATE_LIMIT_MAX):
            response = client.post("/api/genai/playbook", json=_valid_payload())
            assert response.status_code == 200, f"Request {i+1} failed with {response.status_code}"
        # Next request should be blocked with 429
        response = client.post("/api/genai/playbook", json=_valid_payload())
        assert response.status_code == 429

    def test_playbook_header_key_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _routes_module._rate_limit_store.clear()
        called_api_key = None

        async def mock_generate(gates, incident, weather, event_context, api_key):
            nonlocal called_api_key
            called_api_key = api_key
            return {"summary": "Briefing", "steps": ["Step 1"], "announcements": {"en": "Hello"}}

        monkeypatch.setattr("backend.api.routes.generate_briefing_and_playbook", mock_generate)

        headers = {"X-Gemini-API-Key": "test-key-123"}
        response = client.post("/api/genai/playbook", json=_valid_payload(), headers=headers)
        assert response.status_code == 200
        assert called_api_key == "test-key-123"


class TestGenAIHTTPCalls:
    """Validate HTTP requests are correctly made to Gemini endpoint when key is present."""

    @pytest.mark.anyio
    async def test_gemini_briefing_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gates = _valid_gates()
        incident = _valid_incident()
        weather = _valid_weather()
        event = _valid_event()

        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"summary": "Gemini briefing", "steps": ["Gemini Step 1"], "announcements": {"en": "Gemini hello", "es": "Gemini hola", "fr": "Gemini bonjour"}}'
                            }
                        ]
                    }
                }
            ]
        }

        # Mock the httpx.AsyncClient.post method
        class MockResponse:
            def __init__(self) -> None:
                self.status_code = 200
            def raise_for_status(self) -> None:
                pass
            def json(self):
                return mock_response_json

        async def mock_post(self, *args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key="secret-gemini-key")
        assert res["summary"] == "Gemini briefing"
        assert res["steps"] == ["Gemini Step 1"]
        assert res["announcements"]["es"] == "Gemini hola"

    @pytest.mark.anyio
    async def test_gemini_chat_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gates = _valid_gates()
        incident = _valid_incident()
        weather = _valid_weather()
        event = _valid_event()

        mock_response_json = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "Gemini response to question"
                            }
                        ]
                    }
                }
            ]
        }

        class MockResponse:
            def __init__(self) -> None:
                self.status_code = 200
            def raise_for_status(self) -> None:
                pass
            def json(self):
                return mock_response_json

        async def mock_post(self, *args, **kwargs):
            return MockResponse()

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

        res = await chat_with_assistant("Explain lightning protocol", [], gates, incident, weather, event, api_key="secret-gemini-key")
        assert res == "Gemini response to question"

    @pytest.mark.anyio
    async def test_gemini_api_failure_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        gates = _valid_gates()
        incident = _valid_incident()
        weather = _valid_weather()
        event = _valid_event()

        async def mock_post_fail(self, *args, **kwargs) -> Never:
            raise httpx.HTTPStatusError("API Error", request=None, response=None)

        monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_fail)

        # Should fall back to mock without raising exception
        res = await generate_briefing_and_playbook(gates, incident, weather, event, api_key="secret-gemini-key")
        assert "HIGH INCIDENT ALERT" in res["summary"]
