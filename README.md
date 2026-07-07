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
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP POST /api/analyze
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API LAYER                                │
│  FastAPI (routes.py + main.py)                                  │
│  • Input validation (Pydantic)                                  │
│  • Role-based access control                                    │
│  • Rate limiting (in-memory)                                    │
│  • HTML sanitisation                                            │
│  • CORS middleware                                              │
└────────────────────────┬────────────────────────────────────────┘
                         │ function calls
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DECISION ENGINE                              │
│  core/decision_engine.py                                        │
│  • gate_load_balance()                                          │
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
│  • Recommendation, AnalyzeRequest, AnalyzeResponse              │
│  • Field validators (HTML strip, range checks, enums)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Folder Structure

```
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app entry point, CORS, env config
│   │   └── routes.py            # API endpoints (/analyze, /incident, /health)
│   ├── core/
│   │   └── decision_engine.py   # Five stateless decision rules
│   ├── models/
│   │   └── schemas.py           # Pydantic input/output data models
│   └── tests/
│       ├── test_engine.py       # Unit tests for all decision rules
│       └── test_api.py          # Integration tests for API endpoints
├── frontend/
│   ├── index.html               # Dashboard HTML with accessible form
│   ├── style.css                # Dark-theme CSS with design tokens
│   └── app.js                   # Vanilla JS for API calls and rendering
├── data/
│   ├── seed.json                # Pre-generated simulation payload
│   └── simulate.py              # Mock data simulator script
├── .env.example                 # Environment variable placeholders
├── .gitignore                   # Python/Node/build exclusions
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

## Assumptions Made

1. **Weather data is simulated** — not sourced from a live weather API. In production, this would integrate with services like OpenWeatherMap or a venue-specific weather station.
2. **Authentication/roles are mocked** — the `role` field in the payload acts as a simple authorization gate. A production system would use JWT tokens or OAuth.
3. **Gate and sensor data is generated** — the simulator creates realistic but synthetic data. Real deployments would ingest data from IoT sensors, turnstile counters, and CCTV analytics.
4. **Single-venue scope** — the engine handles one venue at a time. Multi-venue tournament support would require session/venue isolation.

---

## Security Measures Implemented

| Measure | Implementation |
|---------|---------------|
| **Input validation** | All inputs validated via Pydantic models with type, range, and length constraints |
| **HTML sanitisation** | Incident descriptions are stripped of all HTML tags before processing |
| **Role-based access control** | Viewers cannot submit fire_smoke or evacuation-level incidents (HTTP 403) |
| **Rate limiting** | `/api/incident` endpoint limited to 10 requests/minute per IP via sliding-window counter |
| **CORS restriction** | Only configured origins allowed; defaults to localhost in development |
| **No hardcoded secrets** | All configuration loaded from `.env`; `.env.example` contains placeholders only |
| **Gitignore** | `.env`, `__pycache__`, and build artifacts are excluded from version control |

---

## Accessibility Features Implemented

### ARIA Attributes

| Element | Attribute | Purpose |
|---------|-----------|---------|
| Recommendations panel | `role="region"` `aria-label="Live Recommendations"` | Screen readers announce the panel |
| Critical/High cards | `role="alert"` | Screen readers immediately announce urgent recommendations |
| Reason toggle buttons | `aria-expanded` `aria-controls` | Indicate expandable content state |
| Loading overlay | `aria-hidden` | Prevent screen readers from reading background content |
| Toast container | `aria-live="polite"` | Announce notifications without interrupting |

### Visual Accessibility

- **Triple-channel severity indicators**: Every severity level uses colour + text badge + icon (never colour alone)
- **WCAG AA colour contrast**: All severity colours verified against their backgrounds:
  - Critical: `#D32F2F` on white (ratio ≥ 4.5:1) ✓
  - High: `#E65100` on white (ratio ≥ 4.5:1) ✓
  - Medium: `#F57F17` on white — used on dark backgrounds in the dashboard for sufficient contrast ✓
  - Low: `#2E7D32` on white (ratio ≥ 4.5:1) ✓
- **Keyboard navigation**: All interactive elements (buttons, inputs, selects, toggle buttons) are keyboard-navigable with visible `:focus-visible` styles
- **Semantic HTML**: Proper `<header>`, `<main>`, `<aside>`, `<section>`, `<fieldset>`, `<legend>` elements
- **Labelled inputs**: Every form input has an explicit `<label>` linked by `for`/`id`

### Engine-Level Accessibility

The decision engine itself includes **Rule 4: Accessibility Routing**, which ensures accessible seating zones receive priority attention during fire/overcrowding incidents and flags when accessible capacity reaches zero.

---

## Test Coverage Summary

### Unit Tests (`test_engine.py`)

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

### Integration Tests (`test_api.py`)

| Test | Endpoint | What It Validates |
|------|----------|-------------------|
| `test_valid_payload_returns_recommendations` | POST /api/analyze | 200 response, ≥1 result, severity ordering |
| `test_viewer_cannot_submit_fire_smoke` | POST /api/analyze | 403 for viewer + fire_smoke |
| `test_malformed_payload_returns_422` | POST /api/analyze | 422 for missing required fields |
| `test_valid_medical_incident` | POST /api/incident | 200 response, High severity present |
| `test_health_returns_ok` | GET /api/health | 200, status "ok", version "1.0.0" |

---

## License

Built for the Smart Stadiums hackathon challenge. All code written from scratch.
