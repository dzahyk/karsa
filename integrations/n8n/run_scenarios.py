"""Send sample requests through the n8n intake workflow and check the outcome in Karsa.

Needs: n8n running with the workflow active (./setup.sh). This script starts its own Karsa API on
127.0.0.1:8077 with a fresh, seeded SQLite database in a temp folder, so the demo database is never touched.

Run:  python3 integrations/n8n/run_scenarios.py
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
FILES = HERE / "files"
KARSA = "http://127.0.0.1:8077/api/v1"
WEBHOOK = os.getenv("N8N_WEBHOOK", "http://127.0.0.1:5678/webhook/karsa-intake")


def env() -> dict[str, str]:
    out = {}
    for line in (HERE / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


ENV = env()


def sample(name: str) -> dict:
    return json.loads((HERE / "samples" / name).read_text())


def send(body: dict, secret: str | None = None) -> tuple[int, dict, float]:
    req = urllib.request.Request(WEBHOOK, data=json.dumps(body).encode(), method="POST", headers={
        "Content-Type": "application/json", "X-Intake-Secret": secret if secret is not None else ENV["KARSA_INTAKE_SECRET"]})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}"), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), time.monotonic() - t0


class Karsa:
    """A small Karsa client (session cookie) used only to read results."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.tmp = Path(tempfile.mkdtemp(prefix="karsa-n8n-"))
        self.db = f"sqlite:///{self.tmp / 'karsa.db'}"

    def start(self, fresh: bool = False):
        e = os.environ | {"DATABASE_URL": self.db, "DEMO_MODE": "true"}
        if fresh:
            subprocess.run(["uv", "run", "-q", "alembic", "upgrade", "head"], cwd=BACKEND, env=e, check=True,
                           capture_output=True)
            subprocess.run(["uv", "run", "-q", "python", "-m", "app.seed"], cwd=BACKEND, env=e, check=True,
                           capture_output=True)
        self.proc = subprocess.Popen(["uv", "run", "-q", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                      "--port", "8077"], cwd=BACKEND, env=e, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{KARSA}/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("Karsa API did not start")
        jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        r = self.http.open(urllib.request.Request(f"{KARSA}/auth/login", method="POST", headers={
            "Content-Type": "application/json"}, data=json.dumps({"username": ENV["KARSA_USERNAME"],
                                                                  "password": ENV["KARSA_PASSWORD"]}).encode()))
        assert r.status == 200

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)
            self.proc = None

    def get(self, path: str):
        return json.loads(self.http.open(f"{KARSA}{path}").read())

    def total(self) -> int:
        return self.get("/cases?limit=1")["total"]

    def audit_verbs(self) -> list[str]:
        a = self.get("/audit")
        items = a.get("items", a.get("events", [])) if isinstance(a, dict) else a
        return [e.get("verb", "") for e in items if isinstance(e, dict)]


