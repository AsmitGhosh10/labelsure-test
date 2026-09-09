"""Authentication and user administration (PRD §30).

Every outcome is audited. Passwords are never echoed, logged or returned.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app import auth, database
from backend.app.models import CreateUserRequest, LoginRequest

router = APIRouter()


@router.get("/auth/status")
def auth_status():
    """Whether auth is enforced, which roles exist, how many users are set up."""
    return auth.describe()


@router.post("/auth/login")
def login(payload: LoginRequest):
    token = auth.authenticate(payload.username, payload.password)
    if token is None:
        # Identical message for unknown user and wrong password - the response
        # must not tell an attacker which usernames exist.
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return token


@router.get("/auth/me")
def whoami(principal: Dict[str, Any] = Depends(auth.current_principal)):
    return {
        "username": principal.get("sub"),
        "role": principal.get("role"),
        "anonymous": bool(principal.get("anonymous", False)),
        "auth_enabled": auth.auth_enabled(),
    }


@router.get("/users")
def list_users(principal: Dict[str, Any] = Depends(auth.require_role(auth.ADMIN))):
    return {"users": database.list_users()}


@router.post("/users")
def create_user(
    payload: CreateUserRequest,
    principal: Dict[str, Any] = Depends(auth.require_role(auth.ADMIN)),
):
    try:
        return auth.create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            full_name=payload.full_name,
            actor=auth.principal_id(principal),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/admin/retention/purge")
def trigger_retention_purge(
    retention_days: Optional[int] = None,
    principal: Dict[str, Any] = Depends(auth.require_role(auth.ADMIN)),
):
    """Purge records older than retention_days (Admin only)."""
    purged = database.purge_expired_records(retention_days=retention_days)
    database.write_audit(
        action="DATA_RETENTION_PURGE",
        actor=auth.principal_id(principal),
        actor_role=auth.principal_role(principal),
        outcome="SUCCESS",
        details={
            "retention_days": retention_days or database.DEFAULT_RETENTION_DAYS,
            "purged": purged,
        },
    )
    return {
        "status": "success",
        "retention_days": retention_days or database.DEFAULT_RETENTION_DAYS,
        "purged": purged,
    }
