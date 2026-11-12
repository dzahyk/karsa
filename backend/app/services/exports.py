"""Human-readable exports. Every export repeats the snapshot hash so a reader can check it."""

from __future__ import annotations

import csv
import io

from ..models import ApprovalRecord, DecisionPackage, ImpactCohortCase


def _idr(n) -> str:
    return "—" if n is None else f"Rp{n:,}"


def package_markdown(pkg: DecisionPackage, approvals: list[ApprovalRecord], names: dict[str, str]) -> str:
    c = pkg.content
    p = c["pricing"]
    lines = [
        f"# Decision package — {c['case']['client']}: {c['case']['title']}",
        "",
        "> SYNTHETIC DEMO DATA — not a real offer.",
        "",
        f"- Case: {c['case']['code']} · Package v{pkg.version} · State: {pkg.state} · Risk: {pkg.risk_level}",
        f"- Snapshot hash: `{pkg.content_hash}`",
        f"- Prepared by: {c['prepared_by']} · Approvals required: {pkg.required_approvals}",
        "",
        "## Recommendation",
        c["recommendation"],
        "",
        f"_{c['recommendation_basis']}_",
        "",
        "## Commercials",
        f"| Item | Value |\n|---|---|\n| Target leads | {p['inputs']['target_units']:,} |\n"
        f"| Duration | {p['inputs']['duration_weeks']} weeks |\n| Proposed fee | {_idr(p['inputs']['proposed_fee_idr'])} |\n"
        f"| Total estimated cost | {_idr(p['total_cost_idr'])} |\n| Estimated gross margin | {p['margin_pct']} |\n"
        f"| Rate card / scenario | {p['rate_card']} / {p['scenario']} |",
        "",
        "Calculation trace:",
        *[f"- `{t}`" for t in p["trace"]],
        "",
        "## Requirements",
        "| Requirement | Value | State | Source |\n|---|---|---|---|",
        *[f"| {q['label']} | {q['value'] or '—'} | {q['state']}{' (overridden)' if q.get('overridden') else ''} | "
          f"{('“' + q['source']['quote'][:80].replace('|', '/') + '” — ' + q['source']['document']) if q['source'] else '—'} |"
          for q in c["requirements"]],
        "",
        "## Options",
        *[f"- {o['label']}: total {_idr(o['total_cost_idr'])}, margin {o['margin_pct']}"
          f"{' (recommended)' if o['recommended'] else ''}" for o in c.get("options", [])],
        "",
        "## Assumptions", *[f"- {a}" for a in c["assumptions"]], "",
        "## Risks", *([f"- {r}" for r in c["risks"]] or ["- None raised by the rules"]), "",
        "## Downstream actions (sandbox)", *[f"- {a['label']} — {a['target']}" for a in c["proposed_actions"]], "",
        "## Review history",
        *([f"- {a.decision} by {names.get(a.actor_id, a.actor_id)} at {a.created_at:%Y-%m-%d %H:%M} UTC "
           f"(hash {a.package_hash[:19]}…){': ' + a.note if a.note else ''}" for a in approvals] or ["- None yet"]),
    ]
    return "\n".join(lines) + "\n"


def cohort_csv(rows: list[ImpactCohortCase]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "period", "flow", "segment", "handler_id", "created_at", "decided_at", "reviewed", "approved",
                "verified", "overridden", "override_reason", "workflow_status", "synthetic"])
    for r in rows:
        w.writerow([r.code, r.period, r.flow, r.segment, r.handler_id, r.created_at.isoformat(),
                    r.decided_at.isoformat() if r.decided_at else "", r.reviewed, r.approved, r.verified,
                    r.overridden, r.override_reason or "", r.workflow_status or "", True])
    return buf.getvalue()
