# Gap closure report

Status of the 25 gaps found in the review after the first build. "Closed" means implemented **and** covered by a test
that was run. "Partial" means the demo-scale version is done and the rest needs something outside this repo.

| # | Gap | Status | What was done | Evidence |
|---|---|---|---|---|
| 1 | Expired rate card did not stop execution (BR-013) | Closed | Approval, authorization and the execution gate refuse packages priced on an expired/replaced card; publishing a new card ends the old one | `test_expired_rate_card_blocks_approval_and_execution` |
| 2 | Clarification evidence could not be checked | Partial | Answers need a channel and a checkable reference; pasting the client's own words makes it `client_text`, otherwise it is labelled `analyst_recorded` everywhere and raised as a risk in the package | `test_clarification_evidence_is_labelled_by_verification`. Still no email/CRM integration to prove the source |
| 3 | Overridden values could mislead approvers | Closed | `overridden` flag + "source says X" on the requirement, evidence panel, review page, export and package risks | `test_change_after_approval_…` (asserts flag + risk) |
| 4 | Cases could be locked forever after a failed run | Closed | Exception queue (incidents), escalate, manual resolution with external ref, cancel with compensation list, reopen | `test_cancelled_run_…`, `test_manual_resolution_…` |
| 5 | Concurrent edits overwrote silently | Closed | Requirement `version` → 409 `VERSION_CONFLICT`; feasibility save checks the run it was based on | `test_stale_versions_get_409` |
| 6 | "Rejected" was not really closed | Closed | Rejected cases are locked until an analyst reopens them with a reason | `test_rejected_case_is_locked_until_reopened` |
| 7 | No identity or tenants | Partial | Username/password login (scrypt), server sessions in an HttpOnly cookie, CSRF token, 8-hour expiry, logout/revoke; `organization_id` on cases and every lookup scoped; second synthetic tenant | `test_password_login_session_and_csrf`, `test_other_tenant_…`, E2E. **Not** OIDC/SSO/MFA — needs an identity provider |
| 8 | All roles saw all modules | Closed | Read permissions on every GET; navigation and mobile bar built from the server's module list; direct URLs show "Not available for your role" | `test_unauthorized_roles_…`, E2E role test |
| 9 | No dual approval for high risk | Closed | HIGH risk → 2 different approvers; slots shown in the UI; same person cannot approve twice | `test_below_floor_needs_exception_and_two_different_approvers`, mobile E2E |
| 10 | No capacity check / scenario comparison | Closed | Capacity per week on the rate card blocks infeasible plans; three scenarios compared side by side | `test_capacity_blocks_package_and_options_are_compared` |
| 11 | No file upload / re-extraction | Closed | Upload PDF (text), .eml, .txt, .md; original bytes kept and downloadable; real page numbers; scanned PDFs refused; re-extraction keeps human-reviewed fields | `test_pdf_upload_…`, `test_eml_upload`, `test_reextract_…`. No OCR |
| 12 | Narrow requirement catalogue | Closed | Added deliverables, start date (date type), constraints | seed + UI |
| 13 | No options, exception flow or fit-gap | Closed | Options in every package, margin-exception request required below floor, fit-gap against a synthetic service catalogue | `test_below_floor_…`, `test_capacity_…` |
| 14 | Execution was synchronous | Closed (demo scale) | Transactional outbox + worker (background thread or `python -m app.worker`) with leases; duplicate delivery and crashed-worker re-claim are safe | `test_duplicate_delivery_and_lease_expiry_…`, E2E async run. SQLite has no `SKIP LOCKED`; claims use a compare-and-set |
| 15 | Claude adapter never run live | **Open — needs your decision** | Adapter ready; Evaluation Lab can score it against the benchmark | Needs an API key and costs money; not run |
| 16 | No exports or notifications | Closed | Package export (Markdown/JSON, with hash), run log JSON, impact CSV; in-app notifications with bell | `test_exports_carry_the_hash`, `test_notifications_…`. No email/Slack |
| 17 | No management pages | Closed | Rate card versions, connector enable/disable, policy rules, team; global audit page | `test_disabled_connector_blocks_authorization`, E2E axe on `/manage` and `/audit` |
| 18 | Regex detection easy to miss | Partial | Number words (EN/ID), ranges, quarters/days, unlabelled geography, more claim and attach-spec phrasing | Dev set 24/24 — but see the held-out result below |
| 19 | Evaluation too small, no gate | Closed (tooling) | +36 held-out briefs written independently and never used for tuning; per-split scores, regressions vs previous run, release gate, human adjudication, provider selector | `test_eval_splits_gate_and_adjudication` |
| 20 | Adoption measured per case only | Closed | Adoption by people (per month) plus case share; live metrics from the demo DB with "insufficient sample" | Impact page |
| 21 | Demo data aged | Closed | One-year rate card, freshness banner, `seed --reset` rebuilds schema | `/api/v1/health` |
| 22 | Audit append-only by convention only | Closed | DB triggers block UPDATE/DELETE on `audit_events`, `approval_records`, and changes to frozen package content; request IDs in responses, logs and audit rows; JSON access logs | `test_audit_is_append_only_and_traced`, `test_database_refuses_…` |
| 23 | No paging, stale or live states | Closed | Paged case list, "API unavailable — data may be stale" notice, polling of runs/inbox with pause control and screen-reader announcement | `test_pagination`, run page |
| 24 | No CI, Docker or hosting | Partial | GitHub Actions workflow; single-container Dockerfile + compose — built and smoke-tested locally | CI not run yet (no remote). **Hosting not done — needs your decision** |
| 25 | Only automated a11y checks | Partial | axe on sign-in + 11 pages, keyboard-only reject flow (AC-10), focus return fixed; manual checklist in `ACCESSIBILITY.md` | Manual screen-reader test not performed (needs a person) |

## What the held-out set revealed

| Split | Cases | Passed | Field F1 | Notes |
|---|---|---|---|---|
| Dev (used while writing rules) | 24 | 24 | 1.00 | Optimistic by construction |
| Held-out (independent) | 36 | 1 | 0.78 | 28 briefs state the lead definition in prose; the rules only read a labelled line |

The release gate **fails** (held-out pass rate, injection recall 2/4). The rules were frozen before the held-out set was
scored and were not tuned to it. Next step: evaluate the Claude provider on the same set, or rewrite the rules and
write a *new* held-out set to measure them.
