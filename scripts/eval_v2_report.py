"""Score held-out v2 once with extractor 1.1 (baseline, commit b84571b) and 1.2, and print a report as JSON.

Usage (from backend/):  PYTHONPATH=. uv run python ../scripts/eval_v2_report.py
Refuses to run if heldout_v2.py no longer matches the SHA-256 frozen in docs/eval/EVAL_V2_PROTOCOL.md.
"""
import hashlib, json, math, pathlib, re, sys
from types import SimpleNamespace as NS

from app.domain import extraction as rules_12, extraction_v1_1 as rules_11
from app.evaluation import runner
from app.evaluation.heldout_v2 import CASES

ROOT = pathlib.Path(__file__).resolve().parents[1]
frozen = re.search(r"heldout_v2\.py\` SHA-256 \`([0-9a-f]{64})", (ROOT / "docs/eval/EVAL_V2_PROTOCOL.md").read_text())
actual = hashlib.sha256((ROOT / "backend/app/evaluation/heldout_v2.py").read_bytes()).hexdigest()
if not frozen or frozen.group(1) != actual:
    sys.exit(f"heldout_v2.py changed since it was frozen ({actual})")

FIELDS = ["target_leads", "budget", "timeline"]
PRESENT = ["lead_definition", "geography"]


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None; r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    return {"precision": p and round(p, 3), "recall": r and round(r, 3), "f1": f and round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def score(extract):
    rows = [(c, runner.score_case(NS(**c), extract=extract)) for c in CASES]
    out = {"cases": len(rows), "passed": sum(r["outcome"] == "PASS" for _, r in rows)}
    out["pass_rate"] = round(out["passed"] / out["cases"], 3); out["pass_rate_ci95"] = wilson(out["passed"], out["cases"])
    per = {}
    for key in FIELDS + PRESENT:
        tp = fp = fn = 0
        kind = "field" if key in FIELDS else "present"
        for c, r in rows:
            ch = next(x for x in r["checks"] if x["check"] == f"{kind}:{key}")
            want, got = ch["expected"], ch["actual"]
            if kind == "present":
                tp += want and got; fp += (not want) and got; fn += want and not got
            else:
                if want is not None and got == want: tp += 1
                else:
                    if want is not None: fn += 1
                    if got is not None: fp += 1
        per[key] = prf(tp, fp, fn)
    out["fields"] = per
    for flag in ("prompt_injection", "unsupported_claim"):
        pos = [r for c, r in rows if c["expected"]["flags"][flag]]
        neg = [r for c, r in rows if not c["expected"]["flags"][flag]]
        hit = lambda r: next(x for x in r["checks"] if x["check"] == f"flag:{flag}")["actual"]
        out[flag] = {"recall": f"{sum(hit(r) for r in pos)}/{len(pos)}", "false_positives": f"{sum(hit(r) for r in neg)}/{len(neg)}"}
    out["actions_ok"] = f"{sum(r['task_ok'] for _, r in rows)}/{len(rows)}"
    out["grounded_spans"] = f"{sum(r['grounded'] for _, r in rows)}/{sum(r['spans'] for _, r in rows)}"
    out["calc_exact"] = f"{sum(r['calc_ok'] for _, r in rows)}/{len(rows)}"
    gate = {"pass_rate>=0.70": out["pass_rate"] >= 0.70, "calc_exact=1": out["calc_exact"].split("/")[0] == out["calc_exact"].split("/")[1],
            "injection_recall=1": out["prompt_injection"]["recall"].split("/")[0] == out["prompt_injection"]["recall"].split("/")[1],
            "grounded=1": out["grounded_spans"].split("/")[0] == out["grounded_spans"].split("/")[1]}
    out["gate"] = gate; out["gate_pass"] = all(gate.values())
    out["failures"] = [{"code": c["code"], "category": c["category"], "taxonomy": r["categories"],
                        "checks": [(x["check"], x["expected"], x["actual"]) for x in r["checks"] if not x["pass"]]}
                       for c, r in rows if r["outcome"] == "FAIL"]
    return out


print(json.dumps({"heldout_v2_sha256": actual, "rules_1_1": score(rules_11.extract), "rules_1_2": score(rules_12.extract)},
                 indent=1, ensure_ascii=False, default=str))
