# Extractor evaluation v2 — pre-registered protocol

Written and committed on 2026-11-12, **before** any change to `backend/app/domain/extraction.py`.

## Why a v2
Held-out v1 (36 briefs) scored 1/36 (field F1 0.779) against a rule extractor that scored 24/24 on the dev split.
The rules only read labelled lines, so 28 briefs that state the lead definition in prose failed. That result is
kept as the historical baseline (commit `b84571b`) and is not overwritten.

## Splits
| Split | Cases | Role in v2 |
|---|---|---|
| dev (`dataset.py`) | 24 | seen; used for rule changes |
| held-out v1 (`heldout.py`) | 36 | **now seen**; its failures are used to revise rules, so after this point it is a development set, not a held-out set |
| held-out v2 (`heldout_v2.py`) | 50 | new; frozen below; scored once after the rule revision |

## Frozen inputs
- `backend/app/evaluation/heldout_v2.py` SHA-256 `d7915c9b763f7f575fedd6001e6627430dfd0b440c0a0aafb1952822ad2cb047`
- extractor before revision, `backend/app/domain/extraction.py` SHA-256 `71c471f72b275a7a0cf32c676d5f42c5c7cb7c64cb36fd41e25b8fba3d6f67be`

## Release gate (unchanged from v1, applied to held-out v2)
| Check | Threshold |
|---|---|
| Complete-case pass rate | ≥ 0.70 |
| Pricing calculation exact | 1.00 |
| Prompt-injection recall | 1.00 |
| Grounded spans (quote equals source text) | 1.00 |

## What will be reported, whatever the outcome
- Complete-case pass rate with a Wilson 95% interval, per split.
- Field-level precision, recall and F1 for each field (target_leads, budget, timeline, lead_definition, geography).
- Flag recall and false-positive rate for prompt_injection and unsupported_claim (v2 has 2 negative controls).
- An error taxonomy of every failing v2 case.
- Gate verdict. If the gate fails, the result is published as a failure and the release stays blocked.

## Rules for the run
1. Revise the extractor using dev + held-out v1 only.
2. Commit the revision. Record its SHA-256.
3. Score held-out v2 once. No further rule changes are counted against v2; any later fix needs a v3 set.

## Known limits
- v2 was written by the same author who revises the rules (an AI coding agent), before the revision. Independence
  comes from ordering and hashing, not from a different person. A human adjudication of v2 labels is still open.
- 50 cases give wide intervals (±~13 points at 70%).
- A live LLM provider (Claude) is not evaluated here: no API key is configured on this machine.
