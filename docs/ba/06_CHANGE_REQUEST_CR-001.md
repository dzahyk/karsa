# Change request CR-001 — extend DCF-1043 from 6 to 8 weeks

| | |
|---|---|
| Case | DCF-1043 · Webinar Lead Program · Northbridge Health (fictional, seeded) |
| Raised by | Approver, when returning package v1 with *Request changes* |
| Reviewer note (verbatim, seed data) | "Six weeks is too tight for hospital procurement cycles. Extend to 8 weeks and reprice." |
| Client confirmation | Analyst-recorded: "client agreed on the call of 10 Nov (see call notes)" — labelled as analyst evidence, not client text |
| Decision | Accepted; package v2 created and sent for a new review |

## 1. What changes
| Item | v1 | v2 |
|---|---|---|
| Timeline requirement | 6 weeks (from the brief) | 8 weeks (edited with a reason; marked as an override of the brief) |
| Required delivery rate | 1,500 ÷ 6 = 250 leads/week | 1,500 ÷ 8 = 187.5 leads/week |
| Pricing | priced on 6 weeks | re-priced on 8 weeks (new pricing run, same rate card) |
| Package | v1, status *changes requested* | v2, new hash, *awaiting approval* |

## 2. Impact analysis
| Area | Impact | Handled by |
|---|---|---|
| Requirements | Timeline no longer matches the brief → must carry a reason and an override flag | FR-05 (versioned edit with reason) |
| Capacity | Lower weekly rate; the capacity check is re-run on the new pricing | FR-08 |
| Pricing | v1 pricing is stale against the confirmed timeline → package gate blocks until re-priced | FR-09 (pricing target must match the confirmed requirement) |
| Package | v2 is a new frozen snapshot with its own hash; v1 and its review note stay unchanged | FR-11, FR-21 (append-only) |
| Approval | No approval carries over; v2 needs a new review, and the reviewer sees a diff (timeline 6 → 8) plus the previous note | FR-10, FR-11 |
| Execution | Nothing was authorized for v1, so no external system is touched | FR-14 |
| Audit | Edit, re-pricing, new package and both reviews are audit events with request IDs | FR-21 |

## 3. Verification
- Seeded demo: open DCF-1043 → *Decision package* shows v2 with the diff against v1 and the previous reviewer note.
- Automated: `test_change_after_approval_creates_new_version_and_keeps_old_snapshot` (same rule after an
  *approval*, the stricter case), `test_stale_versions_get_409`, and the keyboard-only E2E journey that compares
  changes and rejects. All passed in the run recorded in [`05_UAT_REPORT.md`](05_UAT_REPORT.md).
