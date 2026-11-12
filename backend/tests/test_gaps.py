"""Tests for the gap-closure work: auth, tenancy, recovery, dual approval, intake, worker, admin, exports."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import DatabaseError

from app import worker
from app.db import utcnow
from app.models import AuditEvent, OutboxEvent, SandboxRecord, SourceDocument
from app.seed import ASTER_BRIEF


def make_pdf(pages: list[str]) -> bytes:
    """Minimal valid PDF with one text line per page (Helvetica), correct xref offsets."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        safe = text.replace("\\", "").replace("(", "").replace(")", "")
        stream = f"BT /F1 11 Tf 50 750 Td ({safe}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


# ---------- auth & tenancy ----------
def test_password_login_session_and_csrf(app):
    c = TestClient(app)
    assert c.post("/api/v1/auth/login", json={"username": "nadia", "password": "wrong"}).status_code == 401
    r = c.post("/api/v1/auth/login", json={"username": "nadia", "password": "decisionflow-demo"})
    assert r.status_code == 200 and "df_session" in r.cookies
    csrf = r.json()["csrf_token"]
    assert c.get("/api/v1/auth/me").json()["user"]["modules"] == ["cases", "approvals", "workflows"]
    body = {"title": "Test case", "client_name": "Client", "brief": "Target: 10 leads, budget Rp10 juta, 2 weeks."}
    no_csrf = c.post("/api/v1/cases", json=body)
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "CSRF_FAILED"
    assert c.post("/api/v1/cases", json=body, headers={"X-CSRF-Token": csrf}).status_code == 201
    assert c.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert c.get("/api/v1/auth/me").status_code == 401


def test_other_tenant_cannot_see_or_touch_cases(api):
    code = api.create_aster()
    assert api.get(f"/cases/{code}", user="u_omar").status_code == 404
    assert api.get("/cases", user="u_omar").json()["total"] == 0
    r = api.patch(f"/cases/{code}/requirements/budget", {"action": "confirm"}, user="u_omar")
    assert r.status_code == 404
    own = api.create_aster(user="u_omar")
    assert api.get(f"/cases/{own}").status_code == 404  # and the other way round


