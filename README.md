# StadiumOps AI

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
│  • Input validation (Pydantic)                                  │
│  • Role-based access control                                    │
│  • Rate limiting (in-memory sliding window)                     │
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
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app, CORS, security headers, HSTS
│   │   └── routes.py            # API endpoints, audit log, WebSocket, rate limiting
│   ├── core/
│   │   └── decision_engine.py   # Five stateless decision rules (capped output)
│   ├── models/
│   │   └── schemas.py           # Pydantic input/output models (with venue_id)
│   └── tests/
│       ├── test_engine.py       # Unit tests for all decision rules (32 tests)
│       ├── test_api.py          # Integration tests for API + WebSocket + audit (24 tests)
│       └── test_frontend.py     # Frontend structure + accessibility tests (22 tests)
├── frontend/
│   ├── index.html               # Dashboard HTML with full ARIA support
│   ├── style.css                # Dark-theme CSS with reduced-motion + high-contrast
│   └── app.js                   # Vanilla JS — debounced, validated, diff-rendered
├── data/
│   ├── seed.json                # Pre-generated simulation payload
│   └── simulate.py              # Mock data simulator script
├── .env.example                 # Environment variable placeholders
├── .gitignore                   # Python/Node/build exclusions
├── pyproject.toml               # Ruff linting + pytest configuration
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
python data/simulate.py
```

This generates a realistic event snapshot, sends it to the API, and prints ranked recommendations to the terminal.

### Run Tests

```bash
pytest backend/tests/ -v
```

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

---

## Multi-Venue Tournament Support

StadiumOps AI supports **multi-venue tournament operations** via the `venue_id` field in the `/api/analyze` payload. Each venue maintains its own isolated audit log, enabling:

- **Per-venue incident history**: Query `/api/audit?venue_id=stadium-west` for venue-specific logs.
- **Cross-venue analysis**: Tournament operators can compare incident patterns across venues.
- **Default venue**: If `venue_id` is omitted, the system uses `"default"`.

---

## Real-Time Push via WebSocket

Clients can connect to `ws://127.0.0.1:8000/api/ws` to receive **real-time recommendation updates** whenever an analyze or incident request is processed. The server pushes the full recommendation list as a JSON payload:

```json
{
  "type": "recommendations_update",
  "timestamp": "2026-07-08T04:30:00Z",
  "recommendations": [...]
}
```

This enables:
- **Dashboard auto-update** without polling.
- **Multi-screen control rooms** where several displays show live recommendations.
- **Alert forwarding** to mobile devices or downstream systems.

---

## Incident Audit Log

Every incident processed through `/api/analyze` or `/api/incident` is recorded in a **bounded in-memory audit log** (max 100 entries per venue). Query via:

```bash
curl http://127.0.0.1:8000/api/audit?venue_id=default
```

The audit log supports:
- **Post-event review**: What incidents occurred, when, and from which endpoint.
- **Compliance reporting**: Full traceability of all incident submissions.
- **Operational auditing**: Track reporter roles and incident types over time.

> **Production note**: For persistent storage, replace the in-memory log with a database backend (e.g., PostgreSQL, MongoDB). The `_append_audit_entry()` function is the single integration point.

---

## IoT and Sensor Integration Path

While this hackathon version uses simulated data, StadiumOps AI is designed for straightforward IoT integration:

| Data Source | Integration Point | Notes |
|------------|-------------------|-------|
| **Turnstile counters** | `GateStatus.entry_rate`, `capacity_percent` | Push gate data via POST `/api/analyze` |
| **Weather stations** | `WeatherContext` fields | Venue weather API or OpenWeatherMap |
| **CCTV crowd analytics** | `EventContext.occupied_seats` | Computer vision pipeline output |
| **PA system** | Consume `Recommendation.action` | Auto-announce Critical/High actions |
| **BMS (Building Management)** | `WeatherContext.heat_index` | HVAC and environmental sensors |

The API's Pydantic schemas validate all incoming sensor data, ensuring malformed readings are rejected before reaching the decision engine.

---

## Assumptions Made

1. **Weather data is simulated** — not sourced from a live weather API. In production, this would integrate with services like OpenWeatherMap or a venue-specific weather station.
2. **Authentication/roles are mocked** — the `role` field in the payload acts as a simple authorization gate. A production system would use JWT tokens or OAuth 2.0 with scoped permissions per venue.
3. **Gate and sensor data is generated** — the simulator creates realistic but synthetic data. Real deployments would ingest data from IoT sensors, turnstile counters, and CCTV analytics.
4. **Audit log is in-memory** — production systems should persist to a database. The bounded ring buffer prevents memory exhaustion.

---

## Security Measures Implemented

