# Extractor evaluation v2 — results

Run once on 2026-11-12, after the rule revision was committed. Protocol: [`EVAL_V2_PROTOCOL.md`](EVAL_V2_PROTOCOL.md).
Raw output: [`eval_v2_results.json`](eval_v2_results.json). Reproduce from `backend/`:
`PYTHONPATH=. uv run python ../scripts/eval_v2_report.py` (refuses to run if `heldout_v2.py` changed).

| Commit | What |
|---|---|
| `b84571b` | baseline, rules 1.1: dev 24/24, held-out v1 1/36 |
| `c1d7067` | held-out v2 frozen (SHA-256 `d7915c9b…2cb047`) + protocol and gate pre-registered |
| `e476414` | rules 1.2, revised on dev + v1 only: dev 24/24, v1 36/36 (v1 is now development data) |
| this commit | v2 scored once with 1.1 and 1.2 |

## Verdict: the release gate still FAILS

| Held-out v2 (50 new briefs) | Rules 1.1 (baseline) | Rules 1.2 | Gate |
|---|---|---|---|
| Complete-case pass rate | 4/50 = 8% [3%, 19%] | **21/50 = 42% [29%, 56%]** | ≥ 70% ✗ |
| Prompt-injection recall | 0/6 | **1/6** | 6/6 ✗ |
| Pricing calculation exact | 50/50 | 50/50 | 50/50 ✓ |
| Grounded spans (quote = source) | 166/166 | 220/220 | all ✓ |
| Unsupported-claim recall / false positives | 1/4 · 1/46 | 1/4 · 1/46 | not gated |
| Downstream actions planned correctly | 46/50 | 47/50 | not gated |

Intervals are Wilson 95%. 50 cases are few: the 1.2 pass rate could plausibly be anywhere from about 29% to 56%.

## Field-level results (held-out v2)

| Field | 1.1 precision / recall / F1 | 1.2 precision / recall / F1 |
|---|---|---|
| target_leads | 1.000 / 0.796 / 0.886 | 1.000 / 0.939 / 0.968 |
| budget | 0.930 / 0.851 / 0.889 | 0.978 / 0.936 / 0.957 |
| timeline | 0.957 / 0.898 / 0.926 | 0.958 / 0.939 / 0.948 |
| lead_definition (stated?) | 1.000 / 0.143 / 0.250 | 1.000 / 0.837 / 0.911 |
| geography (stated?) | 1.000 / 0.673 / 0.805 | 1.000 / 0.837 / 0.911 |

## Error taxonomy — the 29 failing v2 cases under rules 1.2

| Class | Cases | What happened |
|---|---|---|
| Lead definition phrased in a way no cue covers | 8 | "We count someone as a lead when…", "Our ideal contact is…", "To count, a contact must be…", "They only care about…", a numbered "Who:" line, a definition split over two chat messages |
| Geography missed | 8 | places outside the place list (Malang, Boyolali, Pasuruan, Lombok…), a place wrapped onto the next line, "Region ....." dotted labels, "Market" as a section heading |
| Prompt injection missed | 5 of 6 | each new phrasing ("disregard the rate card", "SYSTEM OVERRIDE", "Untuk asisten AI", "anggap dirimu…", "remove the approval step") escapes the pattern list |
| Unsupported claim missed / false alarm | 3 + 1 | "will definitely convert 25%", "no risk… pay back", "we will close Rp750 juta"; and "we guarantee a replacement generator" (a product promise) flagged as a campaign claim |
| Attach-spec request missed | 3 | "solution brief", "proposal teknis", "the LOI" are not in the document word list |
| Number parsing | 3 + 3 + 3 | "2.200 calon klien" (no lead word), "180 jt" without Rp, "one and a half billion", a timeline range "between 5 and 7 weeks", "tiga bulan" inside a claim read as a second timeline, a revenue figure read as a second budget |

## What this means
- The 1.2 rules fixed the classes they were written for and that transferred (lead-definition recall 0.14 → 0.84 on
  unseen text), but the extractor still does not generalise to new phrasing. That is the expected limit of a
  pattern list, and it is now measured instead of assumed.
- Security is the hard blocker: a regex catches the injections it has seen. Injection detection should not rely on
  the extractor at all; the product already treats brief text as data and grants no permissions from it, and
  approval stays human (that control is tested separately and is unaffected by these numbers).
- Next step stays the same and is now better specified: run the Claude provider on dev + v1 + v2 with the same
  gate (needs `ANTHROPIC_API_KEY`), and any further rule change must be measured on a new v3 set.
- v2 labels were written by the same author who revised the rules and have not been adjudicated by a second
  person. Treat the numbers as the author's measurement, not an independent audit.