# ---------- business-rule gaps ----------
def test_expired_rate_card_blocks_approval_and_execution(api):
    code, pkg = api.ready_package()
    api.approve(pkg)
    api.authorize(pkg)
    card = {"unit_cost_conservative_idr": 40000, "unit_cost_expected_idr": 36000, "unit_cost_aggressive_idr": 32000,
            "fixed_cost_idr": 12000000, "margin_floor_bp": 1500, "capacity_leads_per_week": 400}
    assert api.post("/admin/rate-cards", card, user="u_nadia").status_code == 403
    assert api.post("/admin/rate-cards", card, user="u_bima").status_code == 201
    r = api.post(f"/packages/{pkg['id']}/runs", {"simulate": "none"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RATE_CARD_EXPIRED"
    assert api.get(f"/packages/{pkg['id']}").json()["rate_card_expired"] is True


def test_clarification_evidence_is_labelled_by_verification(api, db):
    code = api.create_aster()
    api.confirm_drafts(code)
    api.post(f"/cases/{code}/clarifications/suggest")
    qs = {q["requirement_key"]: q for q in api.get(f"/cases/{code}/clarifications").json()}
    bad = api.post(f"/cases/{code}/clarifications/{qs['geography']['id']}/answer",
                   {"answer": "Indonesia", "answered_source": "Maya", "channel": "call", "reference": ""})
    assert bad.status_code == 422  # a checkable reference is required
    api.post(f"/cases/{code}/clarifications/{qs['geography']['id']}/answer",
             {"answer": "Indonesia — Jabodetabek", "answered_source": "Maya", "channel": "call",
              "reference": "Call 10 Nov 15:00 WIB"})
    api.post(f"/cases/{code}/clarifications/{qs['lead_definition']['id']}/answer",
             {"answer": "Managers at SaaS firms", "answered_source": "Maya", "channel": "email",
              "reference": "Email 'Re: criteria' 10 Nov", "client_excerpt": "A qualified lead is a manager at a SaaS firm."})
    docs = {d["title"].split(" — ")[0]: d for d in api.get(f"/cases/{code}").json()["documents"]}
    verif = sorted(d["verification"] for k, d in docs.items() if k.startswith("Clarification"))
    assert verif == ["analyst_recorded", "client_text"]
    assert api.req(code, "lead_definition")["source"]["quote"] == "A qualified lead is a manager at a SaaS firm."
    api.price(code)
    pkg = api.post(f"/cases/{code}/packages").json()
    risks = api.get(f"/packages/{pkg['id']}").json()["content"]["risks"]
    assert any("analyst's record of a call" in r for r in risks)


def test_stale_versions_get_409(api):
    code = api.create_aster()
    budget = api.req(code, "budget")
    assert api.patch(f"/cases/{code}/requirements/budget", {"action": "confirm", "version": budget["version"]}).status_code == 200
    stale = api.patch(f"/cases/{code}/requirements/budget",
                      {"action": "edit", "value": "1", "reason": "typo fix", "version": budget["version"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"
    f = api.get(f"/cases/{code}/feasibility").json()
    first = api.post(f"/cases/{code}/feasibility", {"inputs": f["inputs"], "check_base": True,
                                                    "based_on_run_id": None})
    assert first.status_code == 201
    again = api.post(f"/cases/{code}/feasibility", {"inputs": f["inputs"], "check_base": True, "based_on_run_id": None})
    assert again.status_code == 409


def test_rejected_case_is_locked_until_reopened(api):
    code, pkg = api.ready_package()
    api.post(f"/packages/{pkg['id']}/review", {"decision": "REJECT", "note": "Budget unconfirmed",
                                               "package_hash": pkg["content_hash"], "version": 1}, user="u_arif")
    r = api.patch(f"/cases/{code}/requirements/target_leads", {"action": "edit", "value": "2500", "reason": "smaller"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CASE_LOCKED"
    assert api.post(f"/cases/{code}/packages").json()["error"]["code"] == "CASE_LOCKED"
    detail = api.post(f"/cases/{code}/reopen", {"reason": "Procurement confirmed the budget"}).json()
    assert detail["lock_reason"] is None and detail["reopen_count"] == 1
    api.price(code)
    v2 = api.post(f"/cases/{code}/packages").json()
    assert v2["version"] == 2 and v2["state"] == "IN_REVIEW"


def test_cancelled_run_lists_compensation_and_case_can_be_reopened(api, db):
    code, pkg = api.ready_package()
    api.approve(pkg)
    api.authorize(pkg)
    run = api.run(pkg, "tracker_timeout_after_commit")
    assert run["status"] == "UNKNOWN_OUTCOME"
    assert api.post(f"/runs/{run['code']}/cancel", {"reason": "short"}, user="u_jordan").status_code == 422
    run = api.run_action(run["code"], "cancel", {"reason": "Client paused the campaign before launch"})
    assert run["status"] == "CANCELLED"
    assert run["incident"]["compensation"] == [{"step": "Create CRM opportunity", "external_ref": "OPP-SBX-00001"}]
    assert api.get(f"/cases/{code}").json()["status"] == "CANCELLED"
    assert api.post(f"/runs/{run['code']}/steps/tracker.create_project/retry", user="u_jordan").status_code == 409
    assert api.post(f"/cases/{code}/reopen", {"reason": "Campaign restarts next month"}).status_code == 200
    s = db()
    assert s.scalar(select(func.count()).select_from(SandboxRecord)) == 2  # nothing was silently deleted


def test_manual_resolution_continues_the_run(api):
    code, pkg = api.ready_package()
    api.approve(pkg)
    api.authorize(pkg)
    run = api.run(pkg, "tracker_timeout_before_commit")
    body = {"external_ref": "PRJ-MANUAL-1", "note": "Created the project by hand in the tracker UI"}
    assert api.post(f"/runs/{run['code']}/steps/tracker.create_project/resolve", body).status_code == 403  # analyst
    run = api.run_action(run["code"], "steps/tracker.create_project/resolve", body)
    assert run["status"] == "SUCCEEDED"
    verify = next(s for s in run["steps"] if s["key"] == "verify_receipts")
    assert "confirmed manually by an operator" in verify["attempt_log"][-1]["detail"]
    inc = api.post(f"/runs/{run['code']}/escalate", {"reason": "after the fact"}, user="u_jordan")
    assert inc.status_code == 409  # closed runs cannot be escalated


def test_disabled_connector_blocks_authorization(api):
    code, pkg = api.ready_package()
    api.approve(pkg)
    assert api.patch("/admin/connectors/tracker", {"enabled": False, "reason": "maintenance"}, user="u_jordan").status_code == 403
    assert api.patch("/admin/connectors/tracker", {"enabled": False, "reason": "maintenance"}, user="u_bima").status_code == 200
    actions = [a["action"] for a in api.get(f"/packages/{pkg['id']}").json()["content"]["proposed_actions"]]
    r = api.post(f"/packages/{pkg['id']}/authorize", {"package_hash": pkg["content_hash"], "confirmed_actions": actions},
                 user="u_arif")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONNECTOR_DISABLED"


# ---------- dual approval, capacity, exception, options ----------
def test_below_floor_needs_exception_and_two_different_approvers(api):
    code = api.create_aster()
    api.confirm_drafts(code)
    api.clarify_missing(code)
    api.price(code, proposed_fee_idr=125_000_000)  # 6.4 % margin
    r = api.post(f"/cases/{code}/packages")
    assert r.status_code == 422 and r.json()["error"]["code"] == "EXCEPTION_REQUIRED"
    pkg = api.post(f"/cases/{code}/packages", {"exception_reason": "Strategic logo; follow-on quarter at standard rate"}).json()
    assert pkg["risk_level"] == "HIGH" and pkg["required_approvals"] == 2
    first = api.approve(pkg, "u_arif", "Exception accepted")
    assert first["package_state"] == "IN_REVIEW"
    again = api.post(f"/packages/{pkg['id']}/review", {"decision": "APPROVE", "note": "again",
                                                       "package_hash": pkg["content_hash"], "version": 1}, user="u_arif")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_APPROVED"
    second = api.approve(pkg, "u_sari", "Finance agrees")
    assert second["package_state"] == "APPROVED"
    content = api.get(f"/packages/{pkg['id']}").json()["content"]
    assert content["exception"]["reason"].startswith("Strategic logo")


def test_capacity_blocks_package_and_options_are_compared(api):
    code = api.create_aster()
    api.confirm_drafts(code)
    api.clarify_missing(code)
    f = api.get(f"/cases/{code}/feasibility").json()
    a = f["assessment"]
    assert a["capacity"] == {"required_per_week": 375, "capacity_per_week": 400, "utilization_pct": 94}
    assert {k: v["margin_pct"] for k, v in a["scenario_comparison"].items()} == {
        "conservative": "15.00%", "expected": "22.00%", "aggressive": "29.00%"}
    api.price(code, duration_weeks=6)  # 500 per week > 400
    r = api.post(f"/cases/{code}/packages")
    assert any(b["code"] == "CAPACITY_EXCEEDED" for b in r.json()["error"]["details"]["blockers"])
    api.price(code, duration_weeks=8)
    pkg = api.post(f"/cases/{code}/packages").json()
    content = api.get(f"/packages/{pkg['id']}").json()["content"]
    assert [o["recommended"] for o in content["options"]] == [False, True, False]
    assert any(g["fit"] == "Standard" for g in content["fit_gap"])


# ---------- intake ----------
def _upload(api, name, data, user="u_nadia"):
    c, csrf = api.client(user)
    return c.post("/api/v1/cases/upload", data={"title": "Uploaded brief", "client_name": "Aster Labs"},
                  files={"file": (name, data)}, headers={"X-CSRF-Token": csrf})


def test_pdf_upload_keeps_pages_and_rejects_scans(api):
    pdf = make_pdf(["Target: 3,000 qualified leads", "Budget: Rp150.000.000 Timeline: 8 weeks"])
    r = _upload(api, "brief.pdf", pdf)
    assert r.status_code == 201, r.text
    d = api.get(f"/cases/{r.json()['code']}").json()
    brief = next(x for x in d["documents"] if x["kind"] == "brief")
    assert brief["artifact"]["pages"] == 2 and len(brief["page_breaks"]) == 1
    assert api.req(r.json()["code"], "budget")["source"]["start"] >= brief["page_breaks"][0]  # budget is on page 2
    assert api.get(f"/artifacts/{brief['artifact_id']}").content == pdf
    scanned = _upload(api, "scan.pdf", make_pdf(["", ""]))
    assert scanned.status_code == 422 and scanned.json()["error"]["code"] == "NO_TEXT"
    assert _upload(api, "evil.exe", b"MZ....").json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_eml_upload(api):
    eml = (b"Subject: Lead campaign\r\nFrom: maya@example.test\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
           b"Target: 2,000 qualified leads\r\nBudget: Rp80.000.000\r\nTimeline: 6 weeks\r\n")
    r = _upload(api, "brief.eml", eml)
    assert r.status_code == 201
    assert api.req(r.json()["code"], "target_leads")["value"] == "2000"


def test_reextract_keeps_human_decisions(api):
    code = api.create_aster()
    budget = api.req(code, "budget")
    api.patch(f"/cases/{code}/requirements/budget", {"action": "edit", "value": "140000000", "reason": "negotiated",
                                                     "version": budget["version"]})
    r = api.post(f"/cases/{code}/extract").json()
    assert r["changed"] == 0
    assert api.req(code, "budget")["value"] == "140000000"


# ---------- worker ----------
def test_duplicate_delivery_and_lease_expiry_do_not_duplicate_writes(api, db):
    code, pkg = api.ready_package()
    api.approve(pkg)
    api.authorize(pkg)
    r = api.post(f"/packages/{pkg['id']}/runs", {"simulate": "none"})
    run_code = r.json()["code"]
    eid = worker.claim(db)  # a worker claims the event and "crashes" before processing it
    assert eid is not None and worker.claim(db) is None  # the lease prevents a second claim
    s = db()
    s.execute(update(OutboxEvent).where(OutboxEvent.id == eid).values(claimed_at=utcnow() - timedelta(minutes=5)))
    s.add(OutboxEvent(organization_id="org_northstar", kind="run.advance", run_id=s.get(OutboxEvent, eid).run_id,
                      actor_id="u_nadia"))  # duplicate delivery of the same work
    s.commit()
    assert worker.drain(db) == 2
    assert api.get(f"/runs/{run_code}").json()["status"] == "SUCCEEDED"
    assert s.scalar(select(func.count()).select_from(SandboxRecord)) == 2


# ---------- notifications, exports, audit, tracing, paging ----------
def test_notifications_follow_the_workflow(api):
    code, pkg = api.ready_package()
    inbox = api.get("/notifications", user="u_arif").json()
    assert inbox["unread"] >= 1 and inbox["items"][0]["link"] == f"/approvals/{pkg['id']}"
    api.post("/notifications/read", user="u_arif")
    assert api.get("/notifications", user="u_arif").json()["unread"] == 0
    api.approve(pkg)
    assert any("approved" in n["title"] for n in api.get("/notifications").json()["items"])


def test_exports_carry_the_hash(api):
    code, pkg = api.ready_package()
    md = api.get(f"/packages/{pkg['id']}/export.md")
    assert md.status_code == 200 and pkg["content_hash"] in md.text and "SYNTHETIC" in md.text
    js = api.get(f"/packages/{pkg['id']}/export.json").json()
    assert js["content_hash"] == pkg["content_hash"]
    api.approve(pkg)
    api.authorize(pkg)
    run = api.run(pkg)
    assert api.get(f"/runs/{run['code']}/log.json").json()["status"] == "SUCCEEDED"
    csv = api.get("/impact/export.csv", user="u_dewi")
    assert csv.status_code == 200 and csv.text.startswith("code,period")


def test_audit_is_append_only_and_traced(api, db):
    api.create_aster()
    s = db()
    with pytest.raises(DatabaseError, match="append-only"):
        s.execute(update(AuditEvent).values(summary="rewritten"))
        s.commit()
    s.rollback()
    r = api.get("/audit", user="u_lia").json()
    assert r["total"] >= 2 and all(e["request_id"] for e in r["items"] if e["actor"])
    assert api.get("/audit", user="u_nadia").status_code == 403
    err = api.get("/cases/DCF-9999")
    assert err.headers["X-Request-ID"] == err.json()["error"]["request_id"]


def test_pagination(api):
    for _ in range(3):
        api.create_aster()
    page = api.get("/cases?limit=2&offset=0").json()
    assert page["total"] == 3 and len(page["items"]) == 2
    assert len(api.get("/cases?limit=2&offset=2").json()["items"]) == 1


def test_eval_splits_gate_and_adjudication(api, db):
    from app.evaluation.dataset import CASES
    from app.evaluation.heldout import CASES_HELDOUT
    from app.models import EvalCase, EvalDataset

    s = db()
    ds = EvalDataset(slug="b", name="b", version="v1.1", description="d", manifest_hash="x")
    s.add(ds)
    s.flush()
    # A case whose expectation is deliberately wrong, so the adjudication flow always has a FAIL to work on
    # (held-out v1 became development data in extractor 1.2 and now passes in full).
    must_fail = {**CASES_HELDOUT[0], "code": "HO-FAIL", "expected": {
        **CASES_HELDOUT[0]["expected"], "fields": {**CASES_HELDOUT[0]["expected"]["fields"], "target_leads": "1"}}}
    for split, cs in (("dev", CASES), ("heldout", [*CASES_HELDOUT, must_fail])):
        for c in cs:
            s.add(EvalCase(dataset_id=ds.id, code=c["code"], split=split, category=c["category"], brief=c["brief"],
                           expected=c["expected"]))
    s.commit()
    run = api.post("/evaluations/runs", {"dataset_id": ds.id}, user="u_priya").json()
    assert set(run["summary"]["splits"]) == {"dev", "heldout"}
    assert run["summary"]["gate"]["applied_to"] == "heldout"
    assert api.post("/evaluations/runs", {"dataset_id": ds.id, "provider": "anthropic"},
                    user="u_priya").json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    detail = api.get(f"/evaluations/runs/{run['id']}", user="u_priya").json()
    fail = next(r for r in detail["results"] if r["outcome"] == "FAIL")
    body = {"status": "confirmed_failure", "note": "Lead criteria stated in prose were not detected."}
    assert api.post(f"/evaluations/results/{fail['id']}/adjudicate", body, user="u_nadia").status_code == 403
    assert api.post(f"/evaluations/results/{fail['id']}/adjudicate", body, user="u_priya").status_code == 200
    run2 = api.post("/evaluations/runs", {"dataset_id": ds.id}, user="u_priya").json()
    assert run2["summary"]["compared_to_run"] == run["id"] and run2["summary"]["regressions"] == []


def test_brief_text_is_stored_with_hash(api, db):
    code = api.create_aster(ASTER_BRIEF)
    s = db()
    doc = s.scalar(select(SourceDocument).where(SourceDocument.kind == "brief"))
    assert doc.content == ASTER_BRIEF and doc.sha256.startswith("sha256:")
    assert api.get(f"/cases/{code}").json()["lock_reason"] is None
