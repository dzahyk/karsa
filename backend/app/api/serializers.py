from __future__ import annotations

from datetime import datetime

from ..domain.permissions import PERMISSIONS, ROLES, modules
from ..models import (
    ApprovalRecord,
    AuditEvent,
    Case,
    Clarification,
    DecisionPackage,
    ExecutionAuthorization,
    FeasibilityRun,
    Incident,
    Notification,
    Requirement,
    RequirementChange,
    SourceDocument,
    User,
    WorkflowRun,
)
from ..services.cases import STATUS_LABELS


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def user(u: User | None) -> dict | None:
    if u is None:
        return None
    initials = "".join(p[0] for p in u.name.split()[:2]).upper()
    return {"id": u.id, "name": u.name, "role": u.role, "role_label": ROLES.get(u.role, u.role), "title": u.title,
            "initials": initials, "permissions": sorted(PERMISSIONS.get(u.role, set())), "modules": modules(u.role),
            "username": u.username, "organization_id": u.organization_id}


def case_summary(c: Case) -> dict:
    return {"code": c.code, "title": c.title, "client_name": c.client_name, "status": c.status,
            "status_label": STATUS_LABELS.get(c.status, c.status), "next_action": c.next_action,
            "owner": user(c.owner), "due_at": iso(c.due_at), "created_at": iso(c.created_at),
            "updated_at": iso(c.updated_at), "synthetic": c.synthetic,
            "flags": len(c.flags)}


def requirement(r: Requirement) -> dict:
    over = r.origin == "analyst" and r.quote is not None and r.value != r.extracted_value
    return {"key": r.key, "label": r.label, "value_type": r.value_type, "critical": r.critical, "state": r.state,
            "value": r.value, "origin": r.origin, "note": r.note, "candidates": r.candidates, "version": r.version,
            "overridden": over, "source_value": r.extracted_value if over else None,
            "source": ({"document_id": r.source_document_id, "start": r.span_start, "end": r.span_end,
                        "quote": r.quote} if r.source_document_id and r.quote is not None else None),
            "updated_at": iso(r.updated_at)}


def document(d: SourceDocument) -> dict:
    return {"id": d.id, "kind": d.kind, "title": d.title, "content": d.content, "sha256": d.sha256,
            "verification": d.verification, "channel": d.channel, "reference": d.reference,
            "page_breaks": d.page_breaks or [], "artifact_id": d.artifact_id, "created_at": iso(d.created_at)}


def clarification(c: Clarification, users: dict[str, User]) -> dict:
    return {"id": c.id, "requirement_key": c.requirement_key, "question": c.question, "status": c.status,
            "answer": c.answer, "answered_source": c.answered_source, "applied": c.applied,
            "channel": c.channel, "reference": c.reference,
            "source_document_id": c.source_document_id, "asked_by": user(users.get(c.asked_by)),
            "answered_by": user(users.get(c.answered_by)) if c.answered_by else None,
            "created_at": iso(c.created_at), "answered_at": iso(c.answered_at)}


def change(ch: RequirementChange, users: dict[str, User]) -> dict:
    return {"id": ch.id, "action": ch.action, "from_state": ch.from_state, "to_state": ch.to_state,
            "from_value": ch.from_value, "to_value": ch.to_value, "reason": ch.reason,
            "actor": user(users.get(ch.actor_id)), "at": iso(ch.at)}


def feasibility_run(r: FeasibilityRun | None, users: dict[str, User]) -> dict | None:
    if r is None:
        return None
    return {"id": r.id, "scenario": r.scenario, "inputs": r.inputs, "result": r.result, "blockers": r.blockers,
            "assumptions": r.assumptions, "rate_card": r.rate_card.code, "created_by": user(users.get(r.created_by)),
            "created_at": iso(r.created_at)}


def approval(a: ApprovalRecord, users: dict[str, User]) -> dict:
    return {"id": a.id, "decision": a.decision, "note": a.note, "package_hash": a.package_hash,
            "package_version": a.package_version, "actor": user(users.get(a.actor_id)), "created_at": iso(a.created_at)}


def authorization(a: ExecutionAuthorization | None, users: dict[str, User]) -> dict | None:
    if a is None:
        return None
    return {"id": a.id, "actions": a.actions, "note": a.note, "package_hash": a.package_hash,
            "actor": user(users.get(a.actor_id)), "created_at": iso(a.created_at)}


def package_summary(p: DecisionPackage, users: dict[str, User]) -> dict:
    pr = p.content["pricing"]
    return {"id": p.id, "version": p.version, "state": p.state, "risk_level": p.risk_level,
            "required_approvals": p.required_approvals, "content_hash": p.content_hash, "created_by": user(users.get(p.created_by)),
            "created_at": iso(p.created_at), "superseded_reason": p.superseded_reason,
            "case": {"code": p.case.code, "title": p.case.title, "client_name": p.case.client_name},
            "fee_idr": pr["inputs"]["proposed_fee_idr"], "margin_pct": pr["margin_pct"],
            "duration_weeks": pr["inputs"]["duration_weeks"]}


def run_summary(r: WorkflowRun, users: dict[str, User]) -> dict:
    return {"code": r.code, "status": r.status, "simulate": r.simulate, "package_id": r.package_id,
            "cancelled_reason": r.cancelled_reason,
            "package_hash": r.package_hash, "started_by": user(users.get(r.started_by)),
            "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
            "steps_done": sum(1 for s in r.steps if s.status == "SUCCEEDED"), "steps_total": len(r.steps)}


def run_detail(r: WorkflowRun, users: dict[str, User]) -> dict:
    d = run_summary(r, users)
    d["steps"] = [{
        "key": s.key, "label": s.label, "target": s.target, "status": s.status, "attempts": s.attempts,
        "max_attempts": s.max_attempts, "idempotency_key": s.idempotency_key, "external_ref": s.external_ref,
        "last_error": s.last_error, "started_at": iso(s.started_at), "finished_at": iso(s.finished_at),
        "can_retry": s.status == "FAILED" and s.attempts < s.max_attempts and s.idempotency_key is not None,
        "can_reconcile": s.status == "UNKNOWN_OUTCOME",
        "can_resolve": s.status in ("FAILED", "UNKNOWN_OUTCOME"),
        "attempt_log": [{"number": a.number, "kind": a.kind, "outcome": a.outcome, "detail": a.detail,
                         "actor": user(users.get(a.actor_id)), "at": iso(a.finished_at)} for a in s.attempt_log],
    } for s in r.steps]
    return d


def audit_event(e: AuditEvent, users: dict[str, User]) -> dict:
    return {"id": e.id, "verb": e.verb, "summary": e.summary, "entity_type": e.entity_type, "entity_id": e.entity_id,
            "actor": user(users.get(e.actor_id)) if e.actor_id else None, "actor_role": e.actor_role,
            "detail": e.detail, "at": iso(e.at)}


def incident(i: Incident, users: dict[str, User], run_code: str | None = None, case_code: str | None = None) -> dict:
    return {"id": i.id, "status": i.status, "title": i.title, "detail": i.detail, "compensation": i.compensation,
            "step_key": i.step_key, "run_code": run_code, "case_code": case_code,
            "opened_by": user(users.get(i.opened_by)) if i.opened_by else None,
            "resolved_by": user(users.get(i.resolved_by)) if i.resolved_by else None, "resolution": i.resolution,
            "created_at": iso(i.created_at), "resolved_at": iso(i.resolved_at)}


def notification(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "read": n.read_at is not None,
            "created_at": iso(n.created_at)}
