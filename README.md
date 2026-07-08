# StadiumOps AI

[![CI](https://github.com/logeshn554/Smart-Stadiums-Tournament-Operations/actions/workflows/ci.yml/badge.svg)](https://github.com/logeshn554/Smart-Stadiums-Tournament-Operations/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)](https://github.com/logeshn554/Smart-Stadiums-Tournament-Operations)
[![Security: bandit](https://img.shields.io/badge/security-bandit%20clean-brightgreen)](https://github.com/PyCQA/bandit)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000)](https://github.com/astral-sh/ruff)

**Intelligent decision-support assistant for stadium control room staff during live sporting events.**

---

## Chosen Vertical — Smart Stadiums and Tournament Operations

This project targets the **Smart Stadiums and Tournament Operations** vertical. Modern stadiums host tens of thousands of spectators in high-density, time-pressured environments where medical emergencies, crowd surges, severe weather, and security incidents can escalate within minutes. Tournament-scale events compound complexity: multiple matches, overlapping egress waves, and dynamic weather all demand real-time, coordinated responses from gate managers, security leads, medical teams, and venue administrators.

StadiumOps AI provides a **unified operational intelligence layer** that reads live context signals (gate loads, incidents, weather, event phase) and produces ranked, explainable action recommendations — not for fans, but for the professionals running the control room.

---

## Problem Being Solved

Control room staff currently rely on radio chatter, CCTV feeds, and individual judgement to coordinate responses across dozens of zones simultaneously. This creates three critical failure modes:

1. **Information overload** — Too many signals, too few seconds to prioritise.
2. **Inconsistent triage** — Response severity depends on who answers the radio first.
3. **Invisible blind spots** — Accessibility needs, weather thresholds, and gate imbalances go unnoticed until they become crises.

StadiumOps AI solves this by providing a **deterministic, rule-based decision engine** that:
- Processes all context signals simultaneously.
- Produces ranked, severity-coded recommendations with full explanations.
- Ensures accessibility-first routing and weather safety are never overlooked.
- Operates transparently — every recommendation traces back to a named rule and a stated reason.

---

## Approach and Logic

### Why Rules, Not ML

For an operationally critical context where lives may depend on recommendations, **explainability is non-negotiable**. A rule-based engine ensures:

- **Auditability**: Every output traces to a named rule with a human-readable reason.
- **Predictability**: Identical inputs always produce identical outputs.
- **Zero cold-start**: No training data, no model drift, no GPU requirements.
- **Regulatory compliance**: Stadium safety regulations require justifiable decisions.

Machine learning may complement this system in future (e.g., predictive crowd flow), but the core triage layer must remain deterministic and transparent.

### The Five Decision Rules

| Rule | Function | Trigger | Severity |
|------|----------|---------|----------|
| **Gate Load Balancing** | `gate_load_balance()` | One gate >80% AND another <40% capacity | High |
| **Incident Triage** | `triage_incident()` | Any incident report submitted | Critical–Low |
| **Weather Action** | `weather_action()` | Lightning ≤15 km or heat index ≥40 °C | Critical–High |
| **Accessibility Routing** | `accessibility_routing()` | Fire/overcrowding + accessible seats, or zero accessible seats | Critical–High |
| **Egress Plan** | `egress_plan()` | Post-match or overtime phase | High–Low |

All rules are **pure, stateless functions** — they accept typed inputs and return `Recommendation` objects. The engine has zero knowledge of HTTP, FastAPI, or any web framework.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                │
│  index.html + style.css + app.js                                │
│  (Vanilla HTML/CSS/JS — no build tools)                         │
│  • Client-side form validation with aria-describedby            │
│  • Debounced submission (300ms)                                 │
│  • Diff-based rendering (skip re-render if unchanged)           │
│  • WebSocket listener for real-time push                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP POST /api/analyze
                         │ WS /api/ws (real-time push)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API LAYER                                │
│  FastAPI (routes.py + main.py)                                  │
│  • RS256 JWT authentication (python-jose + cryptography)        │
│  • Input validation (Pydantic)                                  │
│  • Role-based access control (JWT claim or payload field)       │
│  • Dual-backend rate limiting (in-memory / Redis via slowapi)   │
│  • HTML sanitisation (dual-layer)                               │
│  • CORS + Security headers (HSTS, CSP, XSS, etc.)              │
│  • Incident audit log (bounded, per-venue)                      │
│  • WebSocket broadcast to connected clients                     │
│  • Multi-venue isolation via venue_id                           │
└────────────────────────┬────────────────────────────────────────┘
                         │ function calls
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION ENGINE                              │
│  core/decision_engine.py                                        │
│  • gate_load_balance() — capped to top-4 most impactful pairs   │
│  • triage_incident()                                            │
│  • weather_action()                                             │
│  • accessibility_routing()                                      │
│  • egress_plan()                                                │
└────────────────────────┬────────────────────────────────────────┘
                         │ typed models
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SCHEMAS                                   │
│  models/schemas.py                                              │
│  • GateStatus, IncidentReport, WeatherContext, EventContext      │
│  • Recommendation, AnalyzeRequest (with venue_id), AnalyzeResponse│
│  • Field validators (HTML strip, range checks, enums)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions CI (lint + test + coverage)
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app, CORS, security headers, HSTS
│   │   └── routes.py            # API endpoints, JWT auth, Redis rate limiting
│   ├── core/
│   │   ├── auth.py              # RS256 JWT module (python-jose + cryptography)
│   │   └── decision_engine.py   # Five stateless decision rules (capped output)
│   ├── models/
│   │   └── schemas.py           # Pydantic input/output models (with venue_id)
│   └── tests/
│       ├── test_engine.py       # Unit tests for all decision rules (32 tests)
│       ├── test_api.py          # Integration + JWT auth tests (29 tests)
│       └── test_frontend.py     # Frontend structure + accessibility tests (22 tests)
├── frontend/
│   ├── index.html               # Dashboard HTML with full ARIA support
│   ├── style.css                # Dark-theme CSS with reduced-motion + high-contrast
│   └── app.js                   # Vanilla JS — debounced, validated, diff-rendered
├── data/
│   ├── seed.json                # Pre-generated simulation payload
│   ├── simulate.py              # Single-venue mock data simulator
│   └── simulate_tournament.py   # Multi-venue tournament operations simulator
├── .env.example                 # Environment variable placeholders
├── .gitignore                   # Python/Node/build/keys exclusions
├── docker-compose.yml           # Redis + API services for production
├── Dockerfile                   # Container image for the backend
├── locustfile.py                # Load test definition (Locust)
├── pyproject.toml               # Ruff, pytest, bandit, coverage configuration
├── requirements.txt             # Pinned Python dependencies
└── README.md                    # This file
```

---

## How to Run

### Prerequisites

- **Python 3.11+**
- **pip** (Python package manager)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for local development)
```

### Start the Backend

```bash
uvicorn backend.api.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

### Run the Simulator

```bash
# Single-venue simulation
python data/simulate.py

# Multi-venue tournament simulation (3 concurrent matches)
python data/simulate_tournament.py
```

### Run Tests with Coverage

```bash
pytest backend/tests/ -v --cov=backend --cov-report=term-missing
```

### Docker Deployment (with Redis)

```bash
docker compose up --build
```

This starts both the API and Redis for distributed rate limiting.

### Open the Frontend

Open `frontend/index.html` directly in a web browser. The dashboard will communicate with the backend API at `http://127.0.0.1:8000`.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze` | Full analysis with all five decision-engine rules |
| `POST` | `/api/incident` | Single-incident triage (rate-limited, 10 req/min per IP) |
| `GET`  | `/api/health` | Service health check and version |
| `GET`  | `/api/audit?venue_id=default` | Incident audit log (per-venue, bounded) |
| `WS`   | `/api/ws` | WebSocket for real-time recommendation push |

### Authentication

StadiumOps AI supports **RS256 JWT authentication** using asymmetric key pairs:

```bash
# Generate a token (for testing)
python -c "from backend.core.auth import create_access_token; print(create_access_token('admin'))"

# Use it in a request
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d @data/seed.json
```

- **RS256 asymmetric signing**: Private key signs tokens; API verifies with public key only.
- **Self-signed key pair** auto-generated on first run (stored in `keys/`).
- **Token claims**: `sub`, `role`, `iat`, `exp` (default 60-minute expiry).
- **Backward compatible**: Falls back to the `role` field in the payload when no JWT is provided.

---

## Multi-Venue Tournament Support

StadiumOps AI supports **multi-venue tournament operations** via the `venue_id` field and a dedicated tournament simulator:

```bash
python data/simulate_tournament.py
```

This simulates **Quarter-Finals Day** across three stadiums:
- **Northern Arena** (65,000 cap) — Post-match egress with crowd surge
- **Southern Stadium** (48,000 cap) — Halftime medical + approaching lightning
- **Eastern Complex** (55,000 cap) — Overtime with fire/smoke + close lightning

The simulator produces a **cross-venue operations summary** with:
- Aggregate recommendation statistics across all venues
- Weather alert coordination across multiple stadiums
- Overlapping egress wave warnings for transit hub management
- Per-venue audit log verification

---

## Real-Time Push via WebSocket

Clients can connect to `ws://127.0.0.1:8000/api/ws` to receive **real-time recommendation updates**:

```json
{
  "type": "recommendations_update",
  "timestamp": "2026-07-08T04:30:00Z",
  "recommendations": [...]
}
```

---

## Security Measures Implemented

| Measure | Implementation |
|---------|---------------|
| **RS256 JWT authentication** | Asymmetric key signing via `python-jose` + `cryptography`. Self-signed RSA-2048 key pair auto-generated. |
| **Input validation** | All inputs validated via Pydantic models with type, range, and length constraints |
| **HTML sanitisation** | Dual-layer: Pydantic `@field_validator` + route-level `_sanitize_description()` (defense-in-depth) |
| **Role-based access control** | JWT `role` claim (preferred) or payload field. Viewers cannot submit Critical incidents. |
| **Dual-backend rate limiting** | In-memory sliding window (default) or Redis-backed sorted sets (auto-detected via `REDIS_URL`) |
| **CORS restriction** | Only configured origins allowed; defaults to localhost in development |
| **Security headers** | X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy |
| **HSTS** | Strict-Transport-Security with max-age=31536000 and includeSubDomains |
| **Content Security Policy** | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` (justified) |
| **No hardcoded secrets** | All configuration loaded from `.env`; `.env.example` contains placeholders only |
| **Gitignore** | `.env`, `keys/`, `__pycache__`, and build artifacts excluded from version control |
| **Frontend XSS prevention** | `escapeHtml()` function + `textContent` DOM construction (no innerHTML for user content) |
| **Linting** | Ruff configured with security rules (flake8-bandit) via `pyproject.toml` |

### Bandit Security Audit

```
$ bandit -r backend/ -c pyproject.toml
Run started:2026-07-08

Test results:
    No issues identified.

Code scanned:
    Total lines of code: 1164
    Total lines skipped (#nosec): 0

Run metrics:
    Total issues (by severity):
        Undefined: 0  Low: 0  Medium: 0  High: 0
    Total issues (by confidence):
        Undefined: 0  Low: 0  Medium: 0  High: 0
```

### Rate Limiter Design Note

The in-memory sliding-window rate limiter is the **default** for single-process deployments typical of stadium control rooms. When `REDIS_URL` is set (e.g., via `docker-compose.yml`), the system automatically switches to **Redis-backed sorted-set counters** for distributed rate limiting across horizontally scaled instances — no API contract changes needed.

---

## Accessibility Features Implemented

### ARIA Attributes

| Element | Attribute | Purpose |
|---------|-----------|---------|
| Recommendations panel | `role="region"` `aria-label="Live Recommendations"` | Screen readers announce the panel |
| Critical/High cards | `role="alert"` | Screen readers immediately announce urgent recommendations |
| Reason toggle buttons | `aria-expanded` `aria-controls` | Indicate expandable content state |
| Loading overlay | `aria-hidden` | Prevent screen readers from reading background content |
| Loading spinner | `role="status"` `aria-label="Loading recommendations"` | Screen readers announce loading state |
| Toast container | `aria-live="polite"` | Announce notifications without interrupting |
| Form inputs | `aria-describedby` | Link inputs to validation error messages |
| Decorative emojis | `aria-hidden="true"` | Hide decorative icons from screen readers |
| Severity badges | `aria-label` | Provide text alternative for severity indicators |

### Visual Accessibility

- **Triple-channel severity indicators**: colour + text badge + text label (never colour alone)
- **WCAG AA colour contrast**: All severity colours verified against their backgrounds
- **Keyboard navigation**: All interactive elements keyboard-navigable with `:focus-visible` styles
- **Semantic HTML**: `<header>`, `<main>`, `<aside>`, `<section>`, `<fieldset>`, `<legend>`, `<article>`
- **Skip navigation**: Skip-to-content link for keyboard users
- **`prefers-reduced-motion: reduce`**: All animations disabled for vestibular disorders
- **`prefers-contrast: more`**: High-contrast colour scheme for low vision

---

## Test Coverage Summary

**98 tests | 88% coverage | 0 bandit issues**

### Unit Tests (`test_engine.py`) — 32 tests

| Test | Rule | What It Validates |
|------|------|-------------------|
| `test_happy_path_overloaded_and_underloaded` | Gate Load Balance | High recommendation when imbalance exists |
| `test_edge_case_exactly_80_percent` | Gate Load Balance | 80% boundary is NOT overloaded |
| `test_edge_case_exactly_40_percent` | Gate Load Balance | 40% boundary is NOT underloaded |
| `test_no_trigger_all_balanced` | Gate Load Balance | Balanced gates produce empty list |
| `test_empty_gate_list` | Gate Load Balance | Empty input produces empty output |
| `test_adversarial_capacity_over_100` | Gate Load Balance | Pydantic rejects >100% capacity |
| `test_multiple_pairs` | Gate Load Balance | Multiple overloaded/underloaded pairs |
| `test_happy_path_known_types` (×5) | Incident Triage | Each type maps to correct severity |
| `test_unknown_type_returns_low` | Incident Triage | Unknown type → Low severity |
| `test_html_stripped_from_description` | Incident Triage | HTML tags removed before processing |
| `test_reason_contains_zone_and_role` | Incident Triage | Reason includes reporter context |
| `test_lightning_close_range` | Weather Action | ≤15 km lightning → Critical |
| `test_lightning_far_range` | Weather Action | >15 km lightning → High |
| `test_edge_case_lightning_exactly_15_km` | Weather Action | 15 km boundary → Critical |
| `test_heat_index_above_40` | Weather Action | Heat ≥40 → High hydration alert |
| `test_edge_case_heat_index_exactly_40` | Weather Action | 40 °C boundary triggers |
| `test_both_lightning_and_heat` | Weather Action | Multiple simultaneous triggers |
| `test_no_trigger_mild_weather` | Weather Action | Mild conditions → empty list |
| `test_no_lightning_detected` | Weather Action | No detection → no trigger |
| `test_fire_smoke_with_available_seats` | Accessibility | Fire + seats → Critical dispatch |
| `test_zero_accessible_seats_any_incident` | Accessibility | Zero seats → High monitoring |
| `test_high_occupancy_post_match` | Egress Plan | ≥90% → High 3-wave exit |
| `test_adversarial_negative_wait_time` | Egress Plan | Pydantic rejects negative wait |
| `test_adversarial_zero_total_capacity` | Egress Plan | Pydantic rejects zero capacity |

### Integration + Auth Tests (`test_api.py`) — 29 tests

| Test | Category | What It Validates |
|------|----------|-------------------|
| `test_valid_payload_returns_recommendations` | Analyze | 200, ≥1 result, severity ordering |
| `test_viewer_cannot_submit_fire_smoke` | RBAC | 403 for viewer + fire_smoke |
| `test_valid_jwt_admin_succeeds` | JWT Auth | Admin JWT overrides payload role |
| `test_valid_jwt_viewer_blocked_for_fire_smoke` | JWT Auth | Viewer JWT blocks fire_smoke |
| `test_invalid_jwt_returns_401` | JWT Auth | Malformed JWT → 401 |
| `test_expired_jwt_returns_401` | JWT Auth | Expired JWT → 401 |
| `test_no_jwt_falls_back_to_role_field` | JWT Auth | Backward-compatible fallback |
| `test_rate_limit_exceeded_returns_429` | Rate Limit | 11th request → 429 |
| `test_security_headers_present` | Security | All 5 security headers |
| `test_hsts_header_present` | Security | HSTS with max-age |
| `test_websocket_connects` | WebSocket | Connection + ping/pong |
| `test_audit_log_records_analyze` | Audit | Records from /analyze |

### Frontend Tests (`test_frontend.py`) — 22 tests

| Test | Category | What It Validates |
|------|----------|-------------------|
| `test_lang_attribute_present` | HTML | `lang="en"` on html element |
| `test_skip_nav_link_present` | HTML | Skip-to-content link exists |
| `test_all_inputs_have_labels` | HTML | Every input has a label |
| `test_prefers_reduced_motion` | CSS | Motion disability support |
| `test_prefers_contrast` | CSS | High contrast mode |
| `test_strict_mode` | JS | "use strict" |
| `test_escape_html_defined` | JS | XSS prevention function |
| `test_iife_encapsulation` | JS | No global pollution |

### Coverage Report

```
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
backend\__init__.py                   1      0   100%
backend\api\__init__.py               1      0   100%
backend\api\main.py                  25      0   100%
backend\api\routes.py               151     35    77%
backend\core\__init__.py              1      0   100%
backend\core\auth.py                 50      7    86%
backend\core\decision_engine.py      70      1    99%
backend\models\__init__.py            1      0   100%
backend\models\schemas.py            91      3    97%
---------------------------------------------------------------
TOTAL                               391     46    88%
```

---

## Load Testing

A Locust load test file is included for p95 latency validation:

```bash
pip install locust
locust -f locustfile.py --headless -u 50 -r 10 --run-time 60s \
       --host http://127.0.0.1:8000 --csv results/load_test
```

Traffic profile simulates realistic control room usage:
- 60% full analysis requests (`/api/analyze`)
- 25% single-incident triage (`/api/incident`)
- 10% health checks (`/api/health`)
- 5% audit log queries (`/api/audit`)

---

## IoT and Sensor Integration Path

| Data Source | Integration Point | Notes |
|------------|-------------------|-------|
| **Turnstile counters** | `GateStatus.entry_rate`, `capacity_percent` | Push gate data via POST `/api/analyze` |
| **Weather stations** | `WeatherContext` fields | Venue weather API or OpenWeatherMap |
| **CCTV crowd analytics** | `EventContext.occupied_seats` | Computer vision pipeline output |
| **PA system** | Consume `Recommendation.action` | Auto-announce Critical/High actions |
| **BMS (Building Management)** | `WeatherContext.heat_index` | HVAC and environmental sensors |

---

## Assumptions Made

1. **Weather data is simulated** — not sourced from a live weather API. In production, this would integrate with services like OpenWeatherMap or a venue-specific weather station.
2. **JWT keys are self-signed** — production deployments would use an identity provider (e.g., Auth0, Keycloak) with managed key rotation.
3. **Gate and sensor data is generated** — the simulator creates realistic but synthetic data. Real deployments would ingest data from IoT sensors, turnstile counters, and CCTV analytics.
4. **Audit log is in-memory** — production systems should persist to a database. The bounded ring buffer prevents memory exhaustion.

---

## License

Built for the Smart Stadiums hackathon challenge. All code written from scratch.
