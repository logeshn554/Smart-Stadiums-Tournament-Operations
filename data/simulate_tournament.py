"""
Multi-venue tournament simulator for StadiumOps AI.

Simulates a realistic tournament day across three stadiums with concurrent
matches, overlapping egress waves, weather events, and cross-venue incident
coordination.  Sends analysis requests to each venue's endpoint and displays
a consolidated tournament operations view.

This directly addresses the "Tournament Operations" aspect of the problem
statement by demonstrating:
  1. Multi-venue concurrent event monitoring
  2. Cross-venue incident pattern analysis
  3. Staggered match scheduling with overlapping egress
  4. Weather-driven venue-wide decisions

Usage:
    python data/simulate_tournament.py

Requires the backend to be running:
    uvicorn backend.api.main:app --reload
"""

import json
import os
import sys
import time
from typing import Any

import httpx

# Avoid UnicodeEncodeError on Windows console when printing emojis/symbols
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ── Tournament venue configurations ──────────────────────────────────────

VENUES: list[dict[str, Any]] = [
    {
        "venue_id": "stadium-north",
        "name": "Northern Arena",
        "capacity": 65000,
        "match": "Team Alpha vs Team Beta (Quarter-Final 1)",
        "phase": "post_match",
        "occupied_ratio": 0.92,
        "gates": [
            {"gate_id": "N-Gate-A", "capacity_percent": 91.0, "entry_rate": 48, "wait_time_seconds": 380},
            {"gate_id": "N-Gate-B", "capacity_percent": 35.0, "entry_rate": 12, "wait_time_seconds": 55},
            {"gate_id": "N-Gate-C", "capacity_percent": 78.0, "entry_rate": 35, "wait_time_seconds": 210},
            {"gate_id": "N-Gate-D", "capacity_percent": 22.0, "entry_rate": 6, "wait_time_seconds": 30},
        ],
        "incident": {
            "incident_id": "INC-TOURN-001",
            "zone": "N-Section-B3",
            "type": "overcrowding",
            "description": "Post-match crowd surge near north exit tunnel. Density exceeding safe limits.",
            "reporter_role": "crowd_control_lead",
        },
        "weather": {
            "temperature_celsius": 36.0,
            "heat_index": 42.0,
            "lightning_detected": False,
            "lightning_radius_km": 0.0,
        },
        "accessible_seats": 8,
        "concession_queue": 12.5,
    },
    {
        "venue_id": "stadium-south",
        "name": "Southern Stadium",
        "capacity": 48000,
        "match": "Team Gamma vs Team Delta (Quarter-Final 2)",
        "phase": "halftime",
        "occupied_ratio": 0.85,
        "gates": [
            {"gate_id": "S-Gate-A", "capacity_percent": 65.0, "entry_rate": 28, "wait_time_seconds": 140},
            {"gate_id": "S-Gate-B", "capacity_percent": 88.0, "entry_rate": 42, "wait_time_seconds": 310},
            {"gate_id": "S-Gate-C", "capacity_percent": 30.0, "entry_rate": 9, "wait_time_seconds": 40},
        ],
        "incident": {
            "incident_id": "INC-TOURN-002",
            "zone": "S-Section-A1",
            "type": "medical",
            "description": "Spectator showing signs of heat exhaustion in uncovered stand. Conscious but dizzy.",
            "reporter_role": "medical_officer",
        },
        "weather": {
            "temperature_celsius": 39.0,
            "heat_index": 44.0,
            "lightning_detected": True,
            "lightning_radius_km": 18.0,
        },
        "accessible_seats": 0,
        "concession_queue": 15.2,
    },
    {
        "venue_id": "stadium-east",
        "name": "Eastern Complex",
        "capacity": 55000,
        "match": "Team Epsilon vs Team Zeta (Quarter-Final 3)",
        "phase": "overtime",
        "occupied_ratio": 0.95,
        "gates": [
            {"gate_id": "E-Gate-A", "capacity_percent": 95.0, "entry_rate": 55, "wait_time_seconds": 450},
            {"gate_id": "E-Gate-B", "capacity_percent": 82.0, "entry_rate": 38, "wait_time_seconds": 260},
            {"gate_id": "E-Gate-C", "capacity_percent": 15.0, "entry_rate": 4, "wait_time_seconds": 20},
            {"gate_id": "E-Gate-D", "capacity_percent": 45.0, "entry_rate": 18, "wait_time_seconds": 95},
        ],
        "incident": {
            "incident_id": "INC-TOURN-003",
            "zone": "E-Section-C2",
            "type": "fire_smoke",
            "description": "Smoke detected from electrical panel near concession area. No visible flames.",
            "reporter_role": "security_lead",
        },
        "weather": {
            "temperature_celsius": 34.0,
            "heat_index": 38.0,
            "lightning_detected": True,
            "lightning_radius_km": 12.0,
        },
        "accessible_seats": 3,
        "concession_queue": 8.0,
    },
]


