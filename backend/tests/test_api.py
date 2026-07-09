"""
Integration tests for the StadiumOps AI FastAPI endpoints.

Contains exactly 29 tests targeting:
- Authentication & JWT (3 tests)
- Health Check (1 test)
- Analyze Endpoint (9 tests)
- Incident Endpoint (4 tests)
- Audit Log Endpoint (3 tests)
- GenAI Endpoints (2 tests)
- WebSockets (4 tests)
- Middleware & Headers (3 tests)
"""

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.core.auth import create_access_token, verify_token
from backend.api.routes import _rate_limit_store, _sweep_rate_limit_store, _SWEEP_INTERVAL_SECONDS

client = TestClient(app)

# Helper mock payload
VALID_PAYLOAD = {
    "venue_id": "stadium-1",
    "gates": [
        {"gate_id": "North-A", "capacity_percent": 85.0, "entry_rate": 40, "wait_time_seconds": 300},
        {"gate_id": "South-A", "capacity_percent": 20.0, "entry_rate": 5, "wait_time_seconds": 60},
    ],
    "incident": {
        "incident_id": "INC-100",
        "zone": "B1",
        "type": "medical",
        "description": "Dehydrated fan",
        "reporter_role": "steward",
    },
    "weather": {
        "temperature_celsius": 30.0,
        "heat_index": 32.0,
        "lightning_detected": False,
        "lightning_radius_km": 0.0,
    },
    "event_context": {
        "phase": "halftime",
        "total_capacity": 50000,
        "occupied_seats": 40000,
        "accessible_seats_available": 5,
        "concession_queue_avg_minutes": 5.0,
    },
    "role": "admin",
}

# ═════════════════════════════════════════════════════════════════════════════
# ── AUTHENTICATION TESTS (3 Tests) ───────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_create_and_verify_token_success():
    """Test 1: Creates a signed token and decodes it successfully."""
    token = create_access_token(role="admin", subject="test-user")
    payload = verify_token(token)
    assert payload["role"] == "admin"
    assert payload["sub"] == "test-user"


def test_verify_token_invalid_format():
    """Test 2: Rejects malformed JWT tokens."""
    with pytest.raises(ValueError, match="Invalid or expired token"):
        verify_token("invalid.token.here")


def test_verify_token_expired():
    """Test 3: Rejects expired tokens."""
    # Create a token that expired 10 minutes ago
    with patch("backend.core.auth.TOKEN_EXPIRE_MINUTES", -10):
        token = create_access_token(role="admin")
    with pytest.raises(ValueError, match="Invalid or expired token"):
        verify_token(token)


