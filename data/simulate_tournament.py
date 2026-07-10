"""StadiumOps AI — Tournament Operations Multi-Venue Simulator.

Simulates 3 distinct FIFA World Cup 2026 venues during Quarter-Finals matchday:
1. Northern Arena (Capacity: 65,000) - Post-match egress with crowd surge.
2. Southern Stadium (Capacity: 48,000) - Halftime medical incident + close lightning.
3. Eastern Complex (Capacity: 55,000) - Overtime with active fire/smoke.

Coordinates recommendations and displays cross-venue alerts for regional transit
coordination and emergency dispatch.
"""

import asyncio
import os
import sys

# Configure stdout to output UTF-8 (fixes UnicodeEncodeError on Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure project root is in the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

API_URL = "http://127.0.0.1:8000/api/analyze"

VENUES = {
    "Northern Arena": {
        "venue_id": "Northern-Arena",
        "gates": [
            {
                "gate_id": "Gate-A",
                "capacity_percent": 95.0,
                "entry_rate": 0,
                "wait_time_seconds": 600,
            },
            {
                "gate_id": "Gate-B",
                "capacity_percent": 88.0,
                "entry_rate": 0,
                "wait_time_seconds": 540,
            },
            {
                "gate_id": "Gate-C",
                "capacity_percent": 30.0,
                "entry_rate": 0,
                "wait_time_seconds": 60,
            },
            {
                "gate_id": "Gate-D",
                "capacity_percent": 20.0,
                "entry_rate": 0,
                "wait_time_seconds": 40,
            },
        ],
        "incident": {
            "incident_id": "INC-NORTH-01",
            "zone": "Gate-A Plaza",
            "type": "overcrowding",
            "description": "Severe bottleneck forming at egress. Spectators blocking stairwell.",
            "reporter_role": "gate_supervisor",
        },
        "weather": {
            "temperature_celsius": 22.0,
            "heat_index": 22.0,
            "lightning_detected": False,
            "lightning_radius_km": 0.0,
        },
        "event_context": {
            "phase": "post_match",
            "total_capacity": 65000,
            "occupied_seats": 62000,
            "accessible_seats_available": 4,
            "concession_queue_avg_minutes": 1.0,
        },
        "role": "admin",
    },
    "Southern Stadium": {
        "venue_id": "Southern-Stadium",
        "gates": [
            {
                "gate_id": "Gate-1",
                "capacity_percent": 45.0,
                "entry_rate": 20,
                "wait_time_seconds": 90,
            },
            {
                "gate_id": "Gate-2",
                "capacity_percent": 50.0,
                "entry_rate": 22,
                "wait_time_seconds": 100,
            },
            {
                "gate_id": "Gate-3",
                "capacity_percent": 40.0,
                "entry_rate": 15,
                "wait_time_seconds": 80,
            },
            {
                "gate_id": "Gate-4",
                "capacity_percent": 35.0,
                "entry_rate": 10,
                "wait_time_seconds": 60,
            },
        ],
        "incident": {
            "incident_id": "INC-SOUTH-02",
            "zone": "Section E2",
            "type": "medical",
            "description": "Spectator in cardiac distress. CPR in progress.",
            "reporter_role": "paramedic_lead",
        },
        "weather": {
            "temperature_celsius": 39.0,
            "heat_index": 42.0,
            "lightning_detected": True,
            "lightning_radius_km": 8.5,
        },
        "event_context": {
            "phase": "halftime",
            "total_capacity": 48000,
            "occupied_seats": 44000,
            "accessible_seats_available": 0,
            "concession_queue_avg_minutes": 14.5,
        },
        "role": "admin",
    },
    "Eastern Complex": {
        "venue_id": "Eastern-Complex",
        "gates": [
            {
                "gate_id": "North-Exit",
                "capacity_percent": 85.0,
                "entry_rate": 0,
                "wait_time_seconds": 300,
            },
            {
                "gate_id": "South-Exit",
                "capacity_percent": 90.0,
                "entry_rate": 0,
                "wait_time_seconds": 350,
            },
            {
                "gate_id": "East-Exit",
                "capacity_percent": 35.0,
                "entry_rate": 0,
                "wait_time_seconds": 50,
            },
            {
                "gate_id": "West-Exit",
                "capacity_percent": 15.0,
                "entry_rate": 0,
                "wait_time_seconds": 20,
            },
        ],
        "incident": {
            "incident_id": "INC-EAST-03",
            "zone": "Concourse level 2",
            "type": "fire_smoke",
            "description": "Smoke reported in food court kitchen. Small grease fire visible.",
            "reporter_role": "concession_manager",
        },
        "weather": {
            "temperature_celsius": 24.0,
            "heat_index": 24.0,
            "lightning_detected": True,
            "lightning_radius_km": 19.0,
        },
        "event_context": {
            "phase": "overtime",
            "total_capacity": 55000,
            "occupied_seats": 53000,
            "accessible_seats_available": 15,
            "concession_queue_avg_minutes": 4.0,
        },
        "role": "admin",
    },
}


