# Architecture

## Overview

```
Browser (React + TS, Vite)          FastAPI modular monolith                    SQLite (default) / Postgres
 ├─ Cases / Requirements  ──HTTP──▶  api/routes.py  (validation, error contract)
 ├─ Feasibility                       │
 ├─ Approval review (mobile)          ├─ services/   use cases + DB transactions
 ├─ Workflows / Run detail            │    cases · requirements · feasibility · packages
 ├─ Evaluation Lab                    │    approvals · execution · impact · audit · authz
 └─ Impact                            ├─ domain/     pure logic, no I/O
                                      │    pricing · extraction · catalog · hashing · permissions
   session cookie + X-CSRF-Token      ├─ ai/         providers: Demo (rules) | Anthropic (optional)
                                      ├─ sandbox/    simulated CRM + tracker (idempotent rows)
                                      ├─ evaluation/ dataset (24 dev + 36 held-out) + runner + gate
                                      └─ worker.py   outbox worker (thread in the API, or standalone)
```

**Boundaries.** `domain/` has no database or HTTP code and is unit-tested directly. The extractor never calls approval
or execution code; execution only accepts a package that passed the gate (`services/execution.gate`). The AI provider
returns an `ExtractionResult` that is validated (grounding + normalisation) before it touches the database.

## Key decisions

| Decision | Why | Trade-off |
|---|---|---|
| FastAPI + SQLAlchemy 2 + Alembic (as in spec ADR-001) | Typed API, explicit transactions, migrations | — |
| SQLite by default | Zero-setup demo; `DATABASE_URL` switches to Postgres | No `SKIP LOCKED` outbox polling; fine for one process |
| Outbox + in-process worker thread | Durable, retry-safe execution without Redis/Celery | One process by default; run `python -m app.worker` to separate |
| React + Vite instead of Next.js | No SSR needs; smaller setup | No server components / BFF layer |
| Hand-written CSS tokens (spec §4.2) | Design system is explicit and small | No component library |
| Local sessions (scrypt + HttpOnly cookie + CSRF) | Real authentication without an external IdP | No SSO/MFA; demo sign-in only when `DEMO_MODE=true` |
| Rule-based demo extractor | Works offline and is reproducible, so the Evaluation Lab is honest | Lower recall than a good LLM |

## Data model

| Table | Purpose | Notable constraints |
|---|---|---|
| `organizations` | Tenants (two synthetic) | — |
| `users` | Accounts, role, scrypt password hash, tenant | unique `username` |
| `auth_sessions` | Session token hash, CSRF token, expiry, revoked | unique `token_hash` |
| `artifacts` | Uploaded files (bytes, SHA-256, pages) | — |
| `connectors` | Connector manifests per tenant, enabled flag | — |
| `outbox_events` | Queued work with lease (`claimed_at`, `claim_token`) | — |
| `incidents` | Exception queue, compensation list, resolution | — |
| `notifications` | In-app notifications per user | — |
| `cases` | Case aggregate: status, next action, flags, action hints | unique `code` |
| `source_documents` | Original brief + each clarification answer, with SHA-256 | append-only in practice |
| `requirements` | Field value, state, source span, candidates, origin | unique `(case_id, key)` |
| `requirement_changes` | Before/after + reason + actor for every change | — |
| `clarifications` | Question, answer, who answered, applied flag | — |
| `rate_cards` | Versioned unit/fixed costs, margin floor, validity window | unique `code` |
| `feasibility_runs` | Saved inputs, results, blockers, assumptions, rate card | — |
| `decision_packages` | Canonical content JSON, `content_hash`, state, risk | unique `(case_id, version)` |
| `approval_records` | Decision, note, actor, **package hash + version** | — |
| `execution_authorizations` | Authorized actions bound to the package hash | unique `package_id` |
| `workflow_runs` / `workflow_steps` / `step_attempts` | Run state, step state, attempt history | unique `(run_id, key)` |
| `sandbox_records` | Simulated external writes | **unique `idempotency_key`** |
| `audit_events` | Append-only log (no update/delete API) | — |
| `eval_datasets` / `eval_cases` / `eval_runs` / `eval_results` | Benchmark, runs, per-case checks | — |
| `impact_cohort_cases` | Synthetic cohort for the Impact page | — |

Money is whole rupiah in integer columns. Margin is computed with `Decimal` and stored in basis points. Times are
stored in UTC and rendered in WIB.

## Snapshot integrity

`content_hash = "sha256:" + sha256(json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False))`.
The hash is stored on the package, copied into the approval record and the execution authorization, and recomputed by
the first workflow step. Any mismatch stops execution.

## AI integration

- `AI_PROVIDER=demo` (default): `domain/extraction.py`, regex-based, deterministic.
- `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`: `ai/providers.py` calls `client.messages.parse` with a Pydantic schema,
  the brief wrapped as untrusted data, and the system prompt as the only instruction source. Each returned value must
  quote the brief verbatim or it is discarded. Injection/claim flags always come from the deterministic scanner. On any
  API failure or refusal it falls back to the demo extractor and records that in `cases.extractor`.
  **This path has not been exercised against the live API in this build.**

## Impact data generator

`seed.py::seed_cohort` creates 337 synthetic cases with `random.Random(20261111)`: May–Jul 2026 manual baseline;
Aug–Oct 2026 with adoption rising 55% → 76%. Cycle times are log-normal with chosen medians (manual ≈ 9–9.7 days,
assisted 7.6 → 6.4 days). These parameters are design inputs, so the chart shows what the generator was told — it is a
demonstration of the measurement design, not evidence.

## Security and reliability controls

- **Sessions:** random token in an HttpOnly, SameSite=Lax cookie (Secure when `COOKIE_SECURE=true`); only its SHA-256 is
  stored; 8-hour expiry; logout revokes. Every non-GET request needs the session's CSRF token in `X-CSRF-Token`.
- **Authorization:** every endpoint checks a permission (reads included); denials are audited. Every lookup is scoped
  to the user's organisation and returns 404 across tenants.
- **Immutability:** database triggers block UPDATE/DELETE on `audit_events` and `approval_records`, and any change to a
  package's `content`/`content_hash`. The execution gate also recomputes the hash (defence in depth; tested with the
  trigger removed).
- **Execution:** start/retry/reconcile write the run change and an outbox event in one transaction. The worker claims
  an event with a compare-and-set and a 30 s lease; an expired lease is re-claimed; failures retry up to 5 times, then
  the event is marked FAILED. Steps are idempotent (unique key in the sandbox), so duplicate delivery is harmless.
- **Tracing:** each request gets `X-Request-ID` (echoed in errors, stored on audit events); JSON access logs record
  method, path, status, duration and user — never bodies, briefs or secrets. Security headers: `nosniff`, `DENY` framing,
  `no-store` for API responses.
- **Uploads:** extension allowlist, 5 MB and 30-page limits, encrypted/scanned PDFs refused, files served back as
  attachments with `nosniff`.

## Before production (not built)

OIDC/SSO and MFA; PostgreSQL with row-level security and `SKIP LOCKED`; real connectors with signed webhooks and a
secret manager; email/Slack notifications; rate limiting and LLM budget guardrails; PII redaction; OpenTelemetry
traces; backups and restore drills; load tests; OCR for scanned files; a larger evaluation set with independent
adjudication and repeated runs for stochastic providers.
