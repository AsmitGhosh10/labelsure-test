"""Authentication and role-based access control (PRD §30)."""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi import HTTPException

from backend.app import auth, database


@pytest.fixture
def enforced(monkeypatch):
    """Auth switched on for the duration of one test."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_SECRET_KEY", "unit-test-secret")
    yield


class TestPasswordHashing:
    def test_hash_verifies_and_is_salted(self):
        a = auth.hash_password("correct horse battery")
        b = auth.hash_password("correct horse battery")
        assert a["salt"] != b["salt"], "each hash must use a fresh salt"
        assert a["password_hash"] != b["password_hash"]
        assert auth.verify_password(
            "correct horse battery", a["password_hash"], a["salt"], a["iterations"]
        )

    def test_wrong_password_fails(self):
        h = auth.hash_password("correct horse battery")
        assert not auth.verify_password(
            "wrong password", h["password_hash"], h["salt"], h["iterations"]
        )

    def test_plaintext_is_never_stored(self):
        h = auth.hash_password("supersecret123")
        assert "supersecret123" not in h["password_hash"]
        assert "supersecret123" not in h["salt"]

    def test_short_passwords_are_rejected(self):
        with pytest.raises(ValueError, match="8 characters"):
            auth.hash_password("short")

    def test_malformed_stored_hash_does_not_crash(self):
        assert not auth.verify_password("anything", "not-hex", "not-hex", 1000)


class TestTokens:
    def test_roundtrip(self, enforced):
        token = auth.create_token("alice", auth.SUPERVISOR)
        payload = auth.decode_token(token["access_token"])
        assert payload["sub"] == "alice"
        assert payload["role"] == auth.SUPERVISOR

    def test_tampered_payload_is_rejected(self, enforced):
        token = auth.create_token("alice", auth.INSPECTOR)["access_token"]
        body, _, signature = token.rpartition(".")
        forged = auth.create_token("alice", auth.ADMIN)["access_token"].split(".")[0]
        assert auth.decode_token(f"{forged}.{signature}") is None

    def test_expired_token_is_rejected(self, enforced):
        token = auth.create_token("alice", auth.INSPECTOR, ttl=-1)
        assert auth.decode_token(token["access_token"]) is None

    def test_garbage_token_is_rejected(self, enforced):
        assert auth.decode_token("") is None
        assert auth.decode_token("nonsense") is None
        assert auth.decode_token("a.b") is None

    def test_a_token_signed_with_another_key_is_rejected(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "key-one")
        token = auth.create_token("alice", auth.ADMIN)["access_token"]
        monkeypatch.setenv("AUTH_SECRET_KEY", "key-two")
        assert auth.decode_token(token) is None


class TestAuthentication:
    def test_login_succeeds_for_a_valid_user(self):
        auth.create_user("t_valid", "password123", auth.INSPECTOR)
        token = auth.authenticate("t_valid", "password123")
        assert token and token["role"] == auth.INSPECTOR

    def test_login_fails_for_a_wrong_password(self):
        auth.create_user("t_wrong", "password123", auth.INSPECTOR)
        assert auth.authenticate("t_wrong", "nope") is None

    def test_login_fails_for_an_unknown_user(self):
        assert auth.authenticate("no_such_user_at_all", "password123") is None

    def test_failed_logins_are_audited_without_the_password(self):
        auth.authenticate("t_audit_user", "hunter2-secret-value")
        entries = database.read_audit(action="LOGIN_FAILED", limit=20)
        assert entries
        assert all(
            "hunter2-secret-value" not in str(e["details"]) for e in entries
        ), "the attempted password must never reach the audit log"

    def test_inactive_user_cannot_log_in(self):
        hashed = auth.hash_password("password123")
        database.upsert_user(
            username="t_inactive", role=auth.INSPECTOR, active=False, **hashed
        )
        assert auth.authenticate("t_inactive", "password123") is None

    def test_user_listing_never_exposes_the_hash(self):
        auth.create_user("t_listed", "password123", auth.ADMIN)
        for user in database.list_users():
            assert "password_hash" not in user
            assert "salt" not in user


class TestRBAC:
    def test_higher_roles_inherit_lower_permissions(self, enforced):
        dependency = auth.require_role(auth.SUPERVISOR)
        assert dependency({"sub": "s", "role": auth.SUPERVISOR})
        assert dependency({"sub": "a", "role": auth.ADMIN})

    def test_insufficient_role_is_denied(self, enforced):
        dependency = auth.require_role(auth.SUPERVISOR)
        with pytest.raises(HTTPException) as exc:
            dependency({"sub": "i", "role": auth.INSPECTOR})
        assert exc.value.status_code == 403

    def test_denials_are_audited(self, enforced):
        dependency = auth.require_role(auth.ADMIN)
        with pytest.raises(HTTPException):
            dependency({"sub": "denied-user", "role": auth.INSPECTOR})
        assert database.read_audit(actor="denied-user", action="ACCESS_DENIED")

    def test_missing_token_is_rejected_when_enforced(self, enforced):
        with pytest.raises(HTTPException) as exc:
            auth.current_principal(authorization=None)
        assert exc.value.status_code == 401

    def test_bad_scheme_is_rejected_when_enforced(self, enforced):
        with pytest.raises(HTTPException) as exc:
            auth.current_principal(authorization="Basic abc123")
        assert exc.value.status_code == 401

    def test_valid_token_is_accepted_when_enforced(self, enforced):
        token = auth.create_token("bob", auth.SUPERVISOR)["access_token"]
        principal = auth.current_principal(authorization=f"Bearer {token}")
        assert principal["sub"] == "bob"

    def test_disabled_auth_admits_everyone_as_inspector(self, monkeypatch):
        monkeypatch.setenv("AUTH_ENABLED", "false")
        principal = auth.current_principal(authorization=None)
        assert principal["role"] == auth.INSPECTOR
        assert principal["anonymous"] is True
        # and nothing is gated
        assert auth.require_role(auth.ADMIN)(principal)


class TestBootstrap:
    def test_no_default_credentials_are_ever_created(self, monkeypatch):
        """Absent explicit env configuration, no account exists to guess."""
        monkeypatch.delenv("AUTH_BOOTSTRAP_USER", raising=False)
        monkeypatch.delenv("AUTH_BOOTSTRAP_PASSWORD", raising=False)
        assert auth.bootstrap_admin() is None

    def test_describe_never_leaks_the_secret(self, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "a-very-secret-value")
        described = auth.describe()
        assert "a-very-secret-value" not in str(described)
        assert described["secret_configured"] is True


class TestAccountLockout:
    def test_account_locks_after_5_failed_attempts(self):
        auth.create_user("lockout_user", "password123", auth.INSPECTOR)
        # 4 failed attempts -> still unlocked
        for _ in range(4):
            assert auth.authenticate("lockout_user", "wrong_pass") is None
            assert not auth.is_account_locked("lockout_user")

        # 5th failed attempt -> locks account
        assert auth.authenticate("lockout_user", "wrong_pass") is None
        assert auth.is_account_locked("lockout_user") is True

        # Even correct password fails while locked
        assert auth.authenticate("lockout_user", "password123") is None

        # Clean up
        auth._clear_failed_attempts("lockout_user")
        assert auth.authenticate("lockout_user", "password123") is not None