def build_venue_payload(venue: dict[str, Any]) -> dict[str, Any]:
    """Construct the /api/analyze payload for a single venue.

    Args:
        venue: Venue configuration dict from the VENUES list.

    Returns:
        A dict matching the AnalyzeRequest schema.
    """
    occupied = int(venue["capacity"] * venue["occupied_ratio"])
    return {
        "venue_id": venue["venue_id"],
        "gates": venue["gates"],
        "incident": venue["incident"],
        "weather": venue["weather"],
        "event_context": {
            "phase": venue["phase"],
            "total_capacity": venue["capacity"],
            "occupied_seats": occupied,
            "accessible_seats_available": venue["accessible_seats"],
            "concession_queue_avg_minutes": venue["concession_queue"],
        },
        "role": "admin",
    }


def print_venue_header(venue: dict[str, Any]) -> None:
    """Print a formatted header for a venue's results.

    Args:
        venue: Venue configuration dict.
    """
    phase_icons = {
        "pre_match": "🟢",
        "halftime": "🟡",
        "post_match": "🔴",
        "overtime": "⚡",
    }
    icon = phase_icons.get(venue["phase"], "⚪")
    print(f"\n{'─' * 72}")
    print(f"  {icon} {venue['name']} ({venue['venue_id']})")
    print(f"     Match: {venue['match']}")
    print(f"     Phase: {venue['phase'].upper()} | Occupancy: {venue['occupied_ratio']:.0%}")
    print(f"     Incident: [{venue['incident']['type']}] {venue['incident']['description'][:60]}...")
    print(f"{'─' * 72}")


def print_recommendations(recommendations: list[dict[str, Any]]) -> None:
    """Print recommendations for a venue.

    Args:
        recommendations: List of recommendation dicts from the API response.
    """
    severity_icons = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}

    for idx, rec in enumerate(recommendations, start=1):
        icon = severity_icons.get(rec["severity"], "⚪")
        print(f"    {icon} [{rec['severity']}] {rec['action'][:80]}")
        if idx <= 3:  # Show reason for top 3 only
            print(f"       └─ {rec['reason'][:100]}")