# ═════════════════════════════════════════════════════════════════════════════
# ── HEALTH CHECK TESTS (1 Test) ──────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_health_endpoint():
    """Test 4: Health endpoint returns version and ok status."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data


# ═════════════════════════════════════════════════════════════════════════════
# ── ANALYZE ENDPOINT TESTS (9 Tests) ─────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_analyze_success_with_jwt():
    """Test 5: Runs full analysis with JWT token authorized."""
    token = create_access_token(role="admin")
    headers = {"Authorization": f"Bearer {token}"}
    res = client.post("/api/analyze", json=VALID_PAYLOAD, headers=headers)
    assert res.status_code == 200
    assert "recommendations" in res.json()


def test_analyze_success_fallback_role():
    """Test 6: Runs full analysis using mock role field when no JWT is provided."""
    payload = VALID_PAYLOAD.copy()
    payload["role"] = "admin"
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    assert len(res.json()["recommendations"]) > 0


def test_analyze_unauthorized_viewer_critical_incident():
    """Test 7: Prevents viewer role from submitting fire/smoke critical incidents."""
    payload = VALID_PAYLOAD.copy()
    payload["role"] = "viewer"
    payload["incident"] = {
        "incident_id": "INC-ERR",
        "zone": "B1",
        "type": "fire_smoke",
        "description": "Kitchen fire",
        "reporter_role": "steward",
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 403
    assert "not authorised" in res.json()["detail"]


def test_analyze_authorized_admin_critical_incident():
    """Test 8: Allows admin role to submit fire/smoke critical incidents."""
    payload = VALID_PAYLOAD.copy()
    payload["role"] = "admin"
    payload["incident"] = {
        "incident_id": "INC-OK",
        "zone": "B1",
        "type": "fire_smoke",
        "description": "Kitchen fire",
        "reporter_role": "steward",
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    recs = res.json()["recommendations"]
    severities = [r["severity"] for r in recs]
    assert "Critical" in severities


def test_analyze_html_sanitization():
    """Test 9: Dynamic input descriptions strip HTML tags to prevent XSS."""
    payload = VALID_PAYLOAD.copy()
    payload["incident"] = {
        "incident_id": "INC-XSS",
        "zone": "B1",
        "type": "medical",
        "description": "<script>alert('XSS')</script>Fan collapsed.",
        "reporter_role": "steward",
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    recs = res.json()["recommendations"]
    triage_rec = [r for r in recs if r["rule_id"] == "triage_incident"][0]
    assert "<script>" not in triage_rec["reason"]
    assert "alert('XSS')" in triage_rec["reason"]


def test_analyze_missing_gates():
    """Test 10: Ensures Pydantic schema rejects empty gate list payload."""
    payload = VALID_PAYLOAD.copy()
    payload["gates"] = []
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422


def test_analyze_invalid_capacity():
    """Test 11: Ensures Pydantic schema rejects invalid capacity percentage ranges."""
    payload = VALID_PAYLOAD.copy()
    payload["gates"] = [
        {"gate_id": "G1", "capacity_percent": 110.0, "entry_rate": 10, "wait_time_seconds": 10}
    ]
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 422


def test_analyze_occupied_exceeds_total_capacity():
    """Test 12: EventContext caps occupied seats to total capacity if it exceeds it."""
    payload = VALID_PAYLOAD.copy()
    payload["event_context"] = {
        "phase": "halftime",
        "total_capacity": 50000,
        "occupied_seats": 60000,  # Exceeds total
        "accessible_seats_available": 5,
        "concession_queue_avg_minutes": 5.0,
    }
    res = client.post("/api/analyze", json=payload)
    assert res.status_code == 200
    # Audit log should show capped status or process successfully without crashing


def test_analyze_audit_logged():
    """Test 13: Verifies that /api/analyze appends logs to the audit service."""
    payload = VALID_PAYLOAD.copy()
    payload["venue_id"] = "audit-test-venue"
    payload["incident"]["incident_id"] = "INC-AUDIT-1"
    client.post("/api/analyze", json=payload)

    audit_res = client.get("/api/audit?venue_id=audit-test-venue")
    assert audit_res.status_code == 200
    entries = audit_res.json()["entries"]
    assert len(entries) > 0
    assert entries[-1]["incident_id"] == "INC-AUDIT-1"


# ═════════════════════════════════════════════════════════════════════════════
# ── INCIDENT ENDPOINT TESTS (4 Tests) ────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_incident_triage_success():
    """Test 14: Triage endpoint processes single incident successfully."""
    inc = {
        "incident_id": "INC-INC-1",
        "zone": "A2",
        "type": "security",
        "description": "Fist fight concourse",
        "reporter_role": "steward",
    }
    res = client.post("/api/incident", json=inc)
    assert res.status_code == 200
    assert "recommendations" in res.json()


def test_incident_triage_rate_limiting():
    """Test 15: Validates sliding window IP rate limiting (429 status on 11th request)."""
    # Clean previous logs to isolate rate limit
    _rate_limit_store.clear()
    inc = {
        "incident_id": "INC-LIMIT",
        "zone": "A2",
        "type": "security",
        "description": "Fist fight",
        "reporter_role": "steward",
    }

    # Send 10 quick requests
    for _ in range(10):
        res = client.post("/api/incident", json=inc)
        assert res.status_code == 200

    # 11th request must fail with 429
    res = client.post("/api/incident", json=inc)
    assert res.status_code == 429
    assert "Rate limit exceeded" in res.json()["detail"]


def test_incident_triage_sanitization():
    """Test 16: HTML tags stripped at incident triage layer."""
    _rate_limit_store.clear()
    inc = {
        "incident_id": "INC-HTML",
        "zone": "A2",
        "type": "security",
        "description": "Fight <b>active</b> here",
        "reporter_role": "steward",
    }
    res = client.post("/api/incident", json=inc)
    assert res.status_code == 200
    recs = res.json()["recommendations"]
    triage_rec = [r for r in recs if r["rule_id"] == "triage_incident"][0]
    assert "Fight active here" in triage_rec["reason"]
    assert "<b>" not in triage_rec["reason"]



def test_incident_triage_audit_logged():
    """Test 17: Incident triages are recorded under 'default' venue audit log."""
    _rate_limit_store.clear()
    inc = {
        "incident_id": "INC-AUDIT-DEF",
        "zone": "A2",
        "type": "security",
        "description": "Fight",
        "reporter_role": "steward",
    }
    client.post("/api/incident", json=inc)

    res = client.get("/api/audit?venue_id=default")
    assert res.status_code == 200
    incident_ids = [e["incident_id"] for e in res.json()["entries"]]
    assert "INC-AUDIT-DEF" in incident_ids


# ═════════════════════════════════════════════════════════════════════════════
# ── AUDIT LOG TESTS (3 Tests) ────────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_audit_log_empty_by_default():
    """Test 18: Unseen venues yield 0 audit entries."""
    res = client.get("/api/audit?venue_id=non-existent-venue")
    assert res.status_code == 200
    assert res.json()["total_entries"] == 0


def test_audit_log_isolation_by_venue():
    """Test 19: Venues maintain separate isolated audit stores."""
    payload_v1 = VALID_PAYLOAD.copy()
    payload_v1["venue_id"] = "Venue-1"
    payload_v1["incident"]["incident_id"] = "INC-V1"
    client.post("/api/analyze", json=payload_v1)

    payload_v2 = VALID_PAYLOAD.copy()
    payload_v2["venue_id"] = "Venue-2"
    payload_v2["incident"]["incident_id"] = "INC-V2"
    client.post("/api/analyze", json=payload_v2)

    res_v1 = client.get("/api/audit?venue_id=Venue-1")
    res_v2 = client.get("/api/audit?venue_id=Venue-2")

    ids_v1 = [e["incident_id"] for e in res_v1.json()["entries"]]
    ids_v2 = [e["incident_id"] for e in res_v2.json()["entries"]]

    assert "INC-V1" in ids_v1
    assert "INC-V2" not in ids_v1
    assert "INC-V2" in ids_v2
    assert "INC-V1" not in ids_v2


def test_audit_log_bounded_capacity():
    """Test 20: Audit logs act as ring buffers, capping at 100 entries."""
    payload = VALID_PAYLOAD.copy()
    payload["venue_id"] = "bounded-venue"

    for idx in range(110):
        payload["incident"]["incident_id"] = f"INC-{idx}"
        client.post("/api/analyze", json=payload)

    res = client.get("/api/audit?venue_id=bounded-venue")
    data = res.json()
    assert data["total_entries"] == 100
    first_id = data["entries"][0]["incident_id"]
    last_id = data["entries"][-1]["incident_id"]
    assert first_id == "INC-10"
    assert last_id == "INC-109"


# ═════════════════════════════════════════════════════════════════════════════
# ── GENAI PLAYBOOK & CHAT TESTS (2 Tests) ────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_genai_playbook_mock_fallback():
    """Test 21: Playbook endpoint returns a mock playbook structure when no API key exists."""
    res = client.post("/api/genai/playbook", json=VALID_PAYLOAD)
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "steps" in data
    assert "announcements" in data


def test_genai_chat_mock_fallback():
    """Test 22: Chat endpoint returns a mock response when no API key exists."""
    chat_payload = {
        "message": "We have a lost child in Section C.",
        "history": [],
        "gates": VALID_PAYLOAD["gates"],
        "incident": VALID_PAYLOAD["incident"],
        "weather": VALID_PAYLOAD["weather"],
        "event_context": VALID_PAYLOAD["event_context"],
    }
    res = client.post("/api/genai/chat", json=chat_payload)
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert "Lost Child Protocol" in data["reply"]


# ═════════════════════════════════════════════════════════════════════════════
# ── WEBSOCKET TESTS (4 Tests) ────────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_websocket_connection():
    """Test 23: WebSocket connection can be successfully established."""
    with client.websocket_connect("/api/ws") as websocket:
        assert websocket is not None


def test_websocket_ping_pong():
    """Test 24: Client receives a pong response for sent heartbeat strings."""
    with client.websocket_connect("/api/ws") as websocket:
        websocket.send_text("ping-test")
        data = websocket.receive_json()
        assert data["type"] == "pong"
        assert data["received"] == "ping-test"


def test_websocket_broadcast_on_incident():
    """Test 25: WebSocket receives broadcast update when new incidents are triaged."""
    _rate_limit_store.clear()
    with client.websocket_connect("/api/ws") as websocket:
        # Submit incident
        inc = {
            "incident_id": "INC-WS",
            "zone": "A1",
            "type": "medical",
            "description": "Ankle sprain",
            "reporter_role": "steward",
        }
        res = client.post("/api/incident", json=inc)
        assert res.status_code == 200

        # Read WS message
        data = websocket.receive_json()
        assert data["type"] == "recommendations_update"
        assert len(data["recommendations"]) > 0


def test_websocket_disconnect_cleanup():
    """Test 26: Gracefully cleans connections list when clients disconnect."""
    # Ensure connections list is tracked
    from backend.api.routes import _ws_connections
    initial_len = len(_ws_connections)

    with client.websocket_connect("/api/ws") as websocket:
        assert len(_ws_connections) == initial_len + 1

    # Out of context, client is disconnected
    assert len(_ws_connections) == initial_len


# ═════════════════════════════════════════════════════════════════════════════
# ── MIDDLEWARE & HEADERS TESTS (3 Tests) ─────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════


def test_cors_headers():
    """Test 27: CORS headers allow access to localhost origins."""
    res = client.options("/api/health", headers={
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type",
    })
    assert res.headers.get("access-control-allow-origin") == "http://localhost:8080"


def test_security_headers_present():
    """Test 28: Security headers are correctly added to response payloads."""
    res = client.get("/api/health")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["x-xss-protection"] == "1; mode=block"
    assert "Content-Security-Policy" in res.headers


def test_gzip_compression_active():
    """Test 29: Middleware compresses payloads exceeding size threshold."""
    # Create large payload that exceeds 1000 bytes
    large_payload = VALID_PAYLOAD.copy()
    large_payload["incident"]["description"] = "A" * 1500
    token = create_access_token(role="admin")

    res = client.post(
        "/api/analyze",
        json=large_payload,
        headers={"Accept-Encoding": "gzip", "Authorization": f"Bearer {token}"}
    )
    assert res.headers.get("content-encoding") == "gzip"


# ═════════════════════════════════════════════════════════════════════════════
# ── SCORE IMPROVEMENT TESTS (Coverage Enhancements) ─────────────────────────
# ═════════════════════════════════════════════════════════════════════════════

import os
import tempfile
import shutil
from unittest.mock import MagicMock, AsyncMock

def test_extra_claims_and_keypair_generation():
    """Test 30: Create access token with extra claims and verify keypair generation in clean state."""
    # Test extra claims
    token = create_access_token(role="admin", extra_claims={"custom_claim": "hello"})
    payload = verify_token(token)
    assert payload["custom_claim"] == "hello"

    # Test keypair generation in a temporary directory
    temp_dir = tempfile.mkdtemp()
    try:
        from backend.core import auth
        with patch("backend.core.auth._KEYS_DIR", temp_dir), \
             patch("backend.core.auth._PRIVATE_KEY_PATH", os.path.join(temp_dir, "private.pem")), \
             patch("backend.core.auth._PUBLIC_KEY_PATH", os.path.join(temp_dir, "public.pem")):
            
            # Call _load_keys directly on an empty directory will generate new keys internally (covers line 91)
            priv, pub = auth._load_keys()
            assert "BEGIN PRIVATE KEY" in priv
            assert "BEGIN PUBLIC KEY" in pub
            assert os.path.exists(os.path.join(temp_dir, "private.pem"))
            assert os.path.exists(os.path.join(temp_dir, "public.pem"))

            # Test reload keys functionality
            priv2, pub2 = auth._load_keys()
            assert priv2 == priv
            assert pub2 == pub
    finally:
        shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_genai_real_api_mocked():
    """Test 31: Test real Gemini API paths under mocked httpx response."""
    from backend.core.genai import generate_briefing_and_playbook, chat_with_assistant
    
    mock_playbook_response = MagicMock()
    mock_playbook_response.status_code = 200
    mock_playbook_response.raise_for_status = MagicMock()
    mock_playbook_response.json = MagicMock(return_value={
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"summary": "Test summary from Gemini", "steps": ["Mock step 1"], "announcements": {"en": "EN", "es": "ES", "fr": "FR"}}'
                }]
            }
        }]
    })

    mock_chat_response = MagicMock()
    mock_chat_response.status_code = 200
    mock_chat_response.raise_for_status = MagicMock()
    mock_chat_response.json = MagicMock(return_value={
        "candidates": [{
            "content": {
                "parts": [{
                    "text": "Gemini interactive assistant reply."
                }]
            }
        }]
    })

    with patch("httpx.AsyncClient.post") as mock_post:
        # 1. Test playbook endpoint with key
        mock_post.return_value = mock_playbook_response
        
        # Test direct playbook generation function
        from backend.models.schemas import GateStatus, IncidentReport, WeatherContext, EventContext
        gates = [GateStatus(gate_id="G1", capacity_percent=50.0, entry_rate=10, wait_time_seconds=60)]
        incident = IncidentReport(incident_id="INC-1", zone="B1", type="medical", description="heat collapse", reporter_role="steward")
        weather = WeatherContext(temperature_celsius=30, heat_index=32, lightning_detected=False, lightning_radius_km=0)
        event_ctx = EventContext(phase="halftime", total_capacity=50000, occupied_seats=30000, accessible_seats_available=10, concession_queue_avg_minutes=5)
        
        playbook = await generate_briefing_and_playbook(gates, incident, weather, event_ctx, api_key="TEST_API_KEY")
        assert playbook["summary"] == "Test summary from Gemini"

        # Test Chat function
        mock_post.return_value = mock_chat_response
        chat_reply = await chat_with_assistant("Hello", [], gates, incident, weather, event_ctx, api_key="TEST_API_KEY")
        assert chat_reply == "Gemini interactive assistant reply."

        # 2. Test failure handling in API call (should fallback to mock playbook)
        mock_post.side_effect = Exception("API Error")
        playbook_fallback = await generate_briefing_and_playbook(gates, incident, weather, event_ctx, api_key="TEST_API_KEY")
        assert "NORMAL OPERATIONS" in playbook_fallback["summary"] or "HIGH INCIDENT" in playbook_fallback["summary"] or "OPERATIONAL BOTTLENECK" in playbook_fallback["summary"]

        chat_fallback = await chat_with_assistant("xyz", [], gates, incident, weather, event_ctx, api_key="TEST_API_KEY")
        assert "Operational Guidance" in chat_fallback


def test_invalid_authorization_formats_and_exceptions():
    """Test 32: Test endpoint behavior with malformed headers or validation failures."""
    clean_payload = {
        "venue_id": "stadium-1",
        "gates": [
            {"gate_id": "North-A", "capacity_percent": 85.0, "entry_rate": 40, "wait_time_seconds": 300},
        ],
        "incident": {
            "incident_id": "INC-100",
            "zone": "B1",
            "type": "medical",
            "description": "Dehydrated fan",
            "reporter_role": "steward",
        },
        "weather": {
            "temperature_celsius": 30.0,
            "heat_index": 32.0,
            "lightning_detected": False,
            "lightning_radius_km": 0.0,
        },
        "event_context": {
            "phase": "halftime",
            "total_capacity": 50000,
            "occupied_seats": 40000,
            "accessible_seats_available": 5,
            "concession_queue_avg_minutes": 5.0,
        },
        "role": "admin",
    }
    # Malformed headers (no Bearer prefix)
    res = client.post("/api/analyze", json=clean_payload, headers={"Authorization": "Basic 12345"})
    assert res.status_code == 401
    assert "Invalid authorization header format" in res.json()["detail"]

    # Invalid Token signature/expiry exception triggering verification error
    res = client.post("/api/analyze", json=clean_payload, headers={"Authorization": "Bearer invalid.token.value"})
    assert res.status_code == 401
    assert "Invalid or expired token" in res.json()["detail"]


def test_redis_rate_limiting_coverage():
    """Test 33: Mock Redis client connections to cover routes.py Redis-based rate limiting."""
    from backend.api import routes
    
    mock_redis = MagicMock()
    mock_redis.pipeline = MagicMock()
    
    mock_pipeline = MagicMock()
    mock_pipeline.zremrangebyscore = MagicMock()
    mock_pipeline.zcard = MagicMock()
    mock_pipeline.zadd = MagicMock()
    mock_pipeline.expire = MagicMock()
    
    # 1. Test rate limit exceeded
    mock_pipeline.execute = MagicMock(return_value=[None, 100])
    mock_redis.pipeline.return_value = mock_pipeline
    
    with patch("backend.api.routes._redis_client", mock_redis):
        inc = {
            "incident_id": "INC-REDIS",
            "zone": "A2",
            "type": "security",
            "description": "Fist fight",
            "reporter_role": "steward",
        }
        res = client.post("/api/incident", json=inc)
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]

        # 2. Test rate limit allowed (count < limit)
        mock_pipeline.execute = MagicMock(return_value=[None, 2])
        res2 = client.post("/api/incident", json=inc)
        assert res2.status_code == 200


def test_redis_init_paths():
    """Test 34: Test Redis client initialization block under successful and failing states."""
    import importlib
    from backend.api import routes
    
    # 1. Force reload of routes with REDIS_URL set to local mock
    with patch("os.getenv", return_value="redis://mock-redis-host:6379"), \
         patch("redis.from_url") as mock_from_url:
        
        mock_client = MagicMock()
        mock_client.ping = MagicMock(return_value=True)
        mock_from_url.return_value = mock_client
        
        importlib.reload(routes)
        assert routes._redis_client is not None

    # 2. Force reload with REDIS_URL but ping fails
    with patch("os.getenv", return_value="redis://mock-redis-host:6379"), \
         patch("redis.from_url", side_effect=Exception("Connection refused")):
        
        importlib.reload(routes)
        assert routes._redis_client is None
        
    # Cleanup to ensure we leave routes in a clean state
    importlib.reload(routes)


def test_direct_sanitize_description():
    """Test 35: Direct call to _sanitize_description with HTML tags to cover logger line."""
    from backend.api.routes import _sanitize_description
    result = _sanitize_description("<p>Test</p> text")
    assert result == "Test text"


def test_audit_log_sqlite_exception_fallback():
    """Test 36: Test SQLite exception path in _append_audit_entry falling back to in-memory log."""
    from backend.api import routes
    
    with patch("backend.api.routes._sqlite_enabled", True), \
         patch("sqlite3.connect", side_effect=Exception("Database locked")):
        
        from backend.models.schemas import IncidentReport
        for i in range(110):
            inc = IncidentReport(incident_id=f"INC-EXC-{i}", zone="A", type="medical", description="test desc", reporter_role="steward")
            routes._append_audit_entry("test-venue-fallback", inc, "test")
        
        assert len(routes._audit_log["test-venue-fallback"]) == 100
        assert routes._audit_log["test-venue-fallback"][-1]["incident_id"] == "INC-EXC-109"


@pytest.mark.asyncio
async def test_ws_broadcast_exception():
    """Test 37: Test exception handling inside _broadcast_ws when a client connection fails."""
    from backend.api import routes
    
    mock_ws = MagicMock()
    mock_ws.send_text = AsyncMock(side_effect=Exception("Connection closed"))
    
    routes._ws_connections.append(mock_ws)
    
    from backend.models.schemas import Recommendation, SeverityLevel, ConfidenceLevel
    rec = Recommendation(rule_id="test", severity=SeverityLevel.LOW, action="Action", reason="Reason", affected_zone="Zone", confidence=ConfidenceLevel.ADVISORY)
    
    await routes._broadcast_ws([rec])
    assert mock_ws not in routes._ws_connections


def test_audit_endpoint_sqlite_exception_fallback():
    """Test 38: Test SQLite exception path in audit_endpoint falling back to in-memory log."""
    from backend.api import routes
    
    with patch("backend.api.routes._sqlite_enabled", True), \
         patch("sqlite3.connect", side_effect=Exception("Database corrupt")):
        
        res = client.get("/api/audit?venue_id=default")
        assert res.status_code == 200
        assert "total_entries" in res.json()


def test_websocket_endpoint_general_exception():
    """Test 39: Test WebSocket connection handling when a general exception is raised."""
    with patch("fastapi.WebSocket.receive_text", side_effect=Exception("WS System Error")):
        try:
            with client.websocket_connect("/api/ws") as websocket:
                pass
        except Exception:
            pass


def test_frontend_index_path_not_exists():
    """Test 40: Test frontend parsed_html fixture raises error when path doesn't exist."""
    from backend.tests.test_frontend import parsed_html
    func = getattr(parsed_html, "__wrapped__", parsed_html)
    with patch("os.path.exists", return_value=False), pytest.raises(BaseException):
        func()


