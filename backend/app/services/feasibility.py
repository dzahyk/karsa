"""Feasibility & pricing service: rate card lookup, deterministic calculation, blockers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..domain import pricing
from ..domain.pricing import format_margin
from ..models import Case, FeasibilityRun, RateCard, User
from . import audit
from .errors import DomainError

SCENARIOS = {
    "conservative": ("Conservative", "unit_cost_conservative_idr", "Unit cost +10% (delivery risk buffer)"),
    "expected": ("Expected", "unit_cost_expected_idr", "Rate card expected unit cost"),
    "aggressive": ("Aggressive", "unit_cost_aggressive_idr", "Unit cost −10% (best-case efficiency)"),
}


def current_rate_card(session: Session, org_id: str) -> RateCard:
    card = session.scalar(select(RateCard).where(RateCard.organization_id == org_id)
                          .order_by(RateCard.valid_from.desc(), RateCard.id.desc()).limit(1))
    if card is None:
        raise DomainError(409, "RATE_CARD_MISSING", "No rate card is configured. Run the seed script.")
    return card


def card_by_code(session: Session, org_id: str, code: str) -> RateCard | None:
    return session.scalar(select(RateCard).where(RateCard.organization_id == org_id, RateCard.code == code))


def card_expired(card: RateCard) -> bool:
    now = utcnow()
    return not (card.valid_from <= now <= card.valid_to)


def default_inputs(case: Case, card: RateCard, scenario: str = "expected") -> dict:
    reqs = {r.key: r for r in case.requirements}

    def num(key: str) -> int | None:
        r = reqs.get(key)
        return int(r.value) if r and r.value and r.value.isdigit() else None

    return {
        "target_units": num("target_leads"),
        "unit_cost_idr": getattr(card, SCENARIOS[scenario][1]),
        "fixed_cost_idr": card.fixed_cost_idr,
        "proposed_fee_idr": num("budget"),
        "duration_weeks": num("timeline"),
    }


def assess(case: Case, card: RateCard, inputs: dict) -> dict:
    """Pure assessment: calculation + blockers (stop approval) + warnings (need attention)."""
    result = pricing.calculate(inputs)
    blockers: list[dict] = []
    warnings: list[dict] = []
    for r in case.requirements:
        if r.critical and r.state != "CONFIRMED":
            state = {"MISSING": "missing", "CONFLICTING": "conflicting", "DRAFT": "not yet confirmed"}.get(
                r.state, r.state.lower())
            blockers.append({"code": "REQUIREMENT_NOT_CONFIRMED", "field": r.key,
                             "message": f"{r.label} is {state}."})
    for issue in result.issues:
        blockers.append({"code": f"INPUT_{issue.code}", "field": issue.field, "message": issue.message})
    if card_expired(card):
        blockers.append({"code": "RATE_CARD_EXPIRED", "field": "rate_card",
                         "message": f"Rate card {card.code} is outside its validity window; reprice first."})
    reqs = {r.key: r for r in case.requirements}
    tl = reqs.get("target_leads")
    if result.valid and tl and tl.state == "CONFIRMED" and tl.value and int(tl.value) != inputs["target_units"]:
        blockers.append({"code": "TARGET_MISMATCH", "field": "target_units",
                         "message": f"Pricing target ({inputs['target_units']:,}) differs from the confirmed "
                                    f"requirement ({int(tl.value):,})."})
    capacity = None
    if result.valid:
        weekly = -(-inputs["target_units"] // inputs["duration_weeks"])
        capacity = {"required_per_week": weekly, "capacity_per_week": card.capacity_leads_per_week,
                    "utilization_pct": round(weekly * 100 / card.capacity_leads_per_week)}
        if weekly > card.capacity_leads_per_week:
            blockers.append({"code": "CAPACITY_EXCEEDED", "field": "target_units",
                             "message": f"Needs {weekly:,} qualified leads per week but delivery capacity is "
                                        f"{card.capacity_leads_per_week:,} per week. Extend the timeline or reduce "
                                        "the target."})
        if result.margin_bp is not None and result.margin_bp < card.margin_floor_bp:
            warnings.append({"code": "MARGIN_BELOW_FLOOR",
                             "message": f"Margin {format_margin(result.margin_bp)} is below the policy floor "
                                        f"{format_margin(card.margin_floor_bp)}; approval needs an exception note."})
        b = reqs.get("budget")
        if b and b.value and b.value.isdigit() and inputs["proposed_fee_idr"] > int(b.value):
            warnings.append({"code": "FEE_ABOVE_BUDGET",
                             "message": "Proposed fee is higher than the client's stated budget."})
    comparison = {}
    for key, (label, attr, desc) in SCENARIOS.items():
        alt = pricing.calculate({**inputs, "unit_cost_idr": getattr(card, attr)}) if result.valid else None
        comparison[key] = {"label": label, "description": desc, "unit_cost_idr": getattr(card, attr),
                           "total_cost_idr": alt.total_cost_idr if alt else None,
                           "margin_bp": alt.margin_bp if alt else None,
                           "margin_pct": format_margin(alt.margin_bp) if alt else None,
                           "below_floor": bool(alt and alt.margin_bp < card.margin_floor_bp)}
    return {"result": result.to_dict(), "blockers": blockers, "warnings": warnings, "capacity": capacity,
            "scenario_comparison": comparison}


def rate_card_dict(card: RateCard) -> dict:
    return {
        "code": card.code, "name": card.name, "synthetic": card.synthetic, "notes": card.notes,
        "unit_cost_idr": {"conservative": card.unit_cost_conservative_idr,
                          "expected": card.unit_cost_expected_idr,
                          "aggressive": card.unit_cost_aggressive_idr},
        "fixed_cost_idr": card.fixed_cost_idr, "margin_floor_bp": card.margin_floor_bp,
        "capacity_leads_per_week": card.capacity_leads_per_week, "expired": card_expired(card),
        "margin_floor_pct": format_margin(card.margin_floor_bp),
        "valid_from": card.valid_from.isoformat() + "Z", "valid_to": card.valid_to.isoformat() + "Z",
    }


def save_run(session: Session, actor: User, case: Case, scenario: str, inputs: dict,
             assumptions: list[str], based_on_run_id: int | None = None, check_base: bool = False) -> FeasibilityRun:
    from .packages import supersede_active  # local import avoids a cycle

    if scenario not in SCENARIOS:
        raise DomainError(422, "VALIDATION_ERROR", "Unknown scenario.", {"scenario": scenario})
    latest = latest_run(session, case)
    if check_base and (latest.id if latest else None) != based_on_run_id:
        raise DomainError(409, "VERSION_CONFLICT", "Someone saved a newer calculation for this case. Reload it before "
                          "saving yours.", {"expected_run": based_on_run_id, "current_run": latest.id if latest else None})
    card = current_rate_card(session, case.organization_id)
    a = assess(case, card, inputs)
    if not a["result"]["valid"]:
        raise DomainError(422, "PRICING_INVALID", "Fix the highlighted pricing inputs before saving.",
                          {"issues": a["result"]["issues"]})
    run = FeasibilityRun(case_id=case.id, rate_card_id=card.id, scenario=scenario, inputs=a["result"]["inputs"],
                         result=a["result"], valid=True, blockers=a["blockers"] + a["warnings"],
                         assumptions=[s.strip() for s in assumptions if s.strip()][:10], created_by=actor.id)
    session.add(run)
    session.flush()
    r = a["result"]
    audit.record(session, actor, "feasibility.calculated", "feasibility_run", run.id,
                 f"{SCENARIOS[scenario][0]} scenario on {card.code}: total cost Rp{r['total_cost_idr']:,}, "
                 f"margin {r['margin_pct']}; {len(a['blockers'])} blocker(s).", case.id)
    supersede_active(session, actor, case, "Pricing was recalculated after the package was frozen.",
                     new_pricing_inputs=run.inputs, new_scenario=scenario)
    return run


def latest_run(session: Session, case: Case) -> FeasibilityRun | None:
    return session.scalar(select(FeasibilityRun).where(FeasibilityRun.case_id == case.id)
                          .order_by(FeasibilityRun.id.desc()).limit(1))
