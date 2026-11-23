# Karsa (formerly DecisionFlow AI) — Implementation Plan

Source of truth: *DecisionFlow AI Production Specification v1.0 (DFA-PRD-002, 11 Nov 2026)*.
Visual reference: an 8-screen mockup set (not published). This is a portfolio build:
all tenants, cases, numbers, and results are **synthetic**.

## 1. Product understanding

Karsa turns an unstructured business request (a campaign brief) into a decision that is
traceable, reviewed by a human, and then executed in a controlled way.

> AI proposes; rules calculate; humans authorize; the system executes in a bounded way;
> evaluators check the results.

The vertical slice is the spec's representative scenario: **DCF-1042 · Aster Labs · B2B Lead
Campaign** — 3,000 qualified leads, Rp150,000,000 proposed fee, 8 weeks, unit cost Rp35,000,
fixed cost Rp12,000,000, total cost Rp117,000,000, estimated gross margin 22%.

## 2. User journey (critical path)

| # | Step | Persona | Gate |
|---|------|---------|------|
| 1 | Create case from brief text | Analyst | Server validates input |
| 2 | Requirement extraction (demo rule-based extractor, or Claude if configured) | system | Every value carries an exact quote + character offsets from the brief, or is marked MISSING |
| 3 | Review requirements: confirm / edit (reason required) / mark missing | Analyst | Changes stored with history |
| 4 | Clarification questions → answers → applied to requirements | Analyst | The answer text becomes the cited source |
| 5 | Feasibility & pricing (deterministic, integer rupiah) | Analyst | Rate card version recorded; blockers listed |
| 6 | Create decision package (frozen, SHA-256 of canonical JSON) | Analyst | Blocked while any critical requirement is not CONFIRMED |
| 7 | Review: approve / reject / request changes | Approver | Hash + version must match (409), SoD (403), blockers (422), note required for reject/changes |
| 8 | Authorize execution (separate act, lists the sandbox write actions) | Approver | Only for an APPROVED, still-current package |
| 9 | Run sandbox workflow: verify snapshot → CRM opportunity → tracker project → read-back verification | Automation Engineer / Analyst | Hash re-verified; idempotency keys; retry rules |
| 10 | Evaluation Lab, Impact | Eval Analyst, Transformation Lead | Synthetic labels everywhere |

## 3. MVP features (built first, in this order)

1. Cases & intake (list, search, status filters, create, detail) — persisted.
2. Requirements & evidence (exact source spans, statuses, edit with reason, history).
3. Clarifications (ask, answer, apply).
4. Feasibility & deterministic pricing with scenarios and calculation trace.
5. Decision package versions, canonical hash, diff vs previous version.
6. Human approval with audit; snapshot immutability; invalidation on later change.
7. Execution authorization + sandbox workflow with failure injection, retry, reconciliation, receipts, audit.
8. Seed data + docs for running locally.

## 4. Follow-on features

9. Evaluation Lab — a **real** runner that scores the demo extractor + pricing oracle + action
   planner against a hand-written synthetic dataset. No fake "Run evaluation" button.
10. Impact — metrics computed from a seeded synthetic cohort (fixed-seed generator), with
    definitions, periods, sample sizes, and a "does not prove causation" note.
11. Mobile approval layout (responsive, bottom tab bar, sticky action bar, confirm dialogs).
12. Accessibility & quality pass (keyboard, focus, labels, contrast, reduced motion).

## 5. Architecture (chosen)

| Layer | Choice | Deviation from spec §3.3 and why |
|---|---|---|
| API | Python 3.12, FastAPI, Pydantic v2 | Same as spec |
| DB | SQLAlchemy 2 + Alembic, **SQLite by default**, Postgres via `DATABASE_URL` | Zero-setup local demo; Postgres remains supported |
| Async | **None** — workflow steps run synchronously inside a request | Celery/Redis is heavy for a demo; outbox pattern is simplified to idempotent step records |
| Web | React 18 + TypeScript + Vite + React Router + TanStack Query | No SSR need; Next.js adds weight without benefit here |
| Styling | Hand-written CSS with design tokens from spec §4.2 | Keeps the design system explicit |
| AI | Provider interface: `demo` (rule-based, deterministic) and `anthropic` (optional, server-side) | Works without credentials |
| Auth | **Demo role switcher** (header `X-Demo-User`), permissions enforced server-side | Not authentication — documented as such |
| Tests | pytest, Vitest, Playwright | Same as spec |

