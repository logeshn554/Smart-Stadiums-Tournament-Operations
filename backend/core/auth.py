"""
RS256 JWT authentication module for StadiumOps AI.

Provides token generation and verification using RSA-256 asymmetric keys.
In production, the private key is used by an identity provider (IdP) to
sign tokens; the API only needs the public key to verify them.

For this deployment a self-signed key pair is generated at startup when
no keys are found on disk.  This demonstrates real cryptographic auth
without requiring external infrastructure.

Security Design:
    - Asymmetric RS256 — private key never leaves the signing authority.
    - Short-lived tokens (default 60 min) with ``exp`` and ``iat`` claims.
    - Role claim (``role``) embedded in the JWT payload.
    - Token verification rejects expired, malformed, and re-signed tokens.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# ── Key file paths ────────────────────────────────────────────────────────

_KEYS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "keys")
_PRIVATE_KEY_PATH = os.path.join(_KEYS_DIR, "private.pem")
_PUBLIC_KEY_PATH = os.path.join(_KEYS_DIR, "public.pem")

ALGORITHM = "RS256"
TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


def _generate_rsa_keypair() -> tuple[str, str]:
    """Generate an RSA-2048 key pair and persist to disk.

    Creates the ``keys/`` directory if it does not exist and writes
    ``private.pem`` and ``public.pem`` in PEM format.

    Returns:
        A tuple of (private_key_pem, public_key_pem) as strings.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    os.makedirs(_KEYS_DIR, exist_ok=True)
    with open(_PRIVATE_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(private_pem)
    with open(_PUBLIC_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(public_pem)

    logger.info("Generated new RSA-2048 key pair in %s", _KEYS_DIR)
    return private_pem, public_pem


def _load_keys() -> tuple[str, str]:
    """Load or generate the RSA key pair.

    Attempts to read existing PEM files from the ``keys/`` directory.
    If either file is missing, a fresh key pair is generated.

    Returns:
        A tuple of (private_key_pem, public_key_pem) as strings.
    """
    if os.path.exists(_PRIVATE_KEY_PATH) and os.path.exists(_PUBLIC_KEY_PATH):
        with open(_PRIVATE_KEY_PATH, encoding="utf-8") as f:
            private_pem = f.read()
        with open(_PUBLIC_KEY_PATH, encoding="utf-8") as f:
            public_pem = f.read()
        logger.info("Loaded existing RSA key pair from %s", _KEYS_DIR)
        return private_pem, public_pem

    return _generate_rsa_keypair()


PRIVATE_KEY, PUBLIC_KEY = _load_keys()


def create_access_token(
    role: str,
    subject: str = "stadiumops-user",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        role: The user role to embed (e.g. 'admin', 'viewer').
        subject: The token subject (default 'stadiumops-user').
        extra_claims: Optional additional claims to merge into the payload.

    Returns:
        A signed JWT string.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(payload, PRIVATE_KEY, algorithm=ALGORITHM)
    logger.debug("Created JWT for sub=%s role=%s", subject, role)
    return token


def verify_token(token: str) -> dict[str, Any]:
    """Verify and decode a JWT access token.

    Args:
        token: The raw JWT string from the Authorization header.

    Returns:
        The decoded payload dict containing claims.

    Raises:
        ValueError: If the token is expired, malformed, or has an invalid
            signature.
    """
    try:
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=[ALGORITHM])
        logger.debug("Verified JWT for sub=%s", payload.get("sub"))
        return payload
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise ValueError(f"Invalid or expired token: {exc}") from exc
