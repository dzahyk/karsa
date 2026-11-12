# Demo guide (≈12 minutes)

Reset first: `cd backend && uv run python -m app.seed --reset`, start the API and web app, open the web URL.
Say up front: *all data is synthetic; the extractor is a rule-based demo; connectors are sandboxes.*

## 1. Sign in and roles
1. The sign-in page lists demo accounts (DEMO_MODE). Sign in as **Nadia Rahman** (analyst).
2. Point out the navigation: only Cases, Approvals, Workflows. Each role sees what the server lets it read.

## 2. Evidence, not magic — DCF-1042 Aster Labs
3. Cases are sorted by urgency. Open **DCF-1042**.
4. Click **Budget**: the exact text is highlighted. Click **Geography**: “to be determined” → Missing.
5. Optional: **New request → Upload file** with a text PDF to show real page numbers; a scanned PDF is refused.

## 3. Numbers from rules — Feasibility
6. Rp105,000,000 → Rp117,000,000 → **22.00 %**, calculation trace, three-scenario table, capacity 375/400 per week.
7. Create package is disabled and says why.

## 4. Close the gaps with checkable evidence
8. Requirements → **Record answer** for both questions: channel *email*, a reference (“Email ‘Re: lead criteria’,
   11 Nov”), and paste the client's own words. Without the paste the evidence is labelled *analyst-recorded*.
9. Feasibility → **Create decision package** → approval review (v1, hash, options, fit-gap, Markdown/JSON export).

## 5. Approval and separate authorization — switch to Arif (header account switcher)
10. Approve with a note. The execution panel shows *approved, not authorized*.
11. **Authorize execution** — tick each sandbox action.

## 6. Controlled, asynchronous execution — switch to Jordan
12. Failure injection “Tracker timeout before commit” → **Run sandbox workflow**. The run is *Queued*, the worker picks it
    up, the page updates by itself (pause control available): tracker step failed, nothing created.
13. **Review and retry** → *Verified*, 2 of 2 records read back.
14. **Workflows → EX-0082**: unknown outcome, retry disabled → **Check target system** links the existing record.
15. **Workflows → Exception queue → EX-0084**: incident from a disabled connector. Retry, then resolve the incident.

## 7. Two-person rule — DCF-1045 Crestview (high risk)
16. As Arif: “1 of 2 approvals recorded”, the exception request, and the approve button is disabled for him.
17. Switch to **Sari** (or use a phone-width window): **Approve (2 of 2)** with a note → approved.

## 8. Change control
18. As Nadia on **DCF-1048** (rejected): the case is locked → **Reopen case** with a reason.
19. As **Bima** (admin) → Manage → publish a new rate card version. Approved-but-unrun packages on RC-3 (e.g. DCF-1050)
    now show “Rate card RC-3 is no longer valid” and cannot be authorized until repriced.

## 9. Is the AI any good? — Priya
20. Evaluation Lab: **Held-out 1/36** vs **Dev 24/24**, release gate **failed**. Open a failed held-out trace, add an
    adjudication. Message: the dev score was tuned; the held-out score is the honest one.

## 10. Did it help? — Dewi
21. Impact: adoption by people and by cases, cycle-time medians with n, insufficient-sample markers, causation caveat,
    live metrics from the demo DB, CSV export.

## 11. Audit — Lia
22. Audit log with request IDs; the database itself rejects edits to it.

## Talking points
- AI drafts, people confirm; every value has a checkable source or is visibly missing.
- Prices and capacity come from versioned rules; approvals bind to a hash; high risk needs two people.
- Execution is queued, idempotent and recoverable; failures stay visible until a person resolves them.
- Evaluation separates tuned and held-out data and reports the bad news.