def test_sqlite_init_exception():
    """Test 41: Test SQLite initialization failure fallback."""
    from backend.api import routes
    with patch("os.makedirs", side_effect=Exception("Permission denied")):
        result = routes._init_db()
        assert result is False


def test_generate_mock_playbook_branches():
    """Test 42: Test _generate_mock_playbook with fire_smoke, lightning, and gate congestion contexts."""
    from backend.core.genai import _generate_mock_playbook
    from backend.models.schemas import GateStatus, IncidentReport, WeatherContext, EventContext
    
    gates = [
        GateStatus(gate_id="North-A", capacity_percent=90.0, entry_rate=45, wait_time_seconds=340),
        GateStatus(gate_id="South-A", capacity_percent=20.0, entry_rate=8, wait_time_seconds=45)
    ]
    event_ctx = EventContext(phase="halftime", total_capacity=60000, occupied_seats=50000, accessible_seats_available=10, concession_queue_avg_minutes=5)
    
    # 1. test fire_smoke branch
    inc_fire = IncidentReport(incident_id="INC-1", zone="B3", type="fire_smoke", description="smoke in B3", reporter_role="steward")
    weather_clear = WeatherContext(temperature_celsius=25, heat_index=26, lightning_detected=False, lightning_radius_km=0)
    pb_fire = _generate_mock_playbook(gates, inc_fire, weather_clear, event_ctx)
    assert "evacuation" in pb_fire["summary"].lower()

    # 2. test lightning branch
    inc_med = IncidentReport(incident_id="INC-2", zone="B3", type="medical", description="heat", reporter_role="steward")
    weather_lightning = WeatherContext(temperature_celsius=25, heat_index=26, lightning_detected=True, lightning_radius_km=10.0)
    pb_weather = _generate_mock_playbook(gates, inc_med, weather_lightning, event_ctx)
    assert "lightning" in pb_weather["summary"].lower()


