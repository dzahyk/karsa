# UAT report — Karsa

| | |
|---|---|
| Build | Karsa at commit `a701e92`, demo-rules-1.2 extractor, SQLite, simulated connectors |
| Data | Seeded synthetic tenants Northstar and Bluepeak (`python -m app.seed`) |
| Run date | 12 Nov 2026, macOS, Chromium (Playwright) |
| Executed by | The builder, as **scripted acceptance**: each UAT script is automated by the checks listed in [`04_TRACEABILITY.md`](04_TRACEABILITY.md) |
| Not done | Acceptance by a real business user; manual screen-reader pass; Safari/Firefox; real connectors |

## How to reproduce

```bash
cd backend && uv run ruff check . && uv run pytest -v -p no:logging --junitxml=../docs/ba/evidence/backend-junit.xml
cd frontend && pnpm e2e --reporter=list,junit > ../docs/ba/evidence/e2e-run.txt
python3 docs/ba/build_pack.py
```

## Results by script

| Script | Scenario | Requirements | Result |
|---|---|---|---|
| UAT-01 | Create DCF-1042 from the Aster Labs brief; check every draft value's quote; confirm or edit with a reason; answer a clarification with channel + reference | FR-01, FR-02, FR-05, FR-06, FR-24 | Passed |
| UAT-02 | Open DCF-1046 (two budgets) and DCF-1051 (injection); pick a budget with a reason; confirm the flag changes nothing | FR-03, FR-04, FR-24 | Passed |
| UAT-03 | Price DCF-1042: expect Rp117,000,000 total and 22.00% margin; try to freeze with a missing requirement and with an expired rate card | FR-07, FR-08, FR-09, FR-16, FR-24 | Passed |
| UAT-04 | As Arif, approve the DCF-1042 package; try the author's own package; try rejecting without a note | FR-10, FR-12, FR-24 | Passed |
| UAT-05 | Run change request CR-001 on DCF-1043 (timeline 6 → 8 weeks) and check v1 + its approval are unchanged | FR-11, FR-24 | Passed |
| UAT-06 | DCF-1045 (6.82% vs 15% floor): first approval by Arif, second by Sari on a phone-width screen | FR-13, FR-24 | Passed |
| UAT-07 | Authorize execution separately; disable the tracker connector and retry authorization | FR-14, FR-15, FR-24 | Passed |
| UAT-08 | Run EX-0082: timeout after commit → reconcile; retry a pre-commit timeout; cancel a run and reopen | FR-17, FR-18, FR-19, FR-24 | Passed |
| UAT-09 | Sign in as each persona; open another tenant's DCF-2001; check the audit page; keyboard-only reject | FR-20, FR-21, FR-23 | Passed |
| UAT-10 | Run the Evaluation Lab; check dev vs held-out split, gate verdict, adjudicate one failure | FR-22 | Passed |

## Defects and observations

| ID | Severity | Observation | Status |
|---|---|---|---|
| OBS-01 | High (release blocker for AI extraction) | Rule extractor passes 21/50 unseen briefs (gate 70%) and catches 1/6 new injection phrasings — see `docs/eval/EVAL_V2_RESULTS.md` | Open. Mitigated: AI values stay drafts until confirmed; brief text grants no permissions |
| OBS-02 | Medium | Claude provider is implemented but has never been run live (no API key on the test machine) | Open |
| OBS-03 | Low | Claim detector flags a product guarantee ("we guarantee a replacement generator") as a campaign claim | Open |

## Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Business owner | — (fictional organisation) | Not signed | — |
| Business analyst | Daffa Zahy Khairy | Scripted acceptance recorded above | 12 Nov 2026 |
