# Karsa

*Formerly DecisionFlow AI; renamed on 11 Nov 2026. “Karsa” is Indonesian for will or intent turned into action.*

**AI-assisted business analysis and controlled workflow orchestration — a portfolio build.**

Karsa turns an unstructured business request (a campaign brief) into a decision that is traceable to its
sources, reviewed by people, and only then executed against sandbox systems with an audit trail.

> AI proposes · rules calculate · humans authorize · the system executes in a bounded way · evaluators check the results.

⚠️ **Everything here is synthetic.** Organisations, clients, people, rate cards, evaluation data and impact metrics are
fictional. The CRM and project tracker are **simulated sandboxes**. The default extractor is a **rule-based demo
parser, not an LLM**. This is not production software.

Built from *DecisionFlow AI Production Specification v1.0 (DFA-PRD-002)* and the 8-screen mockup set.
Gap review and closure: [docs/GAP_CLOSURE.md](docs/GAP_CLOSURE.md).

## What works

| Area | Status |
|---|---|
| Sign-in (scrypt passwords, HttpOnly session cookie, CSRF), two tenants, role-based reads and navigation | ✅ |
| Cases: list (paged, filtered, searched), create from pasted text or uploaded PDF/EML/TXT/MD (original kept) | ✅ |
| Extraction with exact source spans and real PDF page numbers; MISSING / CONFLICTING; injection & claim flags; re-extract | ✅ Demo rules |
| Optional Claude extraction (server-side, structured output, grounding check) | ⚠️ Implemented, **not run live** |
| Requirement review with versions (409 on conflicting edits), reasons, history, override flag | ✅ |
| Clarifications with channel + reference; client's own words vs analyst-recorded evidence | ✅ |
| Deterministic pricing, three-scenario comparison, capacity check, rate card versions | ✅ |
| Decision package: frozen JSON + SHA-256, diff, options, fit-gap, margin-exception request, exports | ✅ |
| Approval with hash/version check, SoD, notes, **two different approvers for high risk** | ✅ |
| Separate execution authorization; connector enable/disable by admin | ✅ |
| Async sandbox execution via transactional outbox + worker; idempotent retries; unknown-outcome reconciliation | ✅ Simulated connectors |
| Exception queue: escalate, manual resolution, cancel with compensation list, reopen | ✅ |
| Append-only audit (database triggers), request IDs, JSON logs, global audit page | ✅ |
| In-app notifications | ✅ (no email/Slack) |
| Evaluation Lab: dev + independent held-out split, release gate, regressions, adjudication | ✅ |
| Impact: synthetic cohort, adoption by people and by cases, live metrics, CSV export | ✅ Synthetic |
| Mobile approval, keyboard flows, axe checks | ✅ |
| OIDC/SSO/MFA, real connectors, OCR, hosting | ❌ Not built |

## Run locally

Needs Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+ with pnpm 9+. No database server (SQLite).

```bash
cd backend && uv sync && uv run alembic upgrade head && uv run python -m app.seed
```

```bash
cd backend && uv run uvicorn app.main:app --port 8000
```

```bash
cd frontend && pnpm install && pnpm dev
```

Open http://localhost:5173 (if that port is busy Vite picks the next one). The API runs the outbox worker in a
background thread; to run it separately set `WORKER_ENABLED=false` and start `uv run python -m app.worker`.

Rebuild the demo database at any time (drops and re-creates the demo tables):

```bash
cd backend && uv run python -m app.seed --reset
```

### Docker (single container)

```bash
docker compose up --build
```

Then open http://localhost:8000. Data lives in the `decisionflow-data` volume.

## Demo accounts

Shared password for every synthetic account: **`decisionflow-demo`**. With `DEMO_MODE=true` the sign-in page also
offers one-click sign-in and the header has an account switcher. Set `DEMO_MODE=false` to disable both.

| Username | Role | Main screens |
|---|---|---|
| `nadia`, `riley` | Deal Desk / Business Analyst | Cases, Approvals (read), Workflows |
| `arif`, `sari` | Commercial Manager / Finance Director (Approvers) | Approvals, Cases (read), Impact |
| `jordan` | Automation Engineer | Workflows (retry, reconcile, resolve, cancel), Cases (read) |
| `priya` | AI Evaluation Analyst | Evaluation Lab |
| `dewi` | Transformation Lead | Impact, Cases (read) |
| `lia` | Auditor (read-only) | Everything read-only + Audit |
| `bima` | Workspace Admin | Manage (rate cards, connectors, policy, team), Audit |
| `omar` | Analyst in a **different tenant** | Sees only `DCF-2001` |

## Workflow automation (n8n)

`integrations/n8n/` holds a self-hosted n8n workflow that feeds requests into Karsa: webhook, validation, idempotent
draft creation (`Idempotency-Key` on `POST /api/v1/cases`), a needs-human branch, retries with exponential backoff and a
dead letter. It never approves anything. Local only, synthetic payloads; 9 of 9 scenarios pass. See
[integrations/n8n/README.md](integrations/n8n/README.md).

## Tests

```bash
cd backend && uv run ruff check . && uv run pytest -q -p no:logging       # 51 tests
```

```bash
cd frontend && pnpm typecheck && pnpm lint && pnpm test && pnpm e2e       # 5 unit + 16 Playwright tests
```

The Playwright suite starts its own API (port 8099, `e2e.db`, real worker thread) and web server (port 5199).
CI runs all of the above (`.github/workflows/ci.yml`).

## Limits

- Authentication is local username/password; no SSO/OIDC/MFA, no password reset, no account management UI.
- SQLite by default; the outbox claim is compare-and-set rather than `SELECT … FOR UPDATE SKIP LOCKED`.
- Connectors and failures are simulated. Notifications are in-app only.
- The demo extractor passes its 24 dev cases but only **1 of 36 held-out cases**; the release gate fails. See
  [docs/GAP_CLOSURE.md](docs/GAP_CLOSURE.md).
- Impact numbers come from a fixed-seed generator: they show the measurement design, not results. No ROI is claimed.
- Manual screen-reader testing has not been done ([docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md)).

## Documentation

- [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) · [docs/PRODUCT_FLOWS.md](docs/PRODUCT_FLOWS.md) ·
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) ·
  [docs/GAP_CLOSURE.md](docs/GAP_CLOSURE.md) · [docs/ACCESSIBILITY.md](docs/ACCESSIBILITY.md)