def lines(name: str) -> list[dict]:
    p = FILES / name
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def main() -> int:
    for f in ("notifications.jsonl", "dead-letter.jsonl"):
        (FILES / f).unlink(missing_ok=True)
    karsa = Karsa()
    karsa.start(fresh=True)
    rows, ok_all = [], True

    def check(name: str, expect: str, ok: bool, got: str, case: str | None = None):
        nonlocal ok_all
        ok_all &= ok
        rows.append((name, expect, got, case or "-", "PASS" if ok else "FAIL"))
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {got}")

    try:
        base = karsa.total()

        # 1. Valid, complete request -> a draft case in Karsa, nothing approved.
        s, b, _ = send(sample("complete.json"))
        code1 = b.get("case_code")
        detail = karsa.get(f"/cases/{code1}") if code1 else {}
        check("valid request", "201 draft_created, case created, no package or approval",
              s == 201 and b.get("status") == "draft_created" and karsa.total() == base + 1
              and detail.get("latest_package") is None,
              f"{s} {b.get('status')}, total cases +{karsa.total() - base}, package={detail.get('latest_package')}",
              code1)

        # 2. The same webhook delivered again -> same case, no duplicate.
        s, b, _ = send(sample("complete.json"))
        check("duplicate replay", "200 already_received, same case, no new case",
              s == 200 and b.get("status") == "already_received" and b.get("case_code") == code1
              and karsa.total() == base + 1,
              f"{s} {b.get('status')} {b.get('case_code')}, total cases +{karsa.total() - base}", b.get("case_code"))

        # 3. Valid payload, but Karsa's extractor finds critical gaps -> draft + needs-human notification.
        s, b, _ = send(sample("unclear.json"))
        code3 = b.get("case_code")
        note = [n for n in lines("notifications.jsonl") if n["status"] == "needs_human" and n["case_code"] == code3]
        check("unclear brief", "202 needs_human with reasons, case stays a draft, notification logged",
              s == 202 and b.get("status") == "needs_human" and len(b.get("reasons", [])) >= 1 and len(note) == 1,
              f"{s} {b.get('status')}; reasons: {'; '.join(b.get('reasons', []))}", code3)

        # 4. Missing required field -> nothing sent to Karsa.
        before = karsa.total()
        s, b, _ = send(sample("missing-field.json"))
        check("missing field", "422 needs_human, no case created",
              s == 422 and b.get("status") == "needs_human" and karsa.total() == before,
              f"{s} {b.get('status')}; {'; '.join(b.get('reasons', []))}; total cases +{karsa.total() - before}")

        # 5. Wrong shared secret -> refused before validation.
        s, b, _ = send(sample("complete.json"), secret="wrong-secret")
        check("wrong secret", "401, no case created", s == 401 and karsa.total() == before,
              f"{s} {b.get('status')}")

        # 6. Same request_id reused for different content -> Karsa refuses (409), a person is told, no retry.
        changed = sample("complete.json") | {"title": "Q1 webinar lead program (edited)"}
        s, b, elapsed = send(changed)
        check("same id, different content", "409 needs_human, not retried",
              s == 409 and b.get("status") == "needs_human" and elapsed < 3,
              f"{s} {b.get('status')} in {elapsed:.1f}s; {'; '.join(b.get('reasons', []))}")

        # 7. Karsa API down -> 1 + 3 retries with 1/2/4 s backoff, then dead letter.
        karsa.stop()
        s, b, elapsed = send(sample("complete.json") | {"request_id": "WEB-2026-1104"})
        dl = [d for d in lines("dead-letter.jsonl") if d["request_id"] == "WEB-2026-1104"]
        check("Karsa API down", "503 dead_letter after 4 attempts (~7 s of backoff), request kept",
              s == 503 and b.get("status") == "dead_letter" and b.get("attempts") == 4 and len(dl) == 1
              and elapsed >= 7,
              f"{s} {b.get('status')}, attempts={b.get('attempts')}, {elapsed:.1f}s, dead-letter entries={len(dl)}")

        # 8. Karsa back up -> replay the dead-lettered request; it is created exactly once.
        karsa.start()
        entry = dl[0] if dl else {}
        before = karsa.total()
        replay = {"request_id": entry.get("request_id"), **entry.get("case", {})}
        s, b, _ = send(replay)
        s2, b2, _ = send(replay)
        check("replay dead letter", "201 then 200, exactly one new case",
              s == 201 and s2 == 200 and b.get("case_code") == b2.get("case_code") and karsa.total() == before + 1,
              f"{s} then {s2}, total cases +{karsa.total() - before}", b.get("case_code"))

        # 9. Nothing the workflow created was packaged, approved or executed.
        made = [c for c in (code1, code3, b.get("case_code")) if c]
        verbs = sorted({e["verb"] for c in made for e in karsa.get(f"/cases/{c}/audit")})
        bad = [v for v in verbs if v.split(".")[0] in ("package", "approval", "authorization", "execution", "run")]
        packages = [c for c in made if karsa.get(f"/cases/{c}")["latest_package"] is not None]
        check("no auto-approval", "workflow cases have no package, approval or execution events",
              not bad and not packages and len(made) == 3,
              f"{len(made)} cases checked; audit verbs: {', '.join(verbs)}", ", ".join(made))
    finally:
        karsa.stop()
        shutil.rmtree(karsa.tmp, ignore_errors=True)

    out = HERE / "RESULTS.md"
    with out.open("w") as f:
        f.write("# Scenario results\n\nGenerated by `run_scenarios.py` against a fresh, seeded Karsa database and the "
                "local n8n workflow. Synthetic payloads only.\n\n| Scenario | Expected | Got | Case | Result |\n"
                "|---|---|---|---|---|\n")
        for r in rows:
            f.write("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |\n")
    print(f"\n{sum(r[4] == 'PASS' for r in rows)}/{len(rows)} scenarios passed. Written to {out.name}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
