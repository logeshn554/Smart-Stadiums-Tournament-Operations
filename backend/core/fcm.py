import logging
import os
import sqlite3
from datetime import datetime, UTC
import httpx

logger = logging.getLogger(__name__)

# Fallback in-memory token list
_in_memory_tokens: list[str] = []

DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
DB_PATH = os.path.join(DB_DIR, "audit_log.db")


def is_sqlite_enabled() -> bool:
    """Check if the SQLite database is enabled and contains the fcm_tokens table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fcm_tokens'")
        res = cursor.fetchone()
        conn.close()
        return res is not None
    except Exception:
        return False


def add_token(token: str) -> None:
    """Store FCM registration token in SQLite or in-memory fallback."""
    if is_sqlite_enabled():
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO fcm_tokens (token, registered_at) VALUES (?, ?)",
                (token, datetime.now(UTC).isoformat()),
            )
            conn.commit()
            conn.close()
            logger.info("Successfully registered FCM token in SQLite.")
            return
        except Exception as exc:
            logger.error("Failed to insert FCM token in SQLite: %s. Using in-memory fallback.", exc)

    if token not in _in_memory_tokens:
        _in_memory_tokens.append(token)
        logger.info("Successfully registered FCM token in-memory.")


def get_tokens() -> list[str]:
    """Retrieve all active registered FCM tokens."""
    if is_sqlite_enabled():
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT token FROM fcm_tokens")
            rows = cursor.fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception as exc:
            logger.error("Failed to select FCM tokens from SQLite: %s", exc)

    return list(_in_memory_tokens)


async def send_fcm_notification(title: str, body: str) -> None:
    """Send FCM notification to all registered tokens using the FCM Legacy HTTP API."""
    fcm_server_key = os.getenv("FCM_SERVER_KEY")
    if not fcm_server_key:
        logger.info("FCM_SERVER_KEY not configured. Skipping push alert.")
        return

    tokens = get_tokens()
    if not tokens:
        logger.info("No registered FCM tokens. Skipping push alert.")
        return

    headers = {
        "Authorization": f"key={fcm_server_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "registration_ids": tokens,
        "notification": {
            "title": title,
            "body": body,
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://fcm.googleapis.com/fcm/send",
                headers=headers,
                json=payload,
                timeout=10.0,
            )
            if response.status_code == 200:
                res_data = response.json()
                results = res_data.get("results", [])
                stale_tokens = []
                for i, result in enumerate(results):
                    error = result.get("error")
                    if error in ("NotRegistered", "InvalidRegistration"):
                        stale_tokens.append(tokens[i])

                if stale_tokens:
                    logger.info("Cleaning up %d stale FCM tokens.", len(stale_tokens))
                    if is_sqlite_enabled():
                        try:
                            conn = sqlite3.connect(DB_PATH)
                            cursor = conn.cursor()
                            cursor.executemany(
                                "DELETE FROM fcm_tokens WHERE token = ?",
                                [(t,) for t in stale_tokens],
                            )
                            conn.commit()
                            conn.close()
                        except Exception as exc:
                            logger.error("Failed to clean up stale FCM tokens in SQLite: %s", exc)

                    global _in_memory_tokens
                    _in_memory_tokens = [t for t in _in_memory_tokens if t not in stale_tokens]
            else:
                logger.error("FCM legacy API returned status code %d: %s", response.status_code, response.text)
    except Exception as exc:
        logger.error("Failed to send FCM messages: %s", exc)