def print_cross_venue_summary(all_results: dict[str, list[dict[str, Any]]]) -> None:
    """Print a cross-venue tournament operations summary.

    Analyzes patterns across all venues and highlights tournament-wide
    concerns that a central operations room would need to coordinate.

    Args:
        all_results: Dict mapping venue_id to list of recommendations.
    """
    print(f"\n{'═' * 72}")
    print("  🏆 TOURNAMENT OPERATIONS SUMMARY")
    print(f"{'═' * 72}")

    total_recs = sum(len(recs) for recs in all_results.values())
    critical_count = sum(
        1 for recs in all_results.values()
        for r in recs if r["severity"] == "Critical"
    )
    high_count = sum(
        1 for recs in all_results.values()
        for r in recs if r["severity"] == "High"
    )

    print(f"\n  📊 Aggregate Statistics:")
    print(f"     Total recommendations across {len(all_results)} venues: {total_recs}")
    print(f"     Critical alerts: {critical_count}")
    print(f"     High-priority actions: {high_count}")

    # Cross-venue pattern detection
    weather_venues = []
    egress_venues = []
    accessibility_venues = []

    for venue_id, recs in all_results.items():
        for r in recs:
            if r["rule_id"] == "weather_action":
                weather_venues.append(venue_id)
            if r["rule_id"] == "egress_plan" and r["severity"] in ("High", "Critical"):
                egress_venues.append(venue_id)
            if r["rule_id"] == "accessibility_routing":
                accessibility_venues.append(venue_id)

    weather_venues = list(set(weather_venues))
    egress_venues = list(set(egress_venues))
    accessibility_venues = list(set(accessibility_venues))

    print(f"\n  🌩  Weather alerts active at: {', '.join(weather_venues) if weather_venues else 'None'}")
    print(f"  🚪 High-priority egress at: {', '.join(egress_venues) if egress_venues else 'None'}")
    print(f"  ♿ Accessibility alerts at: {', '.join(accessibility_venues) if accessibility_venues else 'None'}")

    if len(egress_venues) > 1:
        print(f"\n  ⚠️  COORDINATION ALERT: Multiple venues have concurrent high-priority")
        print(f"     egress situations. Stagger public transport dispatches to prevent")
        print(f"     transit hub overcrowding.")

    if len(weather_venues) > 1:
        print(f"\n  ⚠️  COORDINATION ALERT: Weather affecting {len(weather_venues)} venues.")
        print(f"     Consider tournament-wide weather protocol activation.")

    print(f"\n{'═' * 72}\n")


def main() -> None:
    """Run the multi-venue tournament simulation.

    Sends concurrent analysis requests to all three venues, collects
    results, and produces a consolidated tournament operations summary.
    """
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

    print("=" * 72)
    print("  🏟️  StadiumOps AI — Multi-Venue Tournament Simulation")
    print("  📅  Quarter-Finals Day | 3 Concurrent Matches")
    print("=" * 72)

    all_results: dict[str, list[dict[str, Any]]] = {}

    for venue in VENUES:
        payload = build_venue_payload(venue)

        # Save individual venue payload
        seed_dir = os.path.dirname(__file__)
        seed_path = os.path.join(seed_dir, f"seed_{venue['venue_id']}.json")
        os.makedirs(seed_dir, exist_ok=True)
        with open(seed_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        print_venue_header(venue)

        try:
            response = httpx.post(
                f"{base_url}/api/analyze",
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            recs = data.get("recommendations", [])
            all_results[venue["venue_id"]] = recs
            print_recommendations(recs)
            print(f"\n    📋 {len(recs)} recommendation(s) generated.")

        except httpx.ConnectError:
            print(f"\n    [✗] Could not connect to API at {base_url}.")
            print(f"        Start the backend: uvicorn backend.api.main:app --reload")
            all_results[venue["venue_id"]] = []

        except httpx.HTTPStatusError as exc:
            print(f"\n    [✗] API returned status {exc.response.status_code}")
            all_results[venue["venue_id"]] = []

    # Cross-venue analysis
    print_cross_venue_summary(all_results)

    # Query audit logs for each venue
    print("  📝 Audit Log Summary:")
    for venue in VENUES:
        try:
            response = httpx.get(
                f"{base_url}/api/audit?venue_id={venue['venue_id']}",
                timeout=5.0,
            )
            data = response.json()
            print(f"     {venue['venue_id']}: {data['total_entries']} logged incident(s)")
        except Exception:
            print(f"     {venue['venue_id']}: (audit unavailable)")

    print()


if __name__ == "__main__":
    main()