async def simulate_venue(name, client, payload):
    try:
        response = await client.post(API_URL, json=payload, timeout=10.0)
        response.raise_for_status()
        return name, response.json().get("recommendations", []), None
    except Exception as exc:
        # Direct fallback evaluation using python module imports
        try:
            from backend.core.decision_engine import (
                accessibility_routing,
                egress_plan,
                gate_load_balance,
                triage_incident,
                weather_action,
            )
            from backend.models.schemas import AnalyzeRequest

            req = AnalyzeRequest(**payload)
            recs = []
            recs.extend(gate_load_balance(req.gates))
            recs.append(triage_incident(req.incident))
            recs.extend(weather_action(req.weather))
            recs.extend(accessibility_routing(req.event_context, req.incident))
            recs.extend(egress_plan(req.event_context, req.gates))
            recs.sort(
                key=lambda r: {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}.get(
                    r.severity.value, 99
                )
            )
            return name, [r.model_dump() for r in recs], f"Fallback engine (API offline: {exc})"
        except Exception as local_exc:
            return name, [], f"Local evaluation failed: {local_exc}"


async def run_tournament():
    print("=" * 80)
    print("STADIUMLOPS AI — MULTI-VENUE TOURNAMENT SIMULATOR")
    print("=" * 80)
    print("Simulating 3 venues concurrently...")

    async with httpx.AsyncClient() as client:
        tasks = [simulate_venue(name, client, payload) for name, payload in VENUES.items()]
        results = await asyncio.gather(*tasks)

    total_recommendations = 0
    venue_summaries = []

    for name, recs, error in results:
        total_recommendations += len(recs)
        venue_summaries.append((name, recs, error))

        print("\n" + "=" * 50)
        print(f" VENUE: {name.upper()}")
        if error:
            print(f" [!] Evaluated via: {error}")
        print("=" * 50)

        for idx, rec in enumerate(recs, 1):
            sev = rec["severity"]
            print(f"{idx}. [{sev.upper()}] (Rule: {rec['rule_id']}) in Zone {rec['affected_zone']}")
            print(f"   Action: {rec['action']}")
            print(f"   Reason: {rec['reason']}\n")

    print("=" * 80)
    print("TOURNAMENT OPERATIONS AGGREGATE SUMMARY")
    print("=" * 80)
    print(f"Total Venues Monitored: {len(results)}")
    print(f"Total Live Alerts Generated: {total_recommendations}")

    # Regional Transit Alert Coordination
    egress_stadiums = [
        name for name, recs, _ in results if any(r["rule_id"] == "egress_plan" for r in recs)
    ]
    if egress_stadiums:
        print(
            f"\n[TRANSIT COORDINATION ALERT]: Overlapping egress patterns detected at: {', '.join(egress_stadiums)}."
        )
        print("  Recommendation: Alert regional transit dispatch to scale up train/bus services.")

    # Weather Coordination
    lightning_stadiums = [
        name for name, _, _ in results if VENUES[name]["weather"]["lightning_detected"]
    ]
    if lightning_stadiums:
        print(
            f"\n[WEATHER INCIDENT WARNING]: Severe lightning front active over: {', '.join(lightning_stadiums)}."
        )
        print("  Recommendation: Suspend outdoor volunteer shifts across this zone.")

    print("\nTournament Operations status checks complete.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_tournament())
