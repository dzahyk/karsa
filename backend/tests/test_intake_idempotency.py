"""POST /cases with an Idempotency-Key: a replayed delivery (e.g. an n8n webhook retry) never creates a duplicate."""
from __future__ import annotations

from app.seed import ASTER_BRIEF

BODY = {"title": "B2B Lead Campaign", "client_name": "Aster Labs", "brief": ASTER_BRIEF}


def _post(api, key, body=BODY, user="u_nadia"):
    c, csrf = api.client(user)
    return c.post("/api/v1/cases", json=body, headers={"X-CSRF-Token": csrf, "Idempotency-Key": key})


def _count(api, user="u_nadia"):
    return api.get("/cases?limit=100", user=user).json()["total"]


def test_replay_with_same_key_returns_the_same_case(api):
    before = _count(api)
    first = _post(api, "n8n-intake-0001")
    assert first.status_code == 201, first.text
    again = _post(api, "n8n-intake-0001")
    assert again.status_code == 200, again.text
    assert again.headers["Idempotent-Replay"] == "true"
    assert again.json()["code"] == first.json()["code"]
    assert _count(api) == before + 1
    verbs = [e["verb"] for e in api.get(f"/cases/{first.json()['code']}/audit").json()]
    assert "case.intake_replayed" in verbs


def test_same_key_with_different_content_is_rejected(api):
    assert _post(api, "n8n-intake-0002").status_code == 201
    other = _post(api, "n8n-intake-0002", BODY | {"title": "A different campaign"})
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_malformed_key_is_rejected_and_no_key_keeps_old_behaviour(api):
    assert _post(api, "short").status_code == 422
    before = _count(api)
    assert api.post("/cases", BODY).status_code == 201
    assert api.post("/cases", BODY).status_code == 201  # no key: two separate cases, as before
    assert _count(api) == before + 2


def test_keys_are_scoped_to_the_organisation(api):
    a = _post(api, "n8n-intake-0003")
    b = _post(api, "n8n-intake-0003", user="u_omar")
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["code"] != b.json()["code"]
