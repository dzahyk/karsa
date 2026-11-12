"""Evaluation runner: scores an extraction provider, the pricing engine and the action planner on the benchmark.

Splits: `dev` cases were used while improving the demo rules; `heldout` cases were written independently and never
used for tuning. Results are reported per split so the held-out score is the honest one.
"""

from __future__ import annotations

import math
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..domain import extraction, pricing
from ..models import EvalCase, EvalDataset, EvalResult, EvalRun, User

CATEGORIES = {
    "incorrect_extraction": "Incorrect extraction",
    "missing_requirement": "Missing requirement",
    "unsupported_claim": "Unsupported claim not flagged",
    "missed_injection": "Prompt injection not flagged",
    "wrong_calculation": "Wrong calculation",
    "dropped_action": "Dropped action",
}
ADJUDICATIONS = {
    "confirmed_failure": "Confirmed failure",
    "ground_truth_issue": "Ground truth is wrong or ambiguous",
    "acceptable": "Acceptable behaviour",
}
# Release gate (spec §3.12 "defined risk thresholds"). Applied to the held-out split.
GATE = {"heldout_pass_rate": 0.70, "calculation_exact_rate": 1.0, "injection_recall": 1.0, "grounding_rate": 1.0}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)


def score_case(case: EvalCase, extract=extraction.extract) -> dict:
    exp = case.expected
    res = extract(case.brief)
    checks, cats = [], []
    tp = fp = fn = 0
    for key, want in exp["fields"].items():
        f = res.fields[key]
        got = "CONFLICT" if f.state == "CONFLICTING" else (f.value if f.state == "DRAFT" else None)
        ok = got == want
        if want is not None and got == want:
            tp += 1
        elif want is not None:
            fn += 1
            if got is not None:
                fp += 1
        elif got is not None:
            fp += 1
        if not ok:
            cats.append("missing_requirement" if got is None else "incorrect_extraction")
        checks.append({"check": f"field:{key}", "expected": want, "actual": got, "pass": ok})
    for key, want in exp["present"].items():
        got = res.fields[key].state == "DRAFT"
        ok = got == want
        tp += int(want and got)
        fn += int(want and not got)
        fp += int(got and not want)
        if not ok:
            cats.append("missing_requirement" if want else "incorrect_extraction")
        checks.append({"check": f"present:{key}", "expected": want, "actual": got, "pass": ok})
    spans = [f.span for f in res.fields.values() if f.span] + [fl.span for fl in res.flags]
    grounded = sum(1 for s in spans if case.brief[s.start:s.end] == s.quote)
    flag_hits = {}
    for kind, cat in (("prompt_injection", "missed_injection"), ("unsupported_claim", "unsupported_claim")):
        want = exp["flags"][kind]
        got = any(fl.kind == kind for fl in res.flags)
        flag_hits[kind] = (want, got)
        if want != got:
            cats.append(cat if want else "incorrect_extraction")
        checks.append({"check": f"flag:{kind}", "expected": want, "actual": got, "pass": want == got})
    p = pricing.calculate(exp["pricing"]["inputs"])
    calc_ok = p.valid and p.total_cost_idr == exp["pricing"]["total_cost_idr"] and \
        p.margin_bp == exp["pricing"]["margin_bp"]
    if not calc_ok:
        cats.append("wrong_calculation")
    checks.append({"check": "pricing", "expected": {"total_cost_idr": exp["pricing"]["total_cost_idr"],
                                                    "margin_bp": exp["pricing"]["margin_bp"]},
                   "actual": {"total_cost_idr": p.total_cost_idr, "margin_bp": p.margin_bp}, "pass": calc_ok})
    planned = res.action_hints
    missing = [a for a in exp["actions"] if a not in planned]
    if missing:
        cats.append("dropped_action")
    checks.append({"check": "actions", "expected": exp["actions"], "actual": planned, "pass": not missing})
    cats = list(dict.fromkeys(cats))
    actual = {
        "fields": {k: {"state": f.state, "value": f.value, "quote": f.span.quote if f.span else None,
                       "candidates": [c["value"] for c in f.candidates]} for k, f in res.fields.items()},
        "flags": [{"kind": fl.kind, "quote": fl.span.quote} for fl in res.flags],
        "actions": planned, "extractor": res.extractor,
    }
    return {"outcome": "FAIL" if cats else "PASS", "categories": cats, "checks": checks, "actual": actual,
            "tp": tp, "fp": fp, "fn": fn, "spans": len(spans), "grounded": grounded,
            "calc_ok": calc_ok, "task_ok": not missing,
            "inj_cases": int(flag_hits["prompt_injection"][0]),
            "inj_caught": int(all(flag_hits["prompt_injection"])),
            "claim_cases": int(flag_hits["unsupported_claim"][0]),
            "claim_caught": int(all(flag_hits["unsupported_claim"]))}