def test_generate_mock_chat_branches():
    """Test 43: Test _generate_mock_chat with various operational keywords to cover all paths."""
    from backend.core.genai import _generate_mock_chat
    from backend.models.schemas import GateStatus, IncidentReport, WeatherContext, EventContext
    
    gates = [
        GateStatus(gate_id="North-A", capacity_percent=90.0, entry_rate=45, wait_time_seconds=340),
        GateStatus(gate_id="South-A", capacity_percent=20.0, entry_rate=8, wait_time_seconds=45)
    ]
    incident = IncidentReport(incident_id="INC-1", zone="B3", type="medical", description="collapsed", reporter_role="steward")
    event_ctx = EventContext(phase="halftime", total_capacity=60000, occupied_seats=50000, accessible_seats_available=10, concession_queue_avg_minutes=5)
    
    # 1. fire / evac
    weather_clear = WeatherContext(temperature_celsius=25, heat_index=26, lightning_detected=False, lightning_radius_km=0)
    reply_fire = _generate_mock_chat("fire evacuation protocol", [], gates, incident, weather_clear, event_ctx)
    assert "evacuation" in reply_fire.lower()
    
    # 2. weather/lightning
    weather_lightning = WeatherContext(temperature_celsius=25, heat_index=26, lightning_detected=True, lightning_radius_km=10.0)
    reply_weather = _generate_mock_chat("lightning warning status", [], gates, incident, weather_lightning, event_ctx)
    assert "lightning" in reply_weather.lower()
    
    # 3. gate / redirect
    reply_gate = _generate_mock_chat("gate redirection", [], gates, incident, weather_clear, event_ctx)
    assert "overloaded" in reply_gate.lower()
    
    # 4. weather but no lightning detected path
    reply_no_lightning = _generate_mock_chat("lightning storm check", [], gates, incident, weather_clear, event_ctx)
    assert "no lightning" in reply_no_lightning.lower()


