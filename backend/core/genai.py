"""
StadiumOps AI — GenAI Core Module.

Integrates with the Google Gemini API using direct asynchronous HTTP calls via `httpx`.
If a GEMINI_API_KEY is not provided via the request or environment, the module
falls back to a highly contextual, realistic mock generator to ensure
out-of-the-box functionality and easy evaluation.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
import httpx

from backend.models.schemas import (
    EventContext,
    GateStatus,
    IncidentReport,
    WeatherContext,
)

logger = logging.getLogger(__name__)

GEMINI_MODEL: str = "gemini-1.5-flash"
GEMINI_API_URL: str = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


async def generate_briefing_and_playbook(
    gates: list[GateStatus],
    incident: IncidentReport,
    weather: WeatherContext,
    event_context: EventContext,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Generate a dynamic control room briefing, tactical playbook, and multilingual PA announcements.

    Uses Gemini 1.5 Flash if an API key is available, otherwise falls back to
    contextual mock responses.
    """
    effective_api_key = api_key or os.getenv("GEMINI_API_KEY")

    if not effective_api_key:
        logger.info("No Gemini API key found. Falling back to Mock GenAI Briefing.")
        return _generate_mock_playbook(gates, incident, weather, event_context)

    prompt = f"""You are the AI Chief Operations Officer for a FIFA World Cup 2026 stadium control room.
Analyze the following live stadium state:
- Gate status: {[g.model_dump() for g in gates]}
- Active incident: {incident.model_dump()}
- Weather: {weather.model_dump()}
- Event state: {event_context.model_dump()}

Based on this context, generate a tactical decision support briefing.
Your output must be a single JSON object with the following fields:
- "summary": A professional, concise (2-3 sentences) operational summary of the current status, highlighting key bottlenecks or critical alerts.
- "steps": A list of 3-5 clear, chronological action steps for control room staff. Be specific (e.g., mention gate names, specific zones, wait times).
- "announcements": A JSON object with three keys: "en", "es", "fr". The values must be public address announcements to be broadcast to fans in English, Spanish, and French, tailored to the current situation. Keep the tone helpful, clear, and reassuring.

Your response must contain ONLY the valid JSON object, with no markdown formatting wrapper (do not wrap in ```json).
"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GEMINI_API_URL}?key={effective_api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                },
                timeout=10.0
            )
            response.raise_for_status()
            res_json = response.json()
            text = res_json["candidates"][0]["content"]["parts"][0]["text"]
            # Parse the JSON response
            return json.loads(text.strip())
    except Exception as exc:
        logger.error("Gemini API call failed: %s. Falling back to Mock.", exc)
        return _generate_mock_playbook(gates, incident, weather, event_context)


async def chat_with_assistant(
    message: str,
    history: list[dict[str, str]],
    gates: list[GateStatus],
    incident: IncidentReport,
    weather: WeatherContext,
    event_context: EventContext,
    api_key: Optional[str] = None,
) -> str:
    """Provide real-time conversational decision support to the control room staff.

    Uses Gemini 1.5 Flash if an API key is available, otherwise falls back to
    contextual mock responses.
    """
    effective_api_key = api_key or os.getenv("GEMINI_API_KEY")

    if not effective_api_key:
        logger.info("No Gemini API key found. Falling back to Mock GenAI Chat.")
        return _generate_mock_chat(message, history, gates, incident, weather, event_context)

    # Format history for prompt
    history_str = ""
    for turn in history:
        role = "User" if turn.get("role") == "user" else "Assistant"
        history_str += f"{role}: {turn.get('content')}\n"

    system_context = f"""You are the AI Control Room Assistant for a FIFA World Cup 2026 stadium, helping control room staff manage operations, crowd control, safety, transportation, and multilingual assistance.
Current Stadium State:
- Gate status: {[g.model_dump() for g in gates]}
- Active incident: {incident.model_dump()}
- Weather: {weather.model_dump()}
- Event state: {event_context.model_dump()}

