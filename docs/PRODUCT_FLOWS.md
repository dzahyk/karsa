# Product flows and business rules

All data is synthetic. Rule IDs refer to the specification (DFA-PRD-002 §2.4), which is not published; each rule is restated below.

## Personas → what they do in the app

| Persona | Main screens | Key actions |
|---|---|---|
| Deal Desk / Business Analyst | Cases, Requirements & evidence, Feasibility, Decision package | Create case, review AI drafts, ask/answer clarifications, price, freeze package |
| Commercial Manager (Approver) | Approvals, Approval review (desktop + mobile) | Approve / reject / request changes; authorize execution |
| Automation Engineer | Workflows, Run detail | Start sandbox runs, retry safe failures, reconcile unknown outcomes |
| AI Evaluation Analyst | Evaluation Lab | Run the benchmark, inspect failures and traces |
| Transformation Lead | Impact | Read baseline vs assisted metrics with definitions and caveats |

## Main journey

```
Intake ─▶ Extraction (AI draft) ─▶ Requirement review ─▶ Clarification ─▶ Feasibility & pricing
   ─▶ Decision package (frozen, hashed) ─▶ Human approval ─▶ Execution authorization (separate)
   ─▶ Sandbox workflow ─▶ Read-back verification ─▶ Completed (verified)
```

Case status is derived on the server from requirements, packages, authorizations and runs:

| Status | Meaning | Typical next action |
|---|---|---|
| NEEDS_CLARIFICATION | A critical requirement is missing, conflicting or still an AI draft | Define / resolve / confirm the field |
| IN_ANALYSIS | Critical requirements confirmed | Run pricing, then create a package |
| AWAITING_APPROVAL | Current package is in review | Approver decides |
| CHANGES_REQUESTED / REJECTED | Reviewer returned or rejected the package (note required) | Revise / closed |
| APPROVED | Decision approved, nothing executed | Approver authorizes execution |
| AUTHORIZED | Sandbox actions authorized | Start the run |
| EXECUTION_ATTENTION | Run partial, failed, or outcome unknown | Retry or reconcile |
| COMPLETED | Every write read back with the approved hash | — |

## Rules implemented (and where they are tested)

| Rule | Behaviour | Test |
|---|---|---|
| Evidence (AC-01, BR-009) | Every extracted value carries `quote` + character offsets into the stored source; `text[start:end] == quote`. No page numbers are invented: the UI says “chars 173–194”. Missing values have no source and say so. | `test_every_span_is_a_real_substring_of_the_source` |
| Conflicts (AC-02) | Different values for one field → CONFLICTING with every candidate shown; the analyst must pick one with a reason. | `test_conflicting_budget_is_flagged_with_both_sources` |
| Untrusted documents | Instruction-like text is flagged and audited; it changes no state or permission. Claude output is discarded unless its quote is found verbatim in the brief. | `test_injected_instructions_do_not_change_permissions_or_state`, `test_model_output_without_verbatim_quote_is_discarded` |
| Deterministic pricing (BR-002, AC-03) | `variable = target × unit`, `total = variable + fixed`, `margin = (fee − total) / fee`; integer rupiah, Decimal, basis points, half-up. Fee 0 is rejected instead of dividing by zero. | `tests/test_pricing.py` |
| Package blocked when incomplete (BR-001) | A package cannot be frozen while a critical requirement is not CONFIRMED, pricing is invalid, the rate card is outside its validity window, or the pricing target differs from the confirmed requirement. The approve endpoint re-checks the frozen content. | `test_package_is_blocked_…`, `test_approve_endpoint_rechecks_blockers_…` |
| Snapshot integrity (BR-003, AC-04) | Approval stores the package hash and version; stale hash/version → 409. Execution recomputes the hash and fails closed on mismatch. | `test_approval_records_the_exact_snapshot…`, `test_stale_hash…`, `test_tampered_snapshot_still_fails_closed_without_the_trigger` |
| Change after approval (BR-004) | Editing a requirement or saving different pricing supersedes the active package. The old snapshot and approval record remain unchanged; a new version needs a new review. | `test_change_after_approval_creates_new_version…` |
| Approval ≠ execution | Approving creates no external effect. Execution needs a separate authorization, where the approver confirms each action. | `test_execution_requires_approval_and_separate_authorization` |
| Idempotent retry (BR-007, AC-05) | Each write step has a stable idempotency key; the sandbox has a unique constraint; replays return the existing record. | `test_retry_after_timeout_does_not_duplicate…` |
| Unknown outcome (AC-06) | Timeout after commit → UNKNOWN_OUTCOME; retry is refused (409) until reconciliation reads the target. | `test_unknown_outcome_blocks_blind_retry…` |
| Role checks (AC-08) | Every mutating endpoint checks the role on the server; denials return 403 and are audited as `security.denied`. | `test_unauthorized_roles_are_denied_and_audited` |
| Segregation of duties | The package author cannot review it. | `test_package_author_cannot_review_own_package` |
| Notes | Reject and request-changes need a note; high-risk approval needs an exception note. | `test_reject_and_request_changes_need_a_note`, mobile E2E |
| Dual approval (BR-006) | HIGH risk (margin below floor or injection flag) needs two different approvers; below-floor packages also need a written exception request. | `test_below_floor_needs_exception_and_two_different_approvers` |
| Capacity (FR-008) | Required leads per week above the rate card's capacity blocks the package. | `test_capacity_blocks_package_and_options_are_compared` |
| Rate card expiry (BR-013) | A package priced on an expired or replaced card cannot be approved, authorized or executed. | `test_expired_rate_card_blocks_approval_and_execution` |
| Connector allowlist (BR-005) | Authorization and each write step need an enabled connector for the action. | `test_disabled_connector_blocks_authorization` |
| Concurrency | Stale requirement versions and stale pricing bases return 409. | `test_stale_versions_get_409` |
| Locks & reopen | Rejected cases and cancelled runs lock the case until an analyst reopens it with a reason. | `test_rejected_case_…`, `test_cancelled_run_…` |
| Recovery | Escalate to the exception queue, resolve a step manually with an external reference, or cancel (completed writes listed for compensation, never deleted). | `test_manual_resolution_…`, `test_cancelled_run_…` |
| Evidence verification | Clarification answers need a channel and reference; only pasted client words count as client text. | `test_clarification_evidence_…` |

