import logging
import os
import sqlite3
import json
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

# Fallback in-memory token list
_in_memory_tokens: list[str] = []

DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
DB_PATH = os.path.join(DB_DIR, "audit_log.db")

# Firebase Admin app instance (singleton)
_firebase_app = None


def _init_firebase_admin():
    """Initialize Firebase Admin SDK using service account credentials from env vars."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials

        # Support two modes:
        # 1. FIREBASE_SERVICE_ACCOUNT_JSON env var containing the full service account JSON string
        # 2. GOOGLE_APPLICATION_CREDENTIALS env var pointing to a service account JSON file path
        sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        if sa_json:
            sa_dict = json.loads(sa_json)
            cred = credentials.Certificate(sa_dict)
        else:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if not cred_path:
                logger.info(
                    "No Firebase service account credentials configured "
                    "(FIREBASE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS). "
                    "FCM push notifications will be skipped."
                )
                return None
            cred = credentials.Certificate(cred_path)

        if not firebase_admin._apps:
            _firebase_app = firebase_admin.initialize_app(cred)
        else:
            _firebase_app = firebase_admin.get_app()
        logger.info("Firebase Admin SDK initialized successfully.")
        return _firebase_app
    except Exception as exc:
        logger.error("Failed to initialize Firebase Admin SDK: %s", exc)
        return None


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


def _delete_stale_tokens(stale_tokens: list[str]) -> None:
    """Remove stale/expired FCM tokens from SQLite and in-memory store."""
    global _in_memory_tokens
    if not stale_tokens:
        return

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

    _in_memory_tokens = [t for t in _in_memory_tokens if t not in stale_tokens]


async def send_fcm_notification(title: str, body: str) -> None:
    """Send FCM push notification to all registered tokens using Firebase Admin SDK (HTTP v1 API)."""
    app = _init_firebase_admin()
    if app is None:
        logger.info("Firebase Admin SDK not initialized. Skipping push alert.")
        return

    tokens = get_tokens()
    if not tokens:
        logger.info("No registered FCM tokens. Skipping push alert.")
        return

    try:
        from firebase_admin import messaging

        stale_tokens: list[str] = []

        # Send to each token individually (MulticastMessage is more reliable per token)
        for token in tokens:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                token=token,  # Registration token for the target device
            )
            try:
                messaging.send(msg)
                logger.info("FCM notification sent successfully to token: %s…", token[:20])
            except messaging.UnregisteredError:
                stale_tokens.append(token)
                logger.warning("FCM token is unregistered (stale): %s…", token[:20])
            except Exception as exc:
                logger.error("Failed to send FCM to token %s…: %s", token[:20], exc)

        _delete_stale_tokens(stale_tokens)

    except Exception as exc:
        logger.error("FCM send_fcm_notification error: %s", exc)