Instructions:
1. Provide a professional, concise response (maximum 150 words).
2. Focus on actionable, concrete advice based on the current stadium state.
3. Keep the tone calm, decisive, and clear.
4. Address the user's question directly.
"""

    prompt_content = f"{system_context}\nConversation History:\n{history_str}\nUser asks: {message}\nAssistant:"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GEMINI_API_URL}?key={effective_api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt_content}]}],
                },
                timeout=10.0
            )
            response.raise_for_status()
            res_json = response.json()
            return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:
        logger.error("Gemini API chat call failed: %s. Falling back to Mock.", exc)
        return _generate_mock_chat(message, history, gates, incident, weather, event_context)


# ── MOCK GENERATORS FOR OFFLINE / TESTING FALLBACK ──────────────────────────


def _generate_mock_playbook(
    gates: list[GateStatus],
    incident: IncidentReport,
    weather: WeatherContext,
    event_context: EventContext,
) -> dict[str, Any]:
    """Generates realistic playbooks matching the current stadium context."""
    # Find active gates information for custom steps
    overloaded = [g.gate_id for g in gates if g.capacity_percent > 80.0]
    underloaded = [g.gate_id for g in gates if g.capacity_percent < 40.0]

    if incident.type == "fire_smoke":
        summary = (
            f"CRITICAL ALERT: Active Fire/Smoke reported in Zone {incident.zone}. "
            f"Spectators are in immediate danger. Evacuation of Zone {incident.zone} is required."
        )
        steps = [
            f"Dispatch firefighting crew and emergency medical services to Zone {incident.zone} immediately.",
            f"Activate emergency alarms and initiate evacuation sequence for Zone {incident.zone}.",
            f"Direct spectators away from Zone {incident.zone} toward Gates "
            f"{', '.join(underloaded) if underloaded else 'South-A, South-B'}.",
            "Open all gate egress turnstiles to manual override mode (unrestricted exit)."
        ]
        announcements = {
            "en": f"Attention spectators in Zone {incident.zone}: Please evacuate the area immediately through the nearest exits in an orderly manner. Follow all steward directions.",
            "es": f"Atención espectadores en la Zona {incident.zone}: Por favor evacuen el área de inmediato por las salidas más cercanas de manera ordenada. Sigan las indicaciones del personal.",
            "fr": f"Attention aux spectateurs de la Zone {incident.zone} : Veuillez évacuer la zone immédiatement par les sorties les plus proches, dans le calme. Suivez les instructions des stewards."
        }
    elif weather.lightning_detected and weather.lightning_radius_km <= 15.0:
        summary = (
            f"CRITICAL WEATHER ALERT: Lightning detected {weather.lightning_radius_km} km from the stadium. "
            "Severe risk to players and spectators in open-air sections."
        )
        steps = [
            "Coordinate with match officials to suspend play and guide players to dressing rooms.",
            "Instruct spectators in open-air seating to seek shelter in the covered stadium concourses.",
            "Halt outdoor transit and volunteer dispatch on external plazas.",
            "Monitor lightning radius updates every 5 minutes."
        ]
        announcements = {
            "en": "Notice: A lightning alert has been issued for the area. For your safety, please move from open seating into the covered concourses immediately. Do not exit the stadium.",
            "es": "Aviso: Se ha emitido una alerta de rayos para la zona. Por su seguridad, trasládese de inmediato de los asientos al aire libre a los pasillos cubiertos. No salga del estadio.",
            "fr": "Avis : Une alerte de foudre a été émise. Pour votre sécurité, veuillez vous déplacer immédiatement des tribunes ouvertes vers les coursives couvertes. Ne quittez pas le stade."
        }
    elif incident.type == "medical":
        summary = (
            f"HIGH INCIDENT ALERT: Medical emergency reported in Zone {incident.zone} ({incident.description}). "
            "High heat index may increase patient distress."
        )
        steps = [
            f"Dispatch medical response team to Zone {incident.zone} with standard stretcher gear.",
            f"Instruct Zone {incident.zone} stewards to clear access paths for paramedics.",
            "Configure local CCTV feed for direct visualization of the response.",
            "Log resolution details once the patient is stabilized or evacuated."
        ]
        announcements = {
            "en": "Attention: Please keep aisles and walkways clear in Zone B3 to allow medical personnel to reach their destination. Thank you for your cooperation.",
            "es": "Atención: Por favor, mantenga los pasillos y vías de acceso despejados en la Zona B3 para permitir el paso del personal médico. Gracias por su cooperación.",
            "fr": "Attention : Veuillez laisser les allées et passages libres dans la Zone B3 afin de permettre au personnel médical de circuler. Merci de votre coopération."
        }
    elif overloaded and underloaded:
        summary = (
            f"OPERATIONAL BOTTLENECK: Crowd congestion detected at Gate(s) {', '.join(overloaded)}. "
            f"Gate(s) {', '.join(underloaded)} are currently underutilized with minimal wait times."
        )
        steps = [
            f"Update electronic wayfinding screens to redirect fans from Gate {overloaded[0]} to Gate {underloaded[0]}.",
            "Instruct perimeter stewards to advise fans arriving on plazas of the shorter wait times at the southern gates.",
            "Monitor turnstile entry rates every 2 minutes to assess load redirection."
        ]
        announcements = {
            "en": f"Welcome to the FIFA World Cup! Gate {overloaded[0]} is experiencing high wait times. Please proceed to Gate {underloaded[0]} for immediate, faster entry.",
            "es": "¡Bienvenidos a la Copa Mundial de la FIFA! La Puerta {overloaded[0]} está experimentando altos tiempos de espera. Diríjase a la Puerta {underloaded[0]} para un ingreso más rápido.",
            "fr": "Bienvenue à la Coupe du Monde de la FIFA ! La Porte {overloaded[0]} connaît un temps d'attente élevé. Veuillez vous diriger vers la Porte {underloaded[0]} pour une entrée plus rapide."
        }
    else:
        summary = "NORMAL OPERATIONS: All gates operating within standard load limits. Weather and incident indicators are stable."
        steps = [
            "Continue routine monitoring of turnstile entry rates.",
            "Verify concessions and volunteer posts are fully staffed for the current phase.",
            "Ensure emergency services vehicles remain on standby."
        ]
        announcements = {
            "en": "Welcome fans! We hope you are enjoying the match. Concessions and restrooms are fully open. Please report any issues to a stadium steward.",
            "es": "¡Bienvenidos aficionados! Esperamos que estén disfrutando del partido. Las concesiones y sanitarios están abiertos. Informe cualquier inconveniente a un comisario del estadio.",
            "fr": "Bienvenue aux supporters ! Nous espérons que vous appréciez le match. Les points de restauration et sanitaires sont ouverts. Signalez tout problème à un steward."
        }

    return {
        "summary": summary,
        "steps": steps,
        "announcements": announcements
    }


def _generate_mock_chat(
    message: str,
    history: list[dict[str, str]],
    gates: list[GateStatus],
    incident: IncidentReport,
    weather: WeatherContext,
    event_context: EventContext,
) -> str:
    """Generates realistic chat responses based on message keywords and stadium context."""
    msg = message.lower()

    overloaded_str = ", ".join([g.gate_id for g in gates if g.capacity_percent > 80.0]) or "None"
    underloaded_str = ", ".join([g.gate_id for g in gates if g.capacity_percent < 40.0]) or "None"

    if "lost" in msg or "child" in msg:
        return (
            "Lost Child Protocol: 1. Dispatch security officers to the reporter's zone (Zone B3). "
            "2. Note description: gender, age, clothing. 3. Paging notice can be made via PA: 'Lost child alert'. "
            f"4. Alert exit gates ({overloaded_str if overloaded_str != 'None' else 'North-A, North-B'}) to monitor departing groups."
        )
    elif "fire" in msg or "smoke" in msg or "evac" in msg:
        return (
            f"Fire/Evacuation Protocol for Zone {incident.zone}: 1. Verify source immediately via CCTV and dispatch zone supervisor. "
            f"2. Initiate localized evacuation alarm. 3. Direct crowd flow towards underloaded exits: {underloaded_str if underloaded_str != 'None' else 'South-A, South-B'}. "
            "4. Coordinate with transit dispatch to prepare buses/trains for egress surge."
        )
    elif "lightning" in msg or "storm" in msg or "weather" in msg:
        lightning_msg = f"lightning is currently at {weather.lightning_radius_km} km. Immediate shelter required!" if weather.lightning_detected else "no lightning is currently detected."
        return (
            f"Weather Protocol: The stadium weather index is {weather.temperature_celsius}°C (Heat index {weather.heat_index}°C). "
            f"Regarding lightning, {lightning_msg} Actions: 1. If lightning < 15km, suspend field activities. "
            "2. Direct fans to covered areas. 3. Alert medical for heat-related illness."
        )
    elif "gate" in msg or "redirect" in msg or "traffic" in msg or "crowd" in msg:
        return (
            f"Crowd Redirection: Overloaded gates: {overloaded_str}. Underloaded gates: {underloaded_str}. "
            "Action Plan: 1. Deploy stewards to plazas to guide fans. 2. Reprogram electronic signage to display directional arrows. "
            "3. Broadcast PA redirection announcement."
        )
    elif "hi" in msg or "hello" in msg or "help" in msg:
        return (
            "Hello! I am the GenAI Control Room Assistant. I have live access to the stadium gate feeds, weather monitors, "
            f"and active incident reports (currently: {incident.type} in Zone {incident.zone}). "
            "Ask me anything about emergency procedures, crowd rerouting, translations, or current stadium stats."
        )
    else:
        return (
            f"Operational Guidance: Current stadium phase is {event_context.phase.value} with "
            f"{event_context.occupied_seats}/{event_context.total_capacity} occupied seats. "
            f"To address your query: verify sector status in Zone {incident.zone}, check gate entry rates, "
            "and ensure PA announcements are coordinated. Let me know if you need specific announcements drafted."
        )
