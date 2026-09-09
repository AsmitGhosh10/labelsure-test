"""HTTP contract tests for the FastAPI surface."""

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

pytest.importorskip("httpx", reason="httpx is required by fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import auth, database  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def stored(sample_result):
    database.save_inspection(sample_result)
    return sample_result


class TestHealthAndDocs:
    def test_health_reports_the_system_role(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["system_role"] == "AI-assisted compliance screening"
        assert "auth" in body

    def test_health_never_leaks_the_signing_secret(self, client, monkeypatch):
        monkeypatch.setenv("AUTH_SECRET_KEY", "leaky-secret-value")
        assert "leaky-secret-value" not in client.get("/health").text

    def test_openapi_schema_builds(self, client):
        assert client.get("/openapi.json").status_code == 200


class TestRegulationEndpoints:
    def test_corpus_stats(self, client):
        body = client.get("/regulations").json()
        assert body["chunks"] >= 31

    def test_search_returns_citations(self, client):
        body = client.get(
            "/regulations/search", params={"q": "retail sale price", "top_k": 3}
        ).json()
        assert body["count"] > 0
        assert body["results"][0]["citation"]["page"]

    def test_empty_query_is_rejected(self, client):
        assert client.get("/regulations/search", params={"q": "  "}).status_code == 422

    def test_unknown_rule_id_is_404(self, client):
        assert client.get("/regulations/NOPE-1").status_code == 404

    def test_post_search(self, client):
        body = client.post(
            "/regulations/search", json={"query": "net quantity", "top_k": 2}
        ).json()
        assert len(body["results"]) == 2


class TestInspectionRepository:
    def test_get_inspection(self, client, stored):
        body = client.get(f"/inspections/{stored['inspection_id']}").json()
        assert body["inspection_id"] == stored["inspection_id"]
        assert body["response_schema"] == "labelguard-inspection/1.1"

    def test_unknown_inspection_is_404(self, client):
        assert client.get("/inspections/no-such-id").status_code == 404

    def test_search_by_product(self, client, stored):
        body = client.get("/inspections/search", params={"product": "Crispy"}).json()
        assert body["count"] >= 1
        assert all("priority" in i for i in body["inspections"])

    def test_search_route_is_not_shadowed_by_the_id_route(self, client, stored):
        """/inspections/search must not be read as an inspection id."""
        response = client.get("/inspections/search")
        assert response.status_code == 200
        assert "inspections" in response.json()

    def test_search_with_no_matches_is_empty_not_error(self, client):
        body = client.get(
            "/inspections/search", params={"product": "zzz-nothing"}
        ).json()
        assert body["count"] == 0

    def test_markdown_report(self, client, stored):
        text = client.get(f"/inspections/{stored['inspection_id']}/report").text
        assert "# Compliance Inspection Report" in text
        assert "AI-ASSISTED COMPLIANCE SCREENING" in text.upper()

    def test_pdf_report(self, client, stored):
        response = client.get(f"/inspections/{stored['inspection_id']}/report.pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"

    def test_pdf_report_for_unknown_inspection_is_404(self, client):
        assert client.get("/inspections/nope/report.pdf").status_code == 404


class TestReviewEndpoints:
    def test_accept_then_read_back(self, client, stored):
        inspection_id = stored["inspection_id"]
        response = client.post(
            f"/inspections/{inspection_id}/decision",
            json={
                "action": "ACCEPT",
                "reason": "Checked against the physical package",
                "inspector_id": "api-insp-1",
                "inspector_name": "API Inspector",
            },
        )
        assert response.status_code == 200
        assert response.json()["agreement"] is True

        read_back = client.get(f"/inspections/{inspection_id}/decision").json()
        assert read_back["inspector_id"] == "api-insp-1"

    def test_missing_inspector_id_is_422_when_auth_is_off(self, client, stored):
        response = client.post(
            f"/inspections/{stored['inspection_id']}/decision",
            json={"action": "ACCEPT", "reason": "no id supplied"},
        )
        assert response.status_code == 422

    def test_override_without_a_verdict_is_422(self, client, stored):
        response = client.post(
            f"/inspections/{stored['inspection_id']}/decision",
            json={
                "action": "OVERRIDE",
                "reason": "the automated verdict is wrong here",
                "inspector_id": "api-insp-1",
            },
        )
        assert response.status_code == 422

    def test_decision_on_unknown_inspection_is_404(self, client):
        response = client.post(
            "/inspections/no-such-id/decision",
            json={"action": "ACCEPT", "reason": "x", "inspector_id": "i"},
        )
        assert response.status_code == 404

    def test_audit_endpoint_pairs_both_decisions(self, client, stored):
        inspection_id = stored["inspection_id"]
        client.post(
            f"/inspections/{inspection_id}/decision",
            json={
                "action": "ACCEPT",
                "reason": "Signed off after physical check",
                "inspector_id": "api-insp-2",
            },
        )
        body = client.get(f"/inspections/{inspection_id}/audit").json()
        assert body["ai_decision"] == stored["decision"]
        assert body["current_decision"]["inspector_id"] == "api-insp-2"
        assert body["audit_log"]

    def test_review_queue_is_sorted_least_confident_first(self, client):
        body = client.get("/review-queue").json()
        confidences = [
            i["confidence"] for i in body["queue"] if i["confidence"] is not None
        ]
        assert confidences == sorted(confidences)

    def test_audit_log_endpoint(self, client):
        assert "entries" in client.get("/audit-log").json()


class TestDashboard:
    def test_stats(self, client, stored):
        body = client.get("/stats").json()
        assert body["total_inspections"] >= 1
        assert "common_violations" in body
        assert "not a statutory inspection" in body["disclaimer"]

    def test_violation_breakdown_carries_citations(self, client, stored):
        body = client.get("/stats/violations").json()
        for row in body["violations"]:
            assert "rule_id" in row and "count" in row


class TestUploadValidation:
    def _post(self, client, filename, content, content_type):
        return client.post(
            "/inspect",
            files={"files": (filename, io.BytesIO(content), content_type)},
        )

    def test_executable_upload_is_rejected(self, client):
        response = self._post(client, "payload.exe", b"MZ\x90\x00", "application/x-msdownload")
        assert response.status_code == 422
        assert "Unsupported" in response.json()["detail"]

    def test_pdf_upload_is_rejected(self, client):
        response = self._post(client, "doc.pdf", b"%PDF-1.4", "application/pdf")
        assert response.status_code == 422

    def test_empty_file_is_rejected(self, client):
        response = self._post(client, "front.jpg", b"", "image/jpeg")
        assert response.status_code == 422

    def test_oversized_file_is_rejected(self, client, monkeypatch):
        from backend.app.routers import inspection as inspection_router

        monkeypatch.setattr(inspection_router, "MAX_UPLOAD_BYTES", 10)
        response = self._post(client, "front.jpg", b"0123456789abcdef", "image/jpeg")
        assert response.status_code == 413

    def test_too_many_surfaces_is_rejected(self, client):
        files = [
            ("files", (f"s{i}.jpg", io.BytesIO(b"\xff\xd8\xff"), "image/jpeg"))
            for i in range(7)
        ]
        assert client.post("/inspect", files=files).status_code == 422


class TestAuthEndpoints:
    def test_status_and_whoami_when_auth_is_off(self, client):
        assert client.get("/auth/status").json()["enabled"] is False
        assert client.get("/auth/me").json()["anonymous"] is True

    def test_login_with_bad_credentials_is_401(self, client):
        response = client.post(
            "/auth/login", json={"username": "ghost", "password": "wrongpassword"}
        )
        assert response.status_code == 401
        # the message must not reveal whether the username exists
        assert response.json()["detail"] == "Invalid username or password"

    def test_login_returns_a_usable_token(self, client):
        auth.create_user("api_user", "password123", auth.SUPERVISOR)
        body = client.post(
            "/auth/login", json={"username": "api_user", "password": "password123"}
        ).json()
        assert body["token_type"] == "bearer"
        assert auth.decode_token(body["access_token"])["role"] == auth.SUPERVISOR


class TestAuthEnforced:
    """With AUTH_ENABLED the protected routes actually gate."""

    @pytest.fixture
    def enforced_client(self, monkeypatch):
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH_SECRET_KEY", "api-test-secret")
        with TestClient(app) as c:
            yield c

    def test_protected_route_requires_a_token(self, enforced_client):
        assert enforced_client.get("/review-queue").status_code == 401

    def test_inspector_token_cannot_read_supervisor_stats(self, enforced_client):
        token = auth.create_token("i1", auth.INSPECTOR)["access_token"]
        response = enforced_client.get(
            "/stats", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403

    def test_supervisor_token_can_read_stats(self, enforced_client):
        token = auth.create_token("s1", auth.SUPERVISOR)["access_token"]
        response = enforced_client.get(
            "/stats", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200

    def test_decision_is_attributed_to_the_token_not_the_body(
        self, enforced_client, stored
    ):
        """A caller must not be able to sign off as somebody else."""
        token = auth.create_token("real-inspector", auth.INSPECTOR)["access_token"]
        response = enforced_client.post(
            f"/inspections/{stored['inspection_id']}/decision",
            json={
                "action": "ACCEPT",
                "reason": "Verified on the shelf",
                "inspector_id": "someone-else",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["decision"]["inspector_id"] == "real-inspector"

    def test_expired_token_is_rejected(self, enforced_client):
        token = auth.create_token("i1", auth.ADMIN, ttl=-10)["access_token"]
        response = enforced_client.get(
            "/stats", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    def test_user_admin_requires_admin_role(self, enforced_client):
        token = auth.create_token("s1", auth.SUPERVISOR)["access_token"]
        assert (
            enforced_client.get(
                "/users", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 403
        )
        admin = auth.create_token("a1", auth.ADMIN)["access_token"]
        assert (
            enforced_client.get(
                "/users", headers={"Authorization": f"Bearer {admin}"}
            ).status_code
            == 200
        )


class TestRAGEndpoints:
    def test_status_reports_the_backends(self, client):
        body = client.get("/rag").json()
        assert body["web_search"] is False
        assert body["generator"] in ("groq", "extractive")
        assert body["corpus"]["chunks"] >= 31

    def test_ask_returns_a_grounded_answer_with_sources(self, client):
        body = client.post(
            "/rag/ask", json={"query": "retail sale price declaration", "k": 3}
        ).json()
        assert body["grounded"] is True
        assert body["sources"]
        assert body["sources"][0]["metadata"]["rule"]
        assert body["used_web_search"] is False

    def test_empty_query_is_rejected(self, client):
        assert client.post("/rag/ask", json={"query": ""}).status_code == 422

    def test_k_is_bounded(self, client):
        assert client.post(
            "/rag/ask", json={"query": "net quantity", "k": 999}
        ).status_code == 422


class TestAnnotatedEvidence:
    def test_unknown_inspection_is_404(self, client):
        assert client.get("/inspections/nope/annotated/0").status_code == 404

    def test_out_of_range_index_is_404(self, client, stored):
        response = client.get(f"/inspections/{stored['inspection_id']}/annotated/99")
        assert response.status_code == 404

    def test_a_path_outside_the_evidence_directory_is_refused(self, client, stored):
        """A doctored record must not turn into an arbitrary file read."""
        import backend.app.database as db

        stored["annotated_images"] = [{"name": "x", "path": __file__, "boxes": []}]
        db.save_inspection(stored)
        response = client.get(f"/inspections/{stored['inspection_id']}/annotated/0")
        assert response.status_code == 404


class TestDocumentBrowsing:
    LMPCR = "The Legal Metrology (Packaged Commodities) Rules, 2011"

    def test_documents_are_listed_with_their_share_of_the_corpus(self, client):
        body = client.get("/regulations/documents").json()
        names = {d["document"]: d for d in body["documents"]}
        assert self.LMPCR in names
        assert names[self.LMPCR]["chunks"] == 31

    def test_a_document_can_be_browsed_without_a_query(self, client):
        body = client.get(
            "/regulations/search", params={"q": "", "document": self.LMPCR}
        ).json()
        assert body["count"] == 31
        assert body["document"] == self.LMPCR

    def test_a_browsed_clause_carries_no_score(self, client):
        """Browsing is not searching: nothing was ranked."""
        body = client.get(
            "/regulations/search", params={"q": "", "document": self.LMPCR}
        ).json()
        assert body["results"][0]["score"] is None

    def test_browsing_is_ordered_by_page(self, client):
        body = client.get(
            "/regulations/search", params={"q": "", "document": self.LMPCR}
        ).json()
        pages = [r["citation"]["page"] for r in body["results"]]
        assert pages == sorted(pages)

    def test_search_can_be_scoped_to_one_document(self, client):
        body = client.get(
            "/regulations/search",
            params={"q": "price", "top_k": 10, "document": self.LMPCR},
        ).json()
        assert body["count"] > 0
        assert all(r["citation"]["document"] == self.LMPCR for r in body["results"])

    def test_an_empty_query_with_no_document_is_still_rejected(self, client):
        assert client.get("/regulations/search", params={"q": "  "}).status_code == 422

    def test_an_unknown_document_is_empty_with_a_note(self, client):
        body = client.get(
            "/regulations/search", params={"q": "", "document": "No Such Gazette"}
        ).json()
        assert body["count"] == 0
        assert "No clauses indexed" in body["note"]

    def test_the_documents_route_is_not_read_as_a_rule_id(self, client):
        """/regulations/documents must not match /regulations/{rule_id}."""
        assert client.get("/regulations/documents").status_code == 200
