"""
Load test definition for StadiumOps AI using Locust.

Simulates realistic control room traffic patterns across all API endpoints.
Designed to validate p95 latency and throughput under sustained load.

Usage:
    locust -f locustfile.py --headless -u 50 -r 10 --run-time 60s \
           --host http://127.0.0.1:8000 --csv results/load_test

Results are written to the ``results/`` directory as CSV files.
"""

import random

from locust import HttpUser, between, task


class ControlRoomOperator(HttpUser):
    """Simulates a stadium control room operator interacting with the API.

    Traffic profile:
        - 60% full analysis requests (/api/analyze)
        - 25% single-incident triage (/api/incident)
        - 10% health checks (/api/health)
        - 5% audit log queries (/api/audit)
    """

    wait_time = between(0.5, 2.0)

    # ── Gate data pools ───────────────────────────────────────────────────

    GATE_IDS = ["North-A", "North-B", "South-A", "South-B", "East-A", "West-A"]
    INCIDENT_TYPES = ["medical", "security", "overcrowding", "lost_child", "fire_smoke"]
    PHASES = ["pre_match", "halftime", "post_match", "overtime"]
    ZONES = ["A1", "A2", "B1", "B2", "B3", "C1", "C2", "D1", "D2"]
    VENUE_IDS = ["stadium-north", "stadium-south", "stadium-east", "default"]

    def _random_gates(self) -> list[dict]:
        """Generate a random set of gate statuses.

        Returns:
            A list of 3-4 gate status dicts with realistic values.
        """
        count = random.randint(3, 4)
        return [
            {
                "gate_id": self.GATE_IDS[i % len(self.GATE_IDS)],
                "capacity_percent": round(random.uniform(10, 98), 1),
                "entry_rate": random.randint(5, 60),
                "wait_time_seconds": random.randint(10, 500),
            }
            for i in range(count)
        ]

    def _random_incident(self) -> dict:
        """Generate a random incident report.

        Returns:
            A dict matching the IncidentReport schema.
        """
        return {
            "incident_id": f"INC-LOAD-{random.randint(1000, 9999)}",
            "zone": random.choice(self.ZONES),
            "type": random.choice(self.INCIDENT_TYPES),
            "description": "Load test simulated incident for throughput validation.",
            "reporter_role": random.choice(["security_lead", "medical_officer", "steward"]),
        }

    def _random_analyze_payload(self) -> dict:
        """Build a complete analyze request with random data.

        Returns:
            A dict matching the AnalyzeRequest schema.
        """
        return {
            "venue_id": random.choice(self.VENUE_IDS),
            "gates": self._random_gates(),
            "incident": self._random_incident(),
            "weather": {
                "temperature_celsius": round(random.uniform(15, 42), 1),
                "heat_index": round(random.uniform(15, 48), 1),
                "lightning_detected": random.choice([True, False]),
                "lightning_radius_km": round(random.uniform(0, 50), 1),
            },
            "event_context": {
                "phase": random.choice(self.PHASES),
                "total_capacity": 60000,
                "occupied_seats": random.randint(10000, 58000),
                "accessible_seats_available": random.randint(0, 50),
                "concession_queue_avg_minutes": round(random.uniform(1, 15), 1),
            },
            "role": "admin",
        }

    # ── Task definitions ──────────────────────────────────────────────────

    @task(60)
    def full_analysis(self) -> None:
        """Send a full analysis request (primary workload)."""
        self.client.post(
            "/api/analyze",
            json=self._random_analyze_payload(),
            name="/api/analyze",
        )

    @task(25)
    def single_incident(self) -> None:
        """Send a single incident triage request."""
        self.client.post(
            "/api/incident",
            json=self._random_incident(),
            name="/api/incident",
        )

    @task(10)
    def health_check(self) -> None:
        """Check API health."""
        self.client.get("/api/health", name="/api/health")

    @task(5)
    def audit_log(self) -> None:
        """Query the audit log for a random venue."""
        venue = random.choice(self.VENUE_IDS)
        self.client.get(
            f"/api/audit?venue_id={venue}",
            name="/api/audit",
        )
