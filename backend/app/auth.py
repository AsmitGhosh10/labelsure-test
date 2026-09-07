"""Authentication and role-based access control (PRD §30).

Deliberately dependency-free: PBKDF2-HMAC-SHA256 password hashing and
HMAC-SHA256 signed bearer tokens, both from the standard library. No new
supply-chain surface for a hackathon deployment, and nothing here is
home-grown cryptography - it is the stdlib primitives used the standard way.

Operational notes
-----------------
* ``AUTH_ENABLED`` (env, default ``false``) gates enforcement. Disabled, the
  API behaves exactly as before and every request runs as the anonymous
  ``inspector`` principal - the demo and the Gradio app keep working.
  Enabled, protected endpoints require a valid bearer token.
* ``AUTH_SECRET_KEY`` (env) signs tokens. If it is unset while auth is
  enabled, a random key is generated at start-up: tokens then die with the
  process, which is safe but means every restart forces re-login. Set it in
  production.
* Passwords are never logged, never returned, and never stored in plain text.
  The audit log records *usernames and outcomes*, never credentials.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, Header, HTTPException

from backend.app import database

# --- roles ------------------------------------------------------------------

INSPECTOR = "inspector"
SUPERVISOR = "supervisor"
ADMIN = "admin"
ROLES = (INSPECTOR, SUPERVISOR, ADMIN)

# Higher rank inherits every permission of the lower ranks.
ROLE_RANK = {INSPECTOR: 1, SUPERVISOR: 2, ADMIN: 3}

PBKDF2_ITERATIONS = 240_000
TOKEN_TTL_SECONDS = int(os.environ.get("AUTH_TOKEN_TTL_SECONDS", 8 * 3600))


def auth_enabled() -> bool:
    return os.environ.get("AUTH_ENABLED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


_runtime_secret: Optional[str] = None


def _secret_key() -> str:
    global _runtime_secret
    configured = os.environ.get("AUTH_SECRET_KEY", "").strip()
    if configured:
        return configured
    if _runtime_secret is None:
        # Ephemeral: tokens do not survive a restart. Never a fixed default -
        # a hardcoded fallback key would be a forgeable-token vulnerability.
        _runtime_secret = secrets.token_urlsafe(48)
    return _runtime_secret


# --- password hashing -------------------------------------------------------


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> Dict[str, Any]:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    )
    return {
        "password_hash": digest.hex(),
        "salt": salt,
        "iterations": iterations,
    }


def verify_password(password: str, password_hash: str, salt: str, iterations: int) -> bool:
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"), bytes.fromhex(salt), iterations
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), password_hash or "")


# --- tokens -----------------------------------------------------------------


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_token(username: str, role: str, ttl: int = TOKEN_TTL_SECONDS) -> Dict[str, Any]:
    issued = int(time.time())
    payload = {"sub": username, "role": role, "iat": issued, "exp": issued + ttl}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        _secret_key().encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    return {
        "access_token": f"{body}.{_b64e(signature)}",
        "token_type": "bearer",
        "expires_in": ttl,
        "role": role,
        "username": username,
    }


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify signature and expiry. Returns the payload or None."""
    if not token or "." not in token:
        return None
    body, _, signature = token.rpartition(".")
    expected = hmac.new(
        _secret_key().encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        provided = _b64d(signature)
    except Exception:
        return None
    if not hmac.compare_digest(expected, provided):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


# --- user management --------------------------------------------------------


def create_user(
    username: str,
    password: str,
    role: str,
    full_name: Optional[str] = None,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    username = (username or "").strip().lower()
    if not username:
        raise ValueError("Username is required")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    hashed = hash_password(password)
    user = database.upsert_user(
        username=username,
        role=role,
        full_name=full_name,
        **hashed,
    )
    database.write_audit(
        action="USER_CREATED",
        actor=actor or "system",
        actor_role=ADMIN,
        entity_type="user",
        entity_id=username,
        details={"role": role},
    )
    return user


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Return a token bundle, or None. Failures are audited without the
    attempted password."""
    username = (username or "").strip().lower()
    record = database.get_user_record(username)
    if record is None or not record.active:
        database.write_audit(
            action="LOGIN_FAILED",
            actor=username or "unknown",
            entity_type="user",
            entity_id=username,
            outcome="DENIED",
            details={"reason": "unknown_or_inactive_user"},
        )
        return None
    if not verify_password(
        password, record.password_hash, record.salt, record.iterations
    ):
        database.write_audit(
            action="LOGIN_FAILED",
            actor=username,
            actor_role=record.role,
            entity_type="user",
            entity_id=username,
            outcome="DENIED",
            details={"reason": "bad_password"},
        )
        return None
    token = create_token(record.username, record.role)
    database.write_audit(
        action="LOGIN",
        actor=record.username,
        actor_role=record.role,
        entity_type="user",
        entity_id=record.username,
    )
    return token


def bootstrap_admin() -> Optional[str]:
    """Create the initial admin from ``AUTH_BOOTSTRAP_USER`` /
    ``AUTH_BOOTSTRAP_PASSWORD`` when no users exist yet.

    No default credentials: without both env vars set, no account is created
    and the operator is expected to create one explicitly.
    """
    if database.count_users() > 0:
        return None
    username = os.environ.get("AUTH_BOOTSTRAP_USER", "").strip()
    password = os.environ.get("AUTH_BOOTSTRAP_PASSWORD", "")
    if not username or not password:
        return None
    try:
        create_user(username, password, ADMIN, full_name="Bootstrap admin", actor="bootstrap")
        return username
    except ValueError:
        return None


# --- FastAPI dependencies ---------------------------------------------------

ANONYMOUS = {"sub": "anonymous", "role": INSPECTOR, "anonymous": True}


def current_principal(
    authorization: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Resolve the caller.

    With auth disabled every caller is the anonymous inspector, so existing
    clients keep working. With auth enabled a valid bearer token is required.
    """
    if not auth_enabled():
        if authorization and authorization.lower().startswith("bearer "):
            payload = decode_token(authorization.split(" ", 1)[1].strip())
            if payload:
                return payload
        return dict(ANONYMOUS)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_role(*allowed: str):
    """Dependency factory enforcing a minimum role.

    Roles are ranked, so ``require_role(SUPERVISOR)`` also admits an admin.
    Denials are audited.
    """
    minimum = min(ROLE_RANK.get(r, 99) for r in allowed) if allowed else 1

    def dependency(principal: Dict[str, Any] = Depends(current_principal)) -> Dict[str, Any]:
        role = principal.get("role", INSPECTOR)
        # With enforcement off there is no identity to authorise against, so
        # nothing is gated - the deployment has opted out of access control.
        if not auth_enabled():
            return principal
        if ROLE_RANK.get(role, 0) < minimum:
            database.write_audit(
                action="ACCESS_DENIED",
                actor=principal.get("sub"),
                actor_role=role,
                outcome="DENIED",
                details={"required": list(allowed)},
            )
            raise HTTPException(
                status_code=403,
                detail=f"Requires role: {' or '.join(allowed)} (you are {role})",
            )
        return principal

    return dependency


def principal_id(principal: Dict[str, Any]) -> str:
    return str(principal.get("sub") or "anonymous")


def principal_role(principal: Dict[str, Any]) -> str:
    return str(principal.get("role") or INSPECTOR)


def describe() -> Dict[str, Any]:
    """Auth status for the health endpoint (never leaks the secret)."""
    return {
        "enabled": auth_enabled(),
        "roles": list(ROLES),
        "users": database.count_users(),
        "secret_configured": bool(os.environ.get("AUTH_SECRET_KEY", "").strip()),
        "token_ttl_seconds": TOKEN_TTL_SECONDS,
    }
