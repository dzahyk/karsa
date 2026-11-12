"""Case intake, requirement materialisation, and derived case status / next action."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..domain.catalog import CATALOG
from ..domain.extraction import ExtractionResult
from ..domain.hashing import text_hash
from ..models import (
    Case,
    DecisionPackage,
    ExecutionAuthorization,
    FeasibilityRun,
    Requirement,
    SourceDocument,
    User,
    WorkflowRun,
)
from . import audit
from .errors import DomainError, not_found

STATUS_LABELS = {
    "NEEDS_CLARIFICATION": "Needs clarification",
    "IN_ANALYSIS": "In analysis",
    "AWAITING_APPROVAL": "Awaiting approval",
    "CHANGES_REQUESTED": "Changes requested",
    "REJECTED": "Rejected",
    "APPROVED": "Approved — not yet authorized",
    "AUTHORIZED": "Authorized for execution",
    "EXECUTING": "Executing",
    "EXECUTION_ATTENTION": "Execution needs attention",
    "COMPLETED": "Completed — verified",
    "CANCELLED": "Execution cancelled — reopen to revise",
}
STATUS_GROUPS = {
    "needs_clarification": ("NEEDS_CLARIFICATION",),
    "awaiting_approval": ("AWAITING_APPROVAL",),
    "in_progress": ("IN_ANALYSIS", "CHANGES_REQUESTED", "APPROVED", "AUTHORIZED", "EXECUTING",
                    "EXECUTION_ATTENTION"),
    "closed": ("COMPLETED", "REJECTED", "CANCELLED"),
}


def get_case(session: Session, code: str, actor: User | None = None) -> Case:
    """Tenant-scoped lookup: a case from another organisation is reported as not found."""
    case = session.scalar(select(Case).where(Case.code == code))
    if case is None or (actor is not None and case.organization_id != actor.organization_id):
        raise not_found(f"Case {code}")
    return case


def next_code(session: Session) -> str:
    codes = session.scalars(select(Case.code)).all()
    nums = [int(c.split("-")[1]) for c in codes if c.startswith("DCF-")]
    return f"DCF-{(max(nums) + 1) if nums else 1042}"


def create_case(session: Session, actor: User, *, title: str, client_name: str, brief: str,
                owner: User, extraction: ExtractionResult, provider_label: str,
                due_at: datetime | None = None, code: str | None = None, artifact=None,
                page_breaks: list[int] | None = None) -> Case:
    now = utcnow()
    case = Case(
        organization_id=actor.organization_id,
        code=code or next_code(session), title=title.strip(), client_name=client_name.strip(),
        description=brief, owner_id=owner.id, status="NEEDS_CLARIFICATION", extractor=extraction.extractor,
        flags=[{"kind": f.kind, "message": f.message, "span": f.span.__dict__} for f in extraction.flags],
        action_hints=extraction.action_hints, due_at=due_at or now + timedelta(days=2),
        created_at=now, updated_at=now,
    )
    session.add(case)
    session.flush()
    title_doc = f"Client brief — {artifact.filename}" if artifact else "Client brief (original text)"
    doc = SourceDocument(case_id=case.id, kind="brief", title=title_doc, content=brief, sha256=text_hash(brief),
                         created_by=actor.id, verification="client_text", channel="document" if artifact else None,
                         page_breaks=page_breaks or [], artifact_id=artifact.id if artifact else None)
    session.add(doc)
    session.flush()
    for pos, d in enumerate(CATALOG):
        f = extraction.fields[d.key]
        session.add(Requirement(
            case_id=case.id, position=pos, key=d.key, label=d.label, value_type=d.value_type,
            critical=d.critical, state=f.state, value=f.value,
            source_document_id=doc.id if (f.span or f.candidates) else None,
            span_start=f.span.start if f.span else None, span_end=f.span.end if f.span else None,
            quote=f.span.quote if f.span else None, note=f.note,
            candidates=[{**c, "source_document_id": doc.id} for c in f.candidates],
            origin="extractor", extracted_value=f.value, updated_at=now,
        ))
    audit.record(session, actor, "case.created", "case", case.code,
                 f"Case {case.code} created for {case.client_name}.", case.id)
    found = sum(1 for f in extraction.fields.values() if f.state == "DRAFT")
    audit.record(session, None, "extraction.completed", "case", case.code,
                 f"{provider_label}: {found} of {len(CATALOG)} requirements drafted; "
                 f"{len(extraction.flags)} flag(s).", case.id,
                 {"extractor": extraction.extractor}, organization_id=case.organization_id)
    for f in extraction.flags:
        if f.kind == "prompt_injection":
            audit.record(session, None, "security.flagged", "case", case.code,
                         f"Instruction-like text in brief treated as data: “{f.span.quote}”.", case.id,
                         organization_id=case.organization_id)
    session.flush()
    refresh_status(session, case)
    return case


def latest_package(session: Session, case: Case) -> DecisionPackage | None:
    return session.scalar(select(DecisionPackage).where(DecisionPackage.case_id == case.id)
                          .order_by(DecisionPackage.version.desc()).limit(1))


def latest_run(session: Session, package: DecisionPackage) -> WorkflowRun | None:
    return session.scalar(select(WorkflowRun).where(WorkflowRun.package_id == package.id)
                          .order_by(WorkflowRun.id.desc()).limit(1))


def _requirement_action(reqs: list[Requirement]) -> str | None:
    for r in reqs:
        if not r.critical or r.state == "CONFIRMED":
            continue
        label = r.label[0].lower() + r.label[1:]
        return {"MISSING": f"Define {label}", "CONFLICTING": f"Resolve conflicting {label}",
                "DRAFT": f"Confirm {label}"}.get(r.state, f"Review {label}")
    return None


def refresh_status(session: Session, case: Case) -> None:
    session.flush()
    session.refresh(case, ["requirements"])
    pkg = latest_package(session, case)
    status, action = None, None
    if pkg and pkg.state == "APPROVED":
        run = latest_run(session, pkg)
        if run:
            status, action = {
                "SUCCEEDED": ("COMPLETED", "None — outcome verified"),
                "RUNNING": ("EXECUTING", "Wait for sandbox workflow"),
                "QUEUED": ("EXECUTING", "Wait for sandbox workflow"),
                "CANCELLED": ("CANCELLED", "Reopen the case to revise"),
            }.get(run.status, ("EXECUTION_ATTENTION", f"Resolve run {run.code}"))
        elif session.scalar(select(ExecutionAuthorization).where(ExecutionAuthorization.package_id == pkg.id)):
            status, action = "AUTHORIZED", "Run sandbox workflow"
        else:
            status, action = "APPROVED", "Authorize execution"
    elif pkg and pkg.state == "IN_REVIEW":
        status, action = "AWAITING_APPROVAL", f"Review package v{pkg.version}"
    elif pkg and pkg.state == "REJECTED":
        status, action = "REJECTED", "Closed — reopen to revise and resubmit"
    elif pkg and pkg.state == "CHANGES_REQUESTED":
        status, action = "CHANGES_REQUESTED", "Address reviewer comments"
    if status is None:
        req_action = _requirement_action(case.requirements)
        if req_action:
            status, action = "NEEDS_CLARIFICATION", req_action
        elif not session.scalar(select(FeasibilityRun.id).where(FeasibilityRun.case_id == case.id).limit(1)):
            status, action = "IN_ANALYSIS", "Run feasibility & pricing"
        else:
            status, action = "IN_ANALYSIS", "Create decision package"
    if case.status != status or case.next_action != action:
        case.status, case.next_action = status, action
    case.updated_at = utcnow()


def lock_reason(session: Session, case: Case) -> str | None:
    """Why requirements/pricing cannot change right now (None = editable)."""
    pkg = latest_package(session, case)
    if pkg is None:
        return None
    if pkg.state == "REJECTED":
        return f"Package v{pkg.version} was rejected. Reopen the case to revise and resubmit."
    run = latest_run(session, pkg)
    if run is not None:
        if run.status == "CANCELLED":
            return f"Run {run.code} was cancelled. Reopen the case to revise."
        return f"Execution run {run.code} exists for this case; requirements and pricing are locked."
    return None


def reopen(session: Session, actor: User, case: Case, reason: str) -> Case:
    """REOPENED: supersede the rejected/cancelled package so the case can be revised (spec §2.5 branches)."""
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise DomainError(422, "REASON_REQUIRED", "Explain why the case is reopened.", {"field": "reason"})
    pkg = latest_package(session, case)
    run = latest_run(session, pkg) if pkg else None
    if pkg is None or not (pkg.state == "REJECTED" or (run is not None and run.status == "CANCELLED")):
        raise DomainError(409, "NOT_REOPENABLE", "Only rejected cases or cases with a cancelled run can be reopened.")
    pkg.state = "SUPERSEDED"
    pkg.superseded_reason = f"Case reopened: {reason}"
    case.reopen_count += 1
    audit.record(session, actor, "case.reopened", "case", case.code,
                 f"{actor.name} reopened {case.code}: {reason}", case.id)
    refresh_status(session, case)
    return case


def list_cases(session: Session, actor: User, group: str | None, q: str | None, limit: int = 25,
               offset: int = 0) -> tuple[list[Case], dict[str, int], int]:
    stmt = select(Case).where(Case.organization_id == actor.organization_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Case.code.ilike(like), Case.title.ilike(like), Case.client_name.ilike(like)))
    base = sorted(session.scalars(stmt).all(), key=lambda c: (
        c.status in STATUS_GROUPS["closed"], c.due_at or datetime.max, c.code))  # most urgent open work first
    counts = {"all": len(base)} | {g: sum(1 for c in base if c.status in s) for g, s in STATUS_GROUPS.items()}
    if group and group in STATUS_GROUPS:
        base = [c for c in base if c.status in STATUS_GROUPS[group]]
    return list(base)[offset: offset + limit], counts, len(base)


def count_cases(session: Session) -> int:
    return session.scalar(select(func.count(Case.id))) or 0
