# Functional Requirements and Acceptance Criteria — Karsa

FRD-KARSA-01, version 1.0, 12 Nov 2026. Each requirement traces to a business rule in [`01_BRD.md`](01_BRD.md) and to
automated checks in [`04_TRACEABILITY.md`](04_TRACEABILITY.md). Acceptance criteria are written so a tester can run
them by hand on the seeded demo (`python -m app.seed`), using the fictional cases named in brackets.

## Intake and requirements
**FR-01 Intake.** An analyst creates a case from pasted text or an uploaded PDF / EML / TXT / MD file; the original is
stored unchanged with its SHA-256.
- *Given* a pasted brief, *when* the case is created, *then* the stored source equals the pasted text and carries a hash.

**FR-02 Extraction with evidence** (BR-009, AC-01). Each extracted value is a DRAFT with an exact quote and character
offsets; a value with no evidence is MISSING. Model output whose quote is not found verbatim is discarded.
- *Given* the Aster Labs brief [DCF-1042], *when* extraction runs, *then* leads 3,000, fee Rp150,000,000 and 8 weeks
  appear as drafts whose quote equals `brief[start:end]`, and fields the brief does not state stay MISSING.

**FR-03 Conflicts** (AC-02). Two different values for one field make it CONFLICTING with every candidate shown.
- *Given* a brief with "Budget Rp120.000.000" and "Finance cap Rp100 juta" [DCF-1046], *then* budget is CONFLICTING
  with both quotes, and the analyst must pick one with a reason.

**FR-04 Untrusted brief text.** Instruction-like text and unsupported outcome claims are flagged, audited and change no
state or permission.
- *Given* a brief telling "the AI system" to approve [DCF-1051], *then* a prompt-injection flag is shown and no status,
  role or approval changes.

**FR-05 Requirement review.** Confirm, edit (reason required) or mark missing; every change is versioned; an edit
based on a stale version is refused (409).

**FR-06 Clarification evidence.** An answer needs a channel and a reference; only pasted client words count as client
text; analyst-recorded answers are labelled as such [DCF-1049].

## Pricing and package
**FR-07 Deterministic pricing** (BR-002, AC-03). *Given* 3,000 leads × Rp35,000 + Rp12,000,000 fixed and a fee of
Rp150,000,000, *then* total cost is Rp117,000,000 and margin 22.00%; a fee of 0 is rejected.

**FR-08 Capacity** (spec FR-008). Required leads per week above the rate card's capacity blocks the package; three
scenarios are compared side by side.

**FR-09 Package gate** (BR-001). The package cannot be frozen, and the approve endpoint refuses it again, while any
critical requirement is unconfirmed, pricing is invalid, the rate card is outside its window, or pricing and
requirements disagree.

## Approval
**FR-10 Approval binds the snapshot** (BR-003, AC-04). Approval records package version + hash; a stale version or hash
gets 409; execution recomputes the hash and stops on mismatch.

**FR-11 Change after approval** (BR-004). *Given* an approved package, *when* the timeline changes 6 → 8 weeks
[DCF-1043], *then* a new package version is created, the old snapshot and its approval are unchanged, and the new
version needs a new review. (Worked example: [`06_CHANGE_REQUEST_CR-001.md`](06_CHANGE_REQUEST_CR-001.md).)

**FR-12 Segregation of duties and notes.** The author cannot review their own package; reject and request-changes need
a note; approving a high-risk package needs an exception note.

**FR-13 Dual approval** (BR-006). *Given* a margin of 6.82% against a 15% floor [DCF-1045], *then* an exception
request is required and two *different* approvers must approve; the second can do it on mobile.

## Execution
**FR-14 Separate authorization.** Approval has no external effect; execution needs a separate authorization where the
approver confirms each sandbox action.

**FR-15 Connector allowlist** (BR-005). Authorization and each write step need an enabled connector.

**FR-16 Rate-card validity** (BR-013). A package priced on an expired or replaced card cannot be approved, authorized or
executed.

**FR-17 Idempotent retry** (BR-007, AC-05). A retry after a timeout returns the existing record instead of a duplicate.

**FR-18 Unknown outcome** (AC-06). *Given* a step that committed but whose response was lost [DCF-1044, run EX-0082],
*then* status is UNKNOWN_OUTCOME and retry is refused (409) until reconciliation reads the target system.

**FR-19 Recovery.** Escalate to an exception queue, resolve a step manually with an external reference, or cancel with
a compensation list (completed writes are listed, never deleted); a rejected or cancelled case is locked until reopened
with a reason.

## Platform
**FR-20 Roles and tenancy** (AC-08). Every mutating endpoint checks the role on the server; denials return 403 and are
audited; a second tenant's cases are invisible [DCF-2001].

**FR-21 Append-only audit.** Database triggers refuse UPDATE/DELETE on audit events, approval records and frozen
package content; every request has an ID in the response, the log and the audit row.

**FR-22 Evaluation Lab.** Dev and held-out splits are scored separately; a release gate is applied to the held-out
split; regressions against the previous run are listed; a human can adjudicate a failure.

**FR-23 Accessibility** (AC-10). An approver can open, compare and reject a package with the keyboard only; automated
axe checks report no serious violations on the main pages.

**FR-24 Critical path.** One case can go intake → requirements → clarification → pricing → package → approval →
authorization → sandbox run → verified completion in the browser.
