# Business Requirements Document — Karsa deal desk

| | |
|---|---|
| Document | BRD-KARSA-01, version 1.0, 12 Nov 2026 |
| Product | Karsa (formerly DecisionFlow AI), portfolio build |
| Source | *DecisionFlow AI Production Specification v1.0 (DFA-PRD-002)*; a private working spec, not published; rule IDs (BR-, AC-, FR-) are the spec's and are restated here and in 02_FRD.md |
| Author | Daffa Zahy Khairy (business analysis); built with Claude (via Claude Code) as implementation and drafting assistant under the author's direction |
| Status | Baseline for the built product. **Not signed off by a real business owner** — all organisations are fictional |

> Everything below describes a fictional B2B lead-generation agency ("Northstar") and synthetic data. No real client,
> employer or result is described.

## 1. Business problem
A B2B lead-generation agency receives campaign requests as free text: emails, chat threads, RFPs, PDFs. Today a
deal-desk analyst reads each brief, copies the numbers into a spreadsheet, prices it from a rate card, sends it to a
commercial manager for approval by chat, and then someone types the deal into the CRM and the project tracker.

The spec identifies four failure modes in that process:
1. **Requirements get lost or invented.** Numbers are retyped without a link to where they came from; ambiguous or
   conflicting values (two budgets, a lead range) are silently resolved by whoever copies them.
2. **Pricing is inconsistent.** Spreadsheet formulas differ per analyst; margin floors are checked by eye.
3. **Approval is not tied to what was approved.** A manager approves "the deal", the brief changes afterwards, and
   the CRM receives values nobody approved.
4. **Execution is fragile.** A timeout while writing to the CRM leads to duplicate records or a blind retry.

## 2. Business objectives
| ID | Objective | How it is measured in the product |
|---|---|---|
| OBJ-1 | Every number in a decision is traceable to its source text or to a recorded clarification | 100% of extracted values carry an exact quote with character offsets (AC-01) |
| OBJ-2 | Pricing is the same no matter who prepares it | Deterministic integer-rupiah calculation with a versioned rate card (BR-002) |
| OBJ-3 | Only an approved, unchanged package can reach external systems | Approval stores the package hash; execution re-verifies it and fails closed (BR-003) |
| OBJ-4 | High-risk deals get more scrutiny, not less | Margin below floor or an injection flag needs two different approvers (BR-006) |
| OBJ-5 | Failures during execution never create duplicates or silent gaps | Idempotent steps, unknown-outcome reconciliation, exception queue (BR-007, AC-05, AC-06) |
| OBJ-6 | AI assistance is measured before it is trusted | Evaluation Lab with a held-out split and a release gate (see `docs/eval/`) |

## 3. Scope
**In scope:** intake of a brief (paste or file), AI-assisted requirement extraction with evidence, requirement review
and clarification, deterministic feasibility and pricing, a frozen decision package, human approval (single or dual),
a separate execution authorization, sandboxed CRM and tracker writes with read-back verification, exception handling,
audit trail, evaluation of the extractor, an impact page on synthetic data.

**Out of scope:** real CRM/tracker connectors, SSO/MFA, OCR, email or Slack notifications, hosting, contract
signature, invoicing.

## 4. Stakeholders and personas
| Persona | Role in the process | Main concern |
|---|---|---|
| Deal Desk / Business Analyst | Turns the brief into a priced decision package | Complete, sourced requirements; fewer clarification loops |
| Commercial Manager (Approver) | Approves or returns the package; authorizes execution | Knowing exactly what is being approved and its risk |
| Automation Engineer | Runs and repairs the sandbox workflow | No duplicates, clear recovery path |
| AI Evaluation Analyst | Measures the extractor | Honest metrics on unseen data |
| Transformation Lead | Reads impact | Effect size with caveats, not marketing numbers |
| Workspace Admin | Rate cards, connectors, team | Control over what the system may touch |

## 5. Business rules (from the spec)
| ID | Rule |
|---|---|
| BR-001 | A decision package cannot be frozen while any critical requirement is unconfirmed, pricing is invalid, the rate card is outside its validity window, or the pricing target differs from the confirmed requirement |
| BR-002 | Pricing: variable = target × unit cost; total = variable + fixed; margin = (fee − total) / fee; integer rupiah, half-up, basis points; a zero fee is rejected |
| BR-003 | Approval binds to one exact package version and hash; a stale version or hash is refused |
| BR-004 | Changing a requirement or pricing after approval supersedes the package; the old snapshot and approval record stay unchanged; the new version needs a new review |
| BR-005 | Execution and each write step need an enabled connector for that action |
| BR-006 | HIGH risk (margin below floor, or a prompt-injection flag) needs two different approvers; below floor also needs a written exception request |
| BR-007 | Every write step has a stable idempotency key; a replay returns the existing record |
| BR-009 | Extracted values carry their evidence; a value without evidence is MISSING, never invented |
| BR-013 | A package priced on an expired or replaced rate card cannot be approved, authorized or executed |
| — | Segregation of duties: the package author cannot review it |
| — | Approving creates no external effect; execution needs a separate authorization |

## 6. Success measures and caveats
The impact page compares an assisted cohort with a concurrent manual cohort on cycle time and clarification rounds.
**The cohort is synthetic**, generated with a fixed seed; it shows how the measure is defined and displayed, not a
real improvement. A real rollout would need a baseline measured on the agency's own deals before go-live.

## 7. Assumptions, constraints, risks
| Type | Item |
|---|---|
| Assumption | Briefs are in English or Indonesian; amounts in rupiah (foreign currency is treated as missing) |
| Assumption | The rate card is maintained by the admin and has a validity window |
| Constraint | Demo runs on SQLite and simulated connectors; no external system is ever written |
| Risk | The rule-based extractor does not generalise to new phrasing: held-out v2 pass rate 42% [29%, 56%], below the 70% gate (see `docs/eval/EVAL_V2_RESULTS.md`). Mitigation: every AI value stays a DRAFT until a human confirms it; release of AI-assisted extraction is blocked |
| Risk | Prompt injection in client briefs: regex detection caught 1 of 6 new phrasings. Mitigation: brief text never grants permissions or changes state; approval is always human |