| Measure | Implementation |
|---------|---------------|
| **Input validation** | All inputs validated via Pydantic models with type, range, and length constraints |
| **HTML sanitisation** | Dual-layer: Pydantic `@field_validator` + route-level `_sanitize_description()` (defense-in-depth) |
| **Role-based access control** | Viewers cannot submit fire_smoke or evacuation-level incidents (HTTP 403) |
| **Rate limiting** | `/api/incident` limited to 10 req/min per IP via sliding-window counter with stale-timestamp cleanup |
| **CORS restriction** | Only configured origins allowed; defaults to localhost in development |
| **Security headers** | X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy |
| **HSTS** | Strict-Transport-Security with max-age=31536000 and includeSubDomains |
| **Content Security Policy** | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` (justified: dynamic severity badge styling for control room operators on trusted internal networks; script-src remains strict) |
| **No hardcoded secrets** | All configuration loaded from `.env`; `.env.example` contains placeholders only |
| **Gitignore** | `.env`, `__pycache__`, and build artifacts excluded from version control |
| **Frontend XSS prevention** | `escapeHtml()` function + `textContent` DOM construction (no innerHTML for user content) |
| **Linting** | Ruff configured with security rules (flake8-bandit) via `pyproject.toml` |

### Rate Limiter Design Note

The in-memory sliding-window rate limiter is an **intentional design choice** for single-process deployments typical of stadium control rooms. Each venue runs one API process, making in-memory state sufficient and fast. For multi-instance horizontal scaling, swap in Redis-backed counters (e.g., `slowapi` + Redis) without any API contract changes.

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
| Meta items | `aria-label` | Describe zone, confidence, and rule for assistive tech |

### Visual Accessibility

- **Triple-channel severity indicators**: Every severity level uses colour + text badge + text label (never colour alone)
- **WCAG AA colour contrast**: All severity colours verified against their backgrounds
- **Keyboard navigation**: All interactive elements are keyboard-navigable with visible `:focus-visible` styles
- **Semantic HTML**: Proper `<header>`, `<main>`, `<aside>`, `<section>`, `<fieldset>`, `<legend>`, `<article>` elements
- **Labelled inputs**: Every form input has an explicit `<label>` linked by `for`/`id`
- **Skip navigation**: Skip-to-content link for keyboard users
- **Responsive layout**: Mobile-first grid with `@media (max-width: 900px)` breakpoint

### Motion and Contrast Preferences

- **`prefers-reduced-motion: reduce`**: All animations and transitions are disabled for users with vestibular disorders or motion sensitivity
- **`prefers-contrast: more`**: High-contrast colour scheme with thicker borders and outlines for users with low vision

### Client-Side Validation

- **`aria-describedby`**: Every required input links to a validation error `<span>` via `aria-describedby`
- **`role="alert"`**: Error messages use `role="alert"` for immediate screen reader announcement
- **Visual indicators**: Invalid fields receive a red border + background + error message
- **Live clearing**: Errors clear on input, providing immediate feedback

### Engine-Level Accessibility

The decision engine itself includes **Rule 4: Accessibility Routing**, which ensures accessible seating zones receive priority attention during fire/overcrowding incidents and flags when accessible capacity reaches zero.

---

## Test Coverage Summary

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
| `test_happy_path_known_types` (parametrised ×5) | Incident Triage | Each type maps to correct severity |
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
| `test_fire_smoke_with_available_seats` | Accessibility Routing | Fire + seats → Critical dispatch |
| `test_overcrowding_with_available_seats` | Accessibility Routing | Overcrowding + seats → Critical |
| `test_zero_accessible_seats_any_incident` | Accessibility Routing | Zero seats → High monitoring |
| `test_fire_smoke_zero_accessible_seats` | Accessibility Routing | Fire + zero seats → High |
| `test_no_trigger_medical_with_seats` | Accessibility Routing | Medical + seats → no trigger |
| `test_recommendation_shape` | Accessibility Routing | Field type validation |
| `test_high_occupancy_post_match` | Egress Plan | ≥90% → High 3-wave exit |
| `test_medium_occupancy_overtime` | Egress Plan | 70–89% → Medium 2-wave exit |
| `test_low_occupancy_post_match` | Egress Plan | <70% → Low standard exit |
| `test_edge_case_exactly_90_percent` | Egress Plan | 90% boundary → High |
| `test_edge_case_exactly_70_percent` | Egress Plan | 70% boundary → Medium |
| `test_no_trigger_pre_match_phase` | Egress Plan | Pre-match → no trigger |
| `test_no_trigger_halftime_phase` | Egress Plan | Halftime → no trigger |
| `test_top_two_gates_listed` | Egress Plan | Least-congested gates in output |
| `test_adversarial_negative_wait_time` | Egress Plan | Pydantic rejects negative wait |
| `test_adversarial_zero_total_capacity` | Egress Plan | Pydantic rejects zero capacity |

### Integration Tests (`test_api.py`) — 24 tests

| Test | Endpoint | What It Validates |
|------|----------|-------------------|
| `test_valid_payload_returns_recommendations` | POST /api/analyze | 200, ≥1 result, severity ordering |
| `test_viewer_cannot_submit_fire_smoke` | POST /api/analyze | 403 for viewer + fire_smoke |
| `test_malformed_payload_returns_422` | POST /api/analyze | 422 for missing fields |
| `test_invalid_role_returns_422` | POST /api/analyze | 422 for unknown role |
| `test_html_sanitised_in_response` | POST /api/analyze | HTML stripped from description |
| `test_recommendation_fields_present` | POST /api/analyze | All 6 required fields present |
| `test_admin_can_submit_fire_smoke` | POST /api/analyze | Admin bypasses RBAC |
| `test_empty_gates_returns_422` | POST /api/analyze | Empty gate list rejected |
| `test_gate_capacity_over_100_returns_422` | POST /api/analyze | >100% rejected by schema |
| `test_venue_id_default` | POST /api/analyze | Default venue_id accepted |
| `test_venue_id_custom` | POST /api/analyze | Custom venue_id accepted |
| `test_valid_medical_incident` | POST /api/incident | 200, High severity |
| `test_fire_smoke_incident` | POST /api/incident | Critical severity |
| `test_missing_incident_field_returns_422` | POST /api/incident | 422 for missing field |
| `test_health_returns_ok` | GET /api/health | 200, status ok, version 1.0.0 |
| `test_security_headers_present` | GET /api/health | All 5 security headers |
| `test_security_headers_on_post` | POST /api/analyze | Headers on POST too |
| `test_hsts_header_present` | GET /api/health | HSTS with max-age |
| `test_csp_includes_connect_src` | GET /api/health | CSP allows WebSocket |
| `test_rate_limit_allows_normal_traffic` | POST /api/incident | 10 requests succeed |
| `test_rate_limit_exceeded_returns_429` | POST /api/incident | 11th request → 429 |
| `test_sort_with_unknown_severity` | _sort_recommendations | Unknown severity → end |
| `test_audit_log_empty_by_default` | GET /api/audit | Empty for new venue |
| `test_audit_log_records_analyze` | GET /api/audit | Records from /analyze |
| `test_audit_log_records_incident` | GET /api/audit | Records from /incident |
| `test_websocket_connects` | WS /api/ws | Connection + ping/pong |

### Frontend Tests (`test_frontend.py`) — 22 tests

| Test | Category | What It Validates |
|------|----------|-------------------|
| `test_lang_attribute_present` | HTML Accessibility | `lang="en"` on html element |
| `test_skip_nav_link_present` | HTML Accessibility | Skip-to-content link exists |
| `test_semantic_header/main/aside/section` | HTML Accessibility | Semantic HTML5 elements |
| `test_fieldset_and_legend` | HTML Accessibility | Form grouping elements |
| `test_all_inputs_have_labels` | HTML Accessibility | Every input has a label |
| `test_aria_live_region` | HTML Accessibility | Toast aria-live="polite" |
| `test_aria_hidden_on_loading_overlay` | HTML Accessibility | Loading overlay hidden |
| `test_aria_describedby_on_required_inputs` | HTML Accessibility | Error message links |
| `test_decorative_emojis_hidden` | HTML Accessibility | aria-hidden on emojis |
| `test_meta_viewport_present` | HTML Accessibility | Mobile viewport meta |
| `test_meta_description_present` | HTML Accessibility | SEO meta description |
| `test_focus_visible_styles` | CSS Accessibility | Focus indicator styles |
| `test_prefers_reduced_motion` | CSS Accessibility | Motion disability support |
| `test_prefers_contrast` | CSS Accessibility | High contrast mode |
| `test_skip_nav_styles` | CSS Accessibility | Skip nav reveal on focus |
| `test_sr_only_utility` | CSS Accessibility | Screen reader utility class |
| `test_field_error_styles` | CSS Accessibility | Validation error styles |
| `test_responsive_breakpoint` | CSS Accessibility | Responsive layout |
| `test_strict_mode` | JS Security | "use strict" |
| `test_escape_html_defined` | JS Security | XSS prevention function |
| `test_iife_encapsulation` | JS Security | No global pollution |
| `test_debounce_implemented` | JS Security | Debounced submissions |
| `test_form_validation_present` | JS Security | Client-side validation |

---

## License

Built for the Smart Stadiums hackathon challenge. All code written from scratch.
