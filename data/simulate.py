"""
Mock data simulator for StadiumOps AI.

Generates a realistic event snapshot and sends it to the /api/analyze
endpoint.  Prints ranked recommendations to the terminal and saves the
payload to data/seed.json for reference.
"""

import json
import os
import sys

import httpx

# Avoid UnicodeEncodeError on Windows console when printing emojis/symbols
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def build_simulation_payload() -> dict:
    """Construct a realistic halftime event snapshot.

    Simulates:
      - 4 gates: two overloaded (>80%), one underloaded (<40%), one mid-range
      - A medical incident in zone B3
      - Heat index of 41 °C, no lightning
      - Halftime phase, 85% occupied, 12 accessible seats available
      - Admin role

    Returns:
        A dict matching the AnalyzeRequest schema.
    """
    return {
        "gates": [
            {
                "gate_id": "North-A",
                "capacity_percent": 88.0,
                "entry_rate": 45,
                "wait_time_seconds": 340,
            },
            {
                "gate_id": "North-B",
                "capacity_percent": 92.0,
                "entry_rate": 50,
                "wait_time_seconds": 420,
            },
            {
                "gate_id": "South-A",
                "capacity_percent": 25.0,
                "entry_rate": 8,
                "wait_time_seconds": 45,
            },
            {
                "gate_id": "South-B",
                "capacity_percent": 60.0,
                "entry_rate": 22,
                "wait_time_seconds": 130,
            },
        ],
        "incident": {
            "incident_id": "INC-SIM-001",
            "zone": "B3",
            "type": "medical",
            "description": "Spectator collapsed near Row 14, appears to be heat exhaustion. Conscious but disoriented.",
            "reporter_role": "section_steward",
        },
        "weather": {
            "temperature_celsius": 38.0,
            "heat_index": 41.0,
            "lightning_detected": False,
            "lightning_radius_km": 0.0,
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


def save_seed_json(payload: dict, filepath: str) -> None:
    """Save the simulation payload to a JSON file.

    Args:
        payload: The simulation payload dict.
        filepath: Destination file path.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
    print(f"[✓] Payload saved to {filepath}")


def print_recommendations(recommendations: list[dict]) -> None:
    """Print recommendations in a readable terminal format.

    Args:
        recommendations: List of recommendation dicts from the API response.
    """
    severity_icons = {
        "Critical": "🔴",
        "High": "🟠",
        "Medium": "🟡",
        "Low": "🟢",
    }

    print("\n" + "=" * 72)
    print("  StadiumOps AI — Simulation Results")
    print("=" * 72)

    for index, rec in enumerate(recommendations, start=1):
        icon = severity_icons.get(rec["severity"], "⚪")
        print(f"\n  {icon} Recommendation #{index}")
        print(f"  {'─' * 40}")
        print(f"  Rule ID:       {rec['rule_id']}")
        print(f"  Severity:      {rec['severity']}")
        print(f"  Confidence:    {rec['confidence']}")
        print(f"  Affected Zone: {rec['affected_zone']}")
        print(f"  Action:        {rec['action']}")
        print(f"  Reason:        {rec['reason']}")

    print("\n" + "=" * 72)
    print(f"  Total recommendations: {len(recommendations)}")
    print("=" * 72 + "\n")


def main() -> None:
    """Run the simulation: build payload, send to API, display results."""
    base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    seed_path = os.path.join(os.path.dirname(__file__), "seed.json")

    payload = build_simulation_payload()
    save_seed_json(payload, seed_path)

    print(f"[→] Sending simulation payload to {base_url}/api/analyze ...")

    try:
        response = httpx.post(
            f"{base_url}/api/analyze",
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.ConnectError:
        print(
            "\n[✗] Could not connect to the API server. "
            "Make sure the backend is running:\n"
            "    uvicorn backend.api.main:app --reload\n"
        )
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(f"\n[✗] API returned status {exc.response.status_code}:")
        print(exc.response.text)
        sys.exit(1)

    data = response.json()
    print_recommendations(data.get("recommendations", []))


if __name__ == "__main__":
    main()