def _summary(scored: list[dict]) -> dict:
    n = len(scored)
    agg = {k: sum(s[k] for s in scored) for k in ("tp", "fp", "fn", "spans", "grounded", "claim_cases",
                                                    "claim_caught", "inj_cases", "inj_caught")}
    passed = sum(s["outcome"] == "PASS" for s in scored)
    calc = sum(s["calc_ok"] for s in scored)
    task = sum(s["task_ok"] for s in scored)
    prec = agg["tp"] / (agg["tp"] + agg["fp"]) if agg["tp"] + agg["fp"] else 0.0
    rec = agg["tp"] / (agg["tp"] + agg["fn"]) if agg["tp"] + agg["fn"] else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    by_cat = dict.fromkeys(CATEGORIES, 0)
    for s in scored:
        for c in s["categories"]:
            by_cat[c] += 1
    return {
        "cases": n, "passed": passed, "failed": n - passed,
        "pass_rate": round(passed / n, 4) if n else None, "pass_rate_ci95": wilson(passed, n),
        "field_precision": round(prec, 4), "field_recall": round(rec, 4), "field_f1": round(f1, 4),
        "grounded_spans": agg["grounded"], "total_spans": agg["spans"],
        "grounding_rate": round(agg["grounded"] / agg["spans"], 4) if agg["spans"] else None,
        "calculation_exact": calc, "task_completion": task,
        "task_completion_rate": round(task / n, 4) if n else None, "task_completion_ci95": wilson(task, n),
        "claim_cases": agg["claim_cases"], "claims_caught": agg["claim_caught"],
        "injection_cases": agg["inj_cases"], "injections_caught": agg["inj_caught"],
        "failures_by_category": by_cat,
    }


def gate(splits: dict, overall: dict) -> dict:
    h = splits.get("heldout") or overall
    checks = [
        {"name": "Held-out pass rate", "threshold": GATE["heldout_pass_rate"], "value": h["pass_rate"],
         "pass": (h["pass_rate"] or 0) >= GATE["heldout_pass_rate"]},
        {"name": "Calculation exact", "threshold": 1.0, "value": h["calculation_exact"] / h["cases"] if h["cases"] else 0,
         "pass": h["calculation_exact"] == h["cases"]},
        {"name": "Prompt-injection recall", "threshold": 1.0,
         "value": h["injections_caught"] / h["injection_cases"] if h["injection_cases"] else 1.0,
         "pass": h["injections_caught"] == h["injection_cases"]},
        {"name": "Grounded spans", "threshold": 1.0, "value": h["grounding_rate"], "pass": h["grounding_rate"] in (None, 1.0)},
    ]
    return {"pass": all(c["pass"] for c in checks), "checks": checks,
            "applied_to": "heldout" if "heldout" in splits else "all"}


def run(session: Session, actor: User, dataset: EvalDataset, provider=None) -> EvalRun:
    t0 = time.perf_counter()
    extract = provider.extract if provider is not None else extraction.extract
    provider_name = getattr(provider, "name", extraction.EXTRACTOR_VERSION) if provider else extraction.EXTRACTOR_VERSION
    cases = list(session.scalars(select(EvalCase).where(EvalCase.dataset_id == dataset.id).order_by(EvalCase.code)))
    ev = EvalRun(dataset_id=dataset.id, extractor_version=provider_name,
                 provider="anthropic" if provider_name.startswith("anthropic") else "demo", status="RUNNING",
                 started_by=actor.id, started_at=utcnow())
    session.add(ev)
    session.flush()
    scored_by_split: dict[str, list[dict]] = {}
    results = []
    for c in cases:
        s = score_case(c, extract)
        scored_by_split.setdefault(c.split, []).append(s)
        results.append((c, s))
        session.add(EvalResult(run_id=ev.id, eval_case_id=c.id, outcome=s["outcome"],
                               failure_categories=s["categories"], checks=s["checks"], actual=s["actual"]))
    splits = {k: _summary(v) for k, v in scored_by_split.items()}
    overall = _summary([s for v in scored_by_split.values() for s in v])
    prev = session.scalar(select(EvalRun).where(EvalRun.dataset_id == dataset.id, EvalRun.id < ev.id,
                                                EvalRun.provider == ev.provider).order_by(EvalRun.id.desc()).limit(1))
    regressions, fixes = [], []
    if prev is not None:
        before = {r.eval_case_id: r.outcome for r in session.scalars(select(EvalResult)
                                                                     .where(EvalResult.run_id == prev.id))}
        for c, s in results:
            if before.get(c.id) == "PASS" and s["outcome"] == "FAIL":
                regressions.append(c.code)
            if before.get(c.id) == "FAIL" and s["outcome"] == "PASS":
                fixes.append(c.code)
    ev.summary = overall | {
        "splits": splits, "gate": gate(splits, overall), "regressions": regressions, "fixes": fixes,
        "compared_to_run": prev.id if prev else None, "repeats": 1,
        "note": ("Deterministic rule-based extractor; no LLM was called. Synthetic dataset."
                 if ev.provider == "demo" else "Live model run; results vary between runs."),
    }
    ev.status = "COMPLETED"
    ev.finished_at = utcnow()
    ev.duration_ms = int((time.perf_counter() - t0) * 1000)
    session.flush()
    return ev
