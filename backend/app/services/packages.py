"""Decision packages: frozen canonical snapshot, SHA-256 hash, diff, and invalidation (BR-003/BR-004)."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..domain.hashing import content_hash
from ..domain.pricing import format_margin
from ..models import Case, DecisionPackage, SourceDocument, User
from . import audit, cases, feasibility, notifications
from .errors import DomainError

ACTION_CATALOG = {
    "crm.create_opportunity": ("Create CRM opportunity", "CRM sandbox",
                               "Create one opportunity for the approved fee and scope."),
    "tracker.create_project": ("Create tracker project", "Project tracker sandbox",
                               "Create one delivery project with the approved timeline."),
    "tracker.attach_spec": ("Attach specification", "Project tracker sandbox",
                            "Attach the approved package specification to the project."),
}
ACTIVE_STATES = ("IN_REVIEW", "APPROVED", "CHANGES_REQUESTED")
SCHEMA = "decision-package/1"


# Synthetic service catalogue for fit-gap analysis (spec FR-018).
CAPABILITIES = [
    ("Weekly performance dashboard", ("dashboard", "report", "laporan")),
    ("CRM sync of accepted leads", ("crm", "sync", "sinkron")),
    ("LinkedIn & paid social", ("linkedin", "social", "paid")),
    ("Paid search", ("search", "sem", "google ads")),
    ("Webinar production", ("webinar",)),
    ("Telemarketing qualification", ("telemarketing", "call", "telepon")),
    ("Event & booth follow-up", ("event", "booth", "trade show", "pameran")),
    ("Email nurture", ("email", "nurture", "newsletter")),
]


def fit_gap(reqs) -> list[dict]:
    """Match each requested item (deliverables, reporting) to the catalogue; unmatched items are gaps."""
    out = []
    for q in reqs:
        if q.key not in ("deliverables", "reporting") or not q.value:
            continue
        for item in [x.strip() for x in re.split(r",|;|\band\b|\bdan\b|\+", q.value) if x.strip()]:
            hit = next((name for name, kws in CAPABILITIES if any(k in item.lower() for k in kws)), None)
            out.append({"requested": item, "from": q.label, "capability": hit,
                        "fit": "Standard" if hit else "Gap — custom scoping needed"})
    return out


def get_package(session: Session, package_id: int, actor: User | None = None) -> DecisionPackage:
    pkg = session.get(DecisionPackage, package_id)
    if pkg is None or (actor is not None and pkg.case.organization_id != actor.organization_id):
        raise DomainError(404, "NOT_FOUND", "Package was not found.")
    return pkg


def _risk(margin_bp: int, floor_bp: int, open_items: int, flags: list) -> str:
    if margin_bp < floor_bp or any(f["kind"] == "prompt_injection" for f in flags):
        return "HIGH"
    if margin_bp < 3000 or open_items:
        return "MODERATE"
    return "LOW"


def build_content(session: Session, case: Case, run, card, actor: User, version: int,
                  exception_reason: str | None = None) -> dict:
    r = run.result
    reqs = case.requirements
    docs = {d.id: d for d in session.scalars(select(SourceDocument).where(SourceDocument.case_id == case.id))}
    requirements = []
    for q in reqs:
        src = None
        if q.source_document_id and q.quote is not None:
            d = docs[q.source_document_id]
            src = {"document": d.title, "document_sha256": d.sha256, "start": q.span_start, "end": q.span_end,
                   "quote": q.quote, "verification": d.verification, "channel": d.channel, "reference": d.reference}
        is_override = q.origin == "analyst" and q.quote is not None and q.value != q.extracted_value
        requirements.append({"key": q.key, "label": q.label, "critical": q.critical, "state": q.state,
                             "value": q.value, "value_type": q.value_type, "origin": q.origin, "source": src,
                             "overridden": is_override, "source_value": q.extracted_value if is_override else None})
    open_items = [q.label for q in reqs if not q.critical and q.state not in ("CONFIRMED", "NOT_APPLICABLE")]
    assumptions = [
        f"Unit cost Rp{run.inputs['unit_cost_idr']:,} per qualified lead and fixed cost "
        f"Rp{run.inputs['fixed_cost_idr']:,} from rate card {card.code} ({feasibility.SCENARIOS[run.scenario][0]} "
        "scenario). Synthetic demo rate card.",
        "Gross margin is before overhead and delivery risk; a margin is not proof of operational feasibility.",
    ]
    tl = next((q for q in reqs if q.key == "timeline"), None)
    if tl and tl.quote and any(w in tl.quote.lower() for w in ("month", "bulan")):
        assumptions.append(f"“{tl.quote}” converted to {tl.value} weeks at 4 weeks per month (demo assumption).")
    assumptions += run.assumptions
    claims = [f for f in case.flags if f["kind"] == "unsupported_claim"]
    risks = []
    if r["margin_bp"] < card.margin_floor_bp:
        risks.append(f"Margin {r['margin_pct']} is below the {format_margin(card.margin_floor_bp)} policy floor "
                     "— exception approval required.")
    for f in case.flags:
        if f["kind"] == "prompt_injection":
            risks.append(f"Brief contains instruction-like text (“{f['span']['quote']}”). Treated as data only.")
    for c in claims:
        risks.append(f"Client claim “{c['span']['quote']}” has no supporting data; not used as a fact.")
    if open_items:
        risks.append("Non-critical items still open: " + ", ".join(open_items) + ".")
    for q in requirements:
        if q["critical"] and q["source"] and q["source"]["verification"] == "analyst_recorded":
            risks.append(f"{q['label']} rests on an analyst's record of a {q['source']['channel']} "
                         f"({q['source']['reference']}), not the client's own words.")
        if q["overridden"]:
            risks.append(f"{q['label']} was overridden by the analyst; the source says something different.")
    assessment = feasibility.assess(case, card, run.inputs)
    gaps = fit_gap(reqs)
    if any(g["capability"] is None for g in gaps):
        risks.append("Fit-gap: some requested items are not standard services and need custom scoping.")
    actions = [{"action": a, "label": ACTION_CATALOG[a][0], "target": ACTION_CATALOG[a][1],
                "description": ACTION_CATALOG[a][2]} for a in case.action_hints if a in ACTION_CATALOG]
    req = {q.key: q for q in reqs}
    geo = req["geography"].value if req.get("geography") and req["geography"].value else "the agreed geography"
    recommendation = (
        f"Proceed with {case.client_name} — {case.title}: {run.inputs['target_units']:,} qualified leads in "
        f"{geo} over {run.inputs['duration_weeks']} weeks at a proposed fee of Rp{run.inputs['proposed_fee_idr']:,}. "
        f"Estimated total cost Rp{r['total_cost_idr']:,}; estimated gross margin {r['margin_pct']}."
    )
    return {
        "schema": SCHEMA,
        "case": {"code": case.code, "title": case.title, "client": case.client_name, "owner": case.owner.name},
        "version": version,
        "recommendation": recommendation,
        "recommendation_basis": "Generated from confirmed requirements and the deterministic calculation; "
                                "no free-form AI text.",
        "requirements": requirements,
        "pricing": {
            "feasibility_run_id": run.id, "scenario": run.scenario, "rate_card": card.code,
            "formula_version": r["formula_version"], "inputs": run.inputs,
            "variable_cost_idr": r["variable_cost_idr"], "total_cost_idr": r["total_cost_idr"],
            "gross_profit_idr": r["gross_profit_idr"], "margin_bp": r["margin_bp"], "margin_pct": r["margin_pct"],
            "margin_floor_bp": card.margin_floor_bp, "trace": r["trace"],
            "calculated_at": run.created_at.isoformat() + "Z",
        },
        "options": [{"scenario": k, **v, "recommended": k == run.scenario}
                    for k, v in assessment["scenario_comparison"].items()],
        "capacity": assessment["capacity"],
        "fit_gap": gaps,
        "exception": ({"reason": exception_reason, "requested_by": actor.name}
                      if exception_reason else None),
        "assumptions": assumptions,
        "risks": risks,
        "open_items": open_items,
        "evidence": [{"document": d.title, "kind": d.kind, "sha256": d.sha256,
                      "citations": sum(1 for q in reqs if q.source_document_id == d.id and q.quote)}
                     for d in docs.values()],
        "proposed_actions": actions,
        "prepared_by": actor.name,
        "synthetic": True,
    }


def validate_for_approval(content: dict) -> list[dict]:
    blockers = [{"code": "REQUIREMENT_NOT_CONFIRMED", "field": q["key"], "message": f"{q['label']} is not confirmed."}
                for q in content["requirements"] if q["critical"] and q["state"] != "CONFIRMED"]
    p = content.get("pricing") or {}
    if p.get("total_cost_idr") is None or p.get("margin_bp") is None:
        blockers.append({"code": "PRICING_MISSING", "field": "pricing", "message": "No valid pricing in package."})
    if not content.get("proposed_actions"):
        blockers.append({"code": "NO_ACTIONS", "field": "proposed_actions",
                         "message": "Package has no downstream actions to authorize."})
    return blockers


def assert_editable(session: Session, case: Case) -> None:
    reason = cases.lock_reason(session, case)
    if reason:
        raise DomainError(409, "CASE_LOCKED", reason)


def create_package(session: Session, actor: User, case: Case, exception_reason: str | None = None) -> DecisionPackage:
    assert_editable(session, case)
    run = feasibility.latest_run(session, case)
    if run is None:
        raise DomainError(422, "PACKAGE_BLOCKED", "Run and save a feasibility calculation first.",
                          {"blockers": [{"code": "NO_FEASIBILITY", "message": "No saved pricing calculation."}]})
    card = run.rate_card
    a = feasibility.assess(case, card, run.inputs)
    if a["blockers"]:
        raise DomainError(422, "PACKAGE_BLOCKED",
                          "The decision package cannot be created until these items are resolved.",
                          {"blockers": a["blockers"]})
    exception_reason = (exception_reason or "").strip() or None
    below_floor = run.result["margin_bp"] < card.margin_floor_bp
    if below_floor and (exception_reason is None or len(exception_reason) < 20):
        raise DomainError(422, "EXCEPTION_REQUIRED",
                          "Margin is below the policy floor. Write an exception request (20+ characters) explaining "
                          "why this deal should still be approved.", {"field": "exception_reason"})
    if not below_floor:
        exception_reason = None
    prev = cases.latest_package(session, case)
    version = (prev.version + 1) if prev else 1
    content = build_content(session, case, run, card, actor, version, exception_reason)
    risk = _risk(run.result["margin_bp"], card.margin_floor_bp, len(content["open_items"]), case.flags)
    pkg = DecisionPackage(case_id=case.id, version=version, content=content, content_hash=content_hash(content),
                          state="IN_REVIEW", risk_level=risk, required_approvals=2 if risk == "HIGH" else 1,
                          previous_id=prev.id if prev else None, created_by=actor.id)
    if prev and prev.state in ACTIVE_STATES:
        prev.state = "SUPERSEDED"
        prev.superseded_reason = f"Replaced by package v{version}."
    session.add(pkg)
    session.flush()
    audit.record(session, actor, "package.created", "package", pkg.id,
                 f"Decision package v{version} frozen ({pkg.content_hash[:19]}…) and sent for review"
                 + (f"; {pkg.required_approvals} approvals required (high risk)." if pkg.required_approvals > 1 else "."),
                 case.id, {"hash": pkg.content_hash, "version": version})
    notifications.notify_roles(session, case.organization_id, ("APPROVER",), "package.submitted",
                               f"Review needed: {case.client_name} v{version}",
                               f"{actor.name} sent {case.code} package v{version} for review ({risk.lower()} risk).",
                               f"/approvals/{pkg.id}")
    cases.refresh_status(session, case)
    return pkg


def supersede_active(session: Session, actor: User, case: Case, reason: str, *,
                     new_pricing_inputs: dict | None = None, new_scenario: str | None = None) -> None:
    """BR-004: a change to inputs after a package was frozen invalidates its review/approval."""
    pkg = cases.latest_package(session, case)
    if pkg is None or pkg.state not in ACTIVE_STATES:
        cases.refresh_status(session, case)
        return
    if new_pricing_inputs is not None and pkg.content["pricing"]["inputs"] == new_pricing_inputs \
            and pkg.content["pricing"]["scenario"] == new_scenario:
        cases.refresh_status(session, case)
        return  # identical recalculation: nothing changed
    was = pkg.state
    pkg.state = "SUPERSEDED"
    pkg.superseded_reason = reason
    audit.record(session, actor, "package.invalidated", "package", pkg.id,
                 f"Package v{pkg.version} ({was.lower().replace('_', ' ')}) invalidated: {reason} "
                 "A new version and a new review are required.", case.id, {"previous_state": was})
    cases.refresh_status(session, case)


def diff(prev: dict | None, cur: dict) -> list[dict]:
    if prev is None:
        return []
    out = []

    def add(field: str, label: str, a, b, kind: str = "text"):
        if a != b:
            out.append({"field": field, "label": label, "before": a, "after": b, "kind": kind})

    pr, cr = {q["key"]: q for q in prev["requirements"]}, {q["key"]: q for q in cur["requirements"]}
    for k, q in cr.items():
        p = pr.get(k, {})
        if p.get("value") != q["value"] or p.get("state") != q["state"]:
            out.append({"field": f"requirements.{k}", "label": q["label"], "kind": q["value_type"],
                        "before": {"value": p.get("value"), "state": p.get("state")},
                        "after": {"value": q["value"], "state": q["state"]}})
    pp, cp = prev["pricing"], cur["pricing"]
    add("pricing.proposed_fee_idr", "Proposed fee", pp["inputs"]["proposed_fee_idr"],
        cp["inputs"]["proposed_fee_idr"], "idr")
    add("pricing.total_cost_idr", "Total estimated cost", pp["total_cost_idr"], cp["total_cost_idr"], "idr")
    add("pricing.margin_bp", "Estimated gross margin", pp["margin_bp"], cp["margin_bp"], "bp")
    add("pricing.target_units", "Target leads", pp["inputs"]["target_units"], cp["inputs"]["target_units"], "integer")
    add("pricing.duration_weeks", "Duration", pp["inputs"]["duration_weeks"], cp["inputs"]["duration_weeks"], "weeks")
    add("pricing.scenario", "Pricing scenario", pp["scenario"], cp["scenario"])
    add("pricing.rate_card", "Rate card", pp["rate_card"], cp["rate_card"])
    added = [x for x in cur["assumptions"] if x not in prev["assumptions"]]
    removed = [x for x in prev["assumptions"] if x not in cur["assumptions"]]
    if added or removed:
        out.append({"field": "assumptions", "label": "Assumptions", "kind": "list", "before": removed, "after": added})
    add("proposed_actions", "Downstream actions", [a["action"] for a in prev["proposed_actions"]],
        [a["action"] for a in cur["proposed_actions"]], "list")
    return out


def now_iso() -> str:
    return utcnow().isoformat() + "Z"