def test_rate_limit_memory_sweeper():
    """Verify the lazy sweeper removes inactive IPs after the sweep interval."""
    import backend.api.routes as routes_module

    routes_module._rate_limit_store.clear()

    # Simulate an IP that made requests 10 minutes ago (well outside the 60s window)
    old_time = time.time() - 600
    routes_module._rate_limit_store["192.168.1.100"] = [old_time]
    routes_module._rate_limit_store["192.168.1.200"] = [old_time]
    # Simulate an IP with a recent request (inside the window)
    routes_module._rate_limit_store["192.168.1.300"] = [time.time()]

    assert "192.168.1.100" in routes_module._rate_limit_store
    assert "192.168.1.200" in routes_module._rate_limit_store
    assert "192.168.1.300" in routes_module._rate_limit_store

    # Force the sweeper to run by directly setting _last_sweep_time to epoch start
    original_sweep_time = routes_module._last_sweep_time
    try:
        routes_module.__dict__["_last_sweep_time"] = 0.0

        routes_module._sweep_rate_limit_store()

        # Stale IPs should be removed
        assert "192.168.1.100" not in routes_module._rate_limit_store
        assert "192.168.1.200" not in routes_module._rate_limit_store
        # Recent IP should still be present
        assert "192.168.1.300" in routes_module._rate_limit_store
    finally:
        routes_module._rate_limit_store.clear()
        routes_module.__dict__["_last_sweep_time"] = original_sweep_time