## Secondary flows

- **Request changes → new version.** DCF-1043 shows v1 returned for changes and v2 with a diff (timeline 6 → 8 weeks)
  plus the previous reviewer note.
- **Below-floor margin.** DCF-1045 is high risk (6.82% vs 15% floor); approval requires an exception note.
- **Unknown outcome.** DCF-1044 run EX-0082 stopped after the tracker committed but the response was lost.
- **Prompt injection.** DCF-1051's brief tells “the AI system” to approve; it is flagged, audited and ignored.
- **Conflicting budget.** DCF-1046's brief contains two budgets.
- **Dual approval.** DCF-1045 (6.82 % margin) has an exception request and Arif's first approval; Sari must give the second.
- **Analyst-recorded evidence.** DCF-1049's lead definition came from a phone call, so it is labelled and flagged.
- **Exception queue.** DCF-1053's tracker connector was disabled mid-run; the run is partial with an open incident.
- **Other tenant.** DCF-2001 belongs to Bluepeak and is invisible to Northstar accounts.

## Mockup corrections

| Mockup | Issue | Resolution |
|---|---|---|
| 04 Approval | “Deliver a minimum of 250 MQLs” | Uses 3,000 qualified leads everywhere, per the brief |
| 08 Mobile | Case “#CF-8427”; “Approved package” while still pending; fee 140→150 change | Uses DCF-1042 IDs; header says “Pending your approval”; diffs are computed from real package versions |
| 05 Workflow | Case named “Enterprise CRM Onboarding”; “Review and retry” on a timeout | Run pages use real case names; retry only when nothing was committed, otherwise “Check target system” |
| 06 Evaluation | 120 cases, “Run evaluation” with illustrative numbers | 24 real hand-written cases; the button runs the real scorer; nothing illustrative is shown as measured |
| 07 Impact | 2024 dates, 13k cases | Synthetic cohort May–Oct 2026, labelled, with sample sizes and a concurrent manual comparison group |
| All | Different logos, nav labels (Cases/Approvals/Workflows/Insights vs spec IA) | One logo and one nav: Cases · Approvals · Workflows · Evaluation · Impact |
| 02 Requirements | “Campaign brief.pdf, p.1” and “Verified” | Sources are cited by document and character range; “Confirmed” only after a human confirms |
