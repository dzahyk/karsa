"""Transformation impact metrics computed from the synthetic cohort plus live counts from this database."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ApprovalRecord, Case, DecisionPackage, ImpactCohortCase, RequirementChange, User, WorkflowRun

MIN_SAMPLE = 20
PERIODS = {
    "baseline": {"label": "Baseline — manual process", "start": "2026-05-01", "end": "2026-07-31"},
    "assisted": {"label": "Assisted workflow available", "start": "2026-08-01", "end": "2026-10-31"},
}


def _days(c: ImpactCohortCase) -> float | None:
    if c.decided_at is None:
        return None
    return round((c.decided_at - c.created_at).total_seconds() / 86400, 2)


def summary(session: Session) -> dict:
    rows = list(session.scalars(select(ImpactCohortCase)))
    if not rows:
        return {"available": False}
    monthly: dict[tuple[str, str], list[float]] = defaultdict(list)
    for c in rows:
        d = _days(c)
        if d is None:
            continue
        series = "baseline_manual" if c.period == "baseline" else f"assisted_{c.flow}"
        monthly[(series, c.created_at.strftime("%Y-%m"))].append(d)
    months = sorted({m for _, m in monthly})
    series = {}
    for name in ("baseline_manual", "assisted_assisted", "assisted_manual"):
        pts = []
        for m in months:
            vals = monthly.get((name, m))
            if vals:
                pts.append({"month": m, "median_days": round(median(vals), 1), "n": len(vals),
                            "insufficient_sample": len(vals) < MIN_SAMPLE})
        series[name] = pts

    def med(sel):
        vals = [d for c in rows if sel(c) and (d := _days(c)) is not None]
        return {"median_days": round(median(vals), 1) if vals else None, "n": len(vals)}

    assisted_period = [c for c in rows if c.period == "assisted"]
    flow = [c for c in assisted_period if c.flow == "assisted"]
    reviewed = [c for c in flow if c.reviewed]
    approved = [c for c in flow if c.approved]
    verified = [c for c in flow if c.verified]
    overrides = [c for c in reviewed if c.overridden]
    wf = Counter(c.workflow_status for c in approved if c.workflow_status)
    by_month_users: dict[str, dict[str, set]] = defaultdict(lambda: {"eligible": set(), "adopted": set()})
    for c in assisted_period:
        m = c.created_at.strftime("%Y-%m")
        by_month_users[m]["eligible"].add(c.handler_id)
        if c.flow == "assisted":
            by_month_users[m]["adopted"].add(c.handler_id)
    user_adoption = [{"month": m, "eligible_users": len(v["eligible"]), "adopted_users": len(v["adopted"]),
                      "rate": round(len(v["adopted"]) / len(v["eligible"]), 4) if v["eligible"] else None}
                     for m, v in sorted(by_month_users.items())]
    all_users = {c.handler_id for c in assisted_period}
    adopted_users = {c.handler_id for c in flow}
    return {
        "available": True,
        "synthetic": True,
        "user_adoption": {
            "definition": "Adoption by people: eligible analysts who handled at least one case in the assisted flow "
                          "during the period ÷ eligible analysts who handled any case.",
            "eligible_users": len(all_users), "adopted_users": len(adopted_users),
            "rate": round(len(adopted_users) / len(all_users), 4) if all_users else None,
            "monthly": user_adoption,
        },
        "generator": "seed.py · fixed seed 20261111 · see docs/ARCHITECTURE.md",
        "periods": PERIODS,
        "data_through": "2026-10-31",
        "cycle_time": {
            "definition": "Calendar days from case intake to final decision (approve or reject). Median per month.",
            "series": series,
            "baseline_manual": med(lambda c: c.period == "baseline"),
            "assisted_flow": med(lambda c: c.period == "assisted" and c.flow == "assisted"),
            "concurrent_manual": med(lambda c: c.period == "assisted" and c.flow == "manual"),
            "min_sample": MIN_SAMPLE,
        },
        "funnel": {
            "definition": "Assisted period. Eligible = campaign cases created in the period; adopted = handled in "
                          "the assisted flow; verified = workflow outcome read back from the sandbox.",
            "steps": [
                {"key": "eligible", "label": "Eligible cases", "n": len(assisted_period)},
                {"key": "adopted", "label": "Handled in assisted flow", "n": len(flow)},
                {"key": "reviewed", "label": "Reviewed by a human", "n": len(reviewed)},
                {"key": "approved", "label": "Approved", "n": len(approved)},
                {"key": "verified", "label": "Verified outcome", "n": len(verified)},
            ],
        },
        "adoption_rate": round(len(flow) / len(assisted_period), 4) if assisted_period else None,
        "adoption_rate_definition": "Case share: cases handled in the assisted flow ÷ eligible cases.",
        "override": {
            "definition": "Share of human-reviewed assisted cases where the reviewer changed an AI-drafted value "
                          "or the recommendation. Not treated as good or bad by itself.",
            "n": len(overrides), "of": len(reviewed),
            "rate": round(len(overrides) / len(reviewed), 4) if reviewed else None,
            "reasons": Counter(c.override_reason for c in overrides).most_common(),
        },
        "workflow_status": {"definition": "Final state of sandbox workflows for approved assisted cases.",
                            "counts": dict(wf)},
        "caveats": [
            "Synthetic demonstration data: no real organisation, client or employee is represented.",
            "Association does not prove causation. Case mix, seasonality, policy changes and team experience "
            "also change cycle time; the concurrent manual cases are shown as a partial control.",
            f"Months with fewer than {MIN_SAMPLE} decided cases are marked as insufficient sample.",
            "No ROI or cost saving is claimed. Capacity estimates would need a controlled pilot.",
        ],
    }


def live(session: Session, org_id: str) -> dict:
    """Metrics computed from the real demo cases in this database (same definitions, tiny sample)."""
    org_cases = select(Case.id).where(Case.organization_id == org_id)
    by_status = dict(session.execute(select(Case.status, func.count()).where(Case.organization_id == org_id)
                                     .group_by(Case.status)).all())
    runs = dict(session.execute(select(WorkflowRun.status, func.count()).where(WorkflowRun.case_id.in_(org_cases))
                                .group_by(WorkflowRun.status)).all())
    overrides = session.scalar(select(func.count()).select_from(RequirementChange).where(
        RequirementChange.action == "edit", RequirementChange.case_id.in_(org_cases))) or 0
    reviewed = session.scalar(select(func.count(func.distinct(RequirementChange.case_id))).where(
        RequirementChange.case_id.in_(org_cases))) or 0
    cycle = []
    for c in session.scalars(select(Case).where(Case.organization_id == org_id)):
        first = session.scalar(select(func.min(ApprovalRecord.created_at)).join(
            DecisionPackage, DecisionPackage.id == ApprovalRecord.package_id).where(
            DecisionPackage.case_id == c.id, ApprovalRecord.decision.in_(("APPROVE", "REJECT"))))
        if first:
            cycle.append((first - c.created_at).total_seconds() / 86400)
    analysts = {u.id for u in session.scalars(select(User).where(User.organization_id == org_id,
                                                                 User.role == "ANALYST"))}
    active = {a for (a,) in session.execute(select(RequirementChange.actor_id).where(
        RequirementChange.case_id.in_(org_cases)).distinct())} & analysts
    return {"cases_by_status": by_status, "runs_by_status": runs, "analyst_value_overrides": overrides,
            "cases": sum(by_status.values()), "cases_with_human_review": reviewed,
            "cycle_time": {"median_days": round(median(cycle), 2) if cycle else None, "n": len(cycle),
                           "insufficient_sample": len(cycle) < MIN_SAMPLE},
            "user_adoption": {"active_analysts": len(active), "analysts": len(analysts)}}