Module boundaries (backend `app/`): `domain/` (pure logic: pricing, extraction, hashing, states,
permissions), `services/` (use cases + DB), `api/` (HTTP), `ai/` (providers), `sandbox/`
(fake external CRM/tracker), `evaluation/`, `seed.py`.

## 6. Main data model

`users`, `cases`, `source_documents`, `requirements`, `requirement_changes`, `clarifications`,
`rate_cards`, `feasibility_runs`, `decision_packages`, `approval_records`,
`execution_authorizations`, `workflow_runs`, `workflow_steps`, `step_attempts`,
`sandbox_records` (unique idempotency key), `audit_events` (append-only), `eval_datasets`,
`eval_cases`, `eval_runs`, `eval_results`, `impact_cohort_cases`.

Money: integer rupiah (IDR has no minor unit in practice). Margin: computed with `Decimal`,
stored as basis points (integer), rounded half-up. No floats in money paths.

## 7. Risks and assumptions

- **Assumption:** the demo extractor is a transparent rule-based parser, not an LLM. It is labelled
  "Demo extractor (rule-based)" everywhere. It will miss things; that is visible in Evaluation Lab.
- **Assumption:** IDR amounts are whole rupiah; spec's 2-decimal minor-unit example is noted.
- **Risk:** the Anthropic adapter cannot be verified without a key. It is unit-tested with a mocked
  HTTP response only, and docs say so.
- **Risk:** synchronous execution hides queue/worker failure modes (worker crash, duplicate delivery).
  Those spec scenarios are only partly covered (duplicate request and retry are tested).
- **Assumption:** one approver for this risk class; SoD = package creator cannot approve.
- **Mockup corrections:** 3,000 leads everywhere (not 250); case ID DCF-1042 (not #CF-8427); mobile
  header shows "Pending your approval" without calling the package "Approved"; nav labels unified to
  Cases · Approvals · Workflows · Evaluation · Impact; dates follow the spec (Nov 2026) and the WIB
  timezone.

## 8. Test strategy

| Behaviour | Test |
|---|---|
| Cost/margin math incl. invalid input, zero fee, negatives, rounding | `tests/test_pricing.py` |
| Extraction spans are real substrings; conflicts; injection flag | `tests/test_extraction.py` |
| Approval blocked when critical requirements incomplete | API test |
| Approval stores the correct snapshot hash/version | API test |
| Edits after approval do not change the old snapshot; supersede it | API test |
| Execution blocked without approval/authorization or with stale hash | API test |
| Retry does not duplicate sandbox records; unknown outcome blocks blind retry | API test |
| Unauthorized roles get 403 and a security audit event | API test |
| Full browser flow create → … → sandbox run | Playwright `e2e/critical-path.spec.ts` |

Plus `ruff`, `tsc --noEmit`, ESLint, and a visual check at desktop and mobile widths.

## 9. Delivery stages

1. Backend skeleton, models, migration, pricing + extraction + tests.
2. Services and API for cases → execution, with rule tests.
3. Frontend design system + Cases + Requirements + Feasibility.
4. Package, Approval (desktop + mobile), Execution.
5. Evaluation runner + Lab, Impact.
6. Playwright E2E, visual pass, docs.

## 10. v0.2 — gap closure (after review)

Changes to the plan above, made to close the 25 gaps in [GAP_CLOSURE.md](GAP_CLOSURE.md):
- **Auth:** the demo role switcher was replaced by real local sessions (scrypt, HttpOnly cookie, CSRF) and tenants;
  one-click demo sign-in stays only behind `DEMO_MODE`.
- **Execution:** synchronous execution was replaced by a transactional outbox and a worker with leases.
- **Evaluation:** a 36-case held-out split was written independently (separate author, extractor not read) and frozen
  before scoring. The rules were improved only against the dev split.
- **Delivery:** Dockerfile + compose (verified locally) and a GitHub Actions workflow (not yet run on GitHub).
- **Still open:** live Claude evaluation (needs an API key and budget approval), hosting (needs a platform decision),
  SSO/MFA, real connectors, manual screen-reader testing.
