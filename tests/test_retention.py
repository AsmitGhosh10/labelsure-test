"""Tests for data retention policy (§30)."""

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app import database, auth


def test_purge_expired_records():
    # Insert old record
    old_ts = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    database.init_db()
    with database.SessionLocal() as session:
        session.add(
            database.InspectionRow(
                inspection_id="old_insp_001",
                timestamp=old_ts,
                decision="COMPLIANT",
            )
        )
        session.add(
            database.InspectionRow(
                inspection_id="new_insp_001",
                timestamp=new_ts,
                decision="COMPLIANT",
            )
        )
        session.commit()

    purged = database.purge_expired_records(retention_days=365)
    assert purged["inspections"] >= 1

    with database.SessionLocal() as session:
        assert session.get(database.InspectionRow, "old_insp_001") is None
        assert session.get(database.InspectionRow, "new_insp_001") is not None


def test_admin_retention_purge_endpoint():
    client = TestClient(app)
    # Auth is disabled by default in test env unless enabled
    res = client.post("/admin/retention/purge", json={"retention_days": 365})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "purged" in body
