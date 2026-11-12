from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import worker
from app.db import Base, get_session, make_engine, utcnow
from app.db_triggers import install
from app.main import create_app
from app.models import Connector, Organization, RateCard, User
from app.security import hash_password
from app.seed import ASTER_BRIEF, ORGS, USERS
from app.services.connectors import MANIFEST

PW_HASH = hash_password("decisionflow-demo")


@pytest.fixture()
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        install(conn)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session()
    for oid, name in ORGS:
        s.add(Organization(id=oid, name=name))
    s.flush()
    for uid, username, name, role, title, org in USERS:
        s.add(User(id=uid, username=username, password_hash=PW_HASH, name=name, role=role, title=title,
                   organization_id=org))
    now = utcnow()
    for oid, _ in ORGS:
        s.add(RateCard(code="RC-3", name="test card", organization_id=oid, unit_cost_conservative_idr=38_500,
                       unit_cost_expected_idr=35_000, unit_cost_aggressive_idr=31_500, fixed_cost_idr=12_000_000,
                       margin_floor_bp=1500, capacity_leads_per_week=400, valid_from=now - timedelta(days=1),
                       valid_to=now + timedelta(days=30), notes="test"))
        for m in MANIFEST:
            s.add(Connector(organization_id=oid, **m))
    s.commit()
    s.close()
    yield Session
    engine.dispose()


@pytest.fixture()
def app(db):
    a = create_app(start_worker=False)

    def _session():
        s = db()
        try:
            yield s
        finally:
            s.close()

    a.dependency_overrides[get_session] = _session
    return a


class Api:
    """One logged-in TestClient (own cookie jar + CSRF token) per demo user."""

    def __init__(self, app, db):
        self.app, self.db = app, db
        self.clients: dict[str, tuple[TestClient, str]] = {}
        self.anon = TestClient(app)

    def client(self, user: str) -> tuple[TestClient, str]:
        if user not in self.clients:
            c = TestClient(self.app)
            r = c.post("/api/v1/auth/demo-login", json={"username": user.removeprefix("u_")})
            assert r.status_code == 200, r.text
            self.clients[user] = (c, r.json()["csrf_token"])
        return self.clients[user]

    def get(self, path, user="u_nadia"):
        c, _ = self.client(user)
        return c.get(f"/api/v1{path}")

    def post(self, path, json=None, user="u_nadia", **kw):
        c, csrf = self.client(user)
        return c.post(f"/api/v1{path}", json=json if json is not None else ({} if "files" not in kw else None),
                      headers={"X-CSRF-Token": csrf}, **kw)

    def patch(self, path, json, user="u_nadia"):
        c, csrf = self.client(user)
        return c.patch(f"/api/v1{path}", json=json, headers={"X-CSRF-Token": csrf})

    def drain(self):
        worker.drain(self.db)

    # --- flow helpers ---
    def create_aster(self, brief: str = ASTER_BRIEF, user="u_nadia") -> str:
        r = self.post("/cases", {"title": "B2B Lead Campaign", "client_name": "Aster Labs", "brief": brief}, user=user)
        assert r.status_code == 201, r.text
        return r.json()["code"]

    def req(self, code, key):
        return next(r for r in self.get(f"/cases/{code}").json()["requirements"] if r["key"] == key)

    def confirm_drafts(self, code: str):
        for req in self.get(f"/cases/{code}").json()["requirements"]:
            if req["state"] == "DRAFT":
                r = self.patch(f"/cases/{code}/requirements/{req['key']}", {"action": "confirm", "version": req["version"]})
                assert r.status_code == 200, r.text

    def clarify_missing(self, code: str, excerpt: bool = True):
        self.post(f"/cases/{code}/clarifications/suggest")
        for q in self.get(f"/cases/{code}/clarifications").json():
            if q["status"] != "OPEN":
                continue
            text = {"lead_definition": "Manager-level or above at a SaaS or fintech company with 50–500 staff "
                                       "who agrees to a discovery call.",
                    "geography": "Indonesia — Jabodetabek and Surabaya."}[q["requirement_key"]]
            body = {"answer": text, "answered_source": "Maya Santoso (client)", "apply": True, "channel": "email",
                    "reference": "Email 'Re: lead criteria', 10 Nov 2026"}
            if excerpt:
                body["client_excerpt"] = text
            r = self.post(f"/cases/{code}/clarifications/{q['id']}/answer", body)
            assert r.status_code == 200, r.text

    def price(self, code: str, **override):
        f = self.get(f"/cases/{code}/feasibility").json()
        r = self.post(f"/cases/{code}/feasibility", {"scenario": "expected", "inputs": f["inputs"] | override})
        assert r.status_code == 201, r.text
        return r.json()

    def ready_package(self, **price_override) -> tuple[str, dict]:
        code = self.create_aster()
        self.confirm_drafts(code)
        self.clarify_missing(code)
        self.price(code, **price_override)
        r = self.post(f"/cases/{code}/packages")
        assert r.status_code == 201, r.text
        return code, r.json()

    def approve(self, pkg: dict, user="u_arif", note="ok"):
        body = {"decision": "APPROVE", "note": note, "package_hash": pkg["content_hash"], "version": pkg["version"]}
        r = self.post(f"/packages/{pkg['id']}/review", body, user=user)
        assert r.status_code == 200, r.text
        return r.json()

    def authorize(self, pkg: dict):
        detail = self.get(f"/packages/{pkg['id']}").json()
        actions = [a["action"] for a in detail["content"]["proposed_actions"]]
        r = self.post(f"/packages/{pkg['id']}/authorize", {"package_hash": pkg["content_hash"],
                                                            "confirmed_actions": actions}, user="u_arif")
        assert r.status_code == 200, r.text

    def run(self, pkg: dict, simulate="none", user="u_nadia") -> dict:
        r = self.post(f"/packages/{pkg['id']}/runs", {"simulate": simulate}, user=user)
        assert r.status_code == 202, r.text
        assert r.json()["status"] == "QUEUED"
        self.drain()
        return self.get(f"/runs/{r.json()['code']}", user="u_jordan").json()

    def run_action(self, code: str, path: str, body=None, user="u_jordan"):
        r = self.post(f"/runs/{code}/{path}", body, user=user)
        assert r.status_code == 200, r.text
        self.drain()
        return self.get(f"/runs/{code}", user=user).json()


@pytest.fixture()
def api(app, db):
    return Api(app, db)
