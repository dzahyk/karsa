"""Controlled sandbox execution of an approved, authorized decision package (spec §3.7, §4.9).

Starting, retrying or reconciling only *enqueues* work in the outbox, in the same transaction as the state change.
The worker (app/worker.py) claims outbox events with a lease and advances the run. Steps are idempotent, so a
duplicate delivery or a re-claimed event after a crash never creates a second external record.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..domain.hashing import content_hash
from ..models import (
    ApprovalRecord,
    DecisionPackage,
    ExecutionAuthorization,
    Incident,
    OutboxEvent,
    StepAttempt,
    User,
    WorkflowRun,
    WorkflowStep,
)
from ..sandbox import connectors as sandbox
from . import approvals, audit, cases, connectors, notifications
from .authz import require
from .errors import DomainError
from .packages import ACTION_CATALOG

WRITE_PREFIXES = ("crm.", "tracker.")
TERMINAL = ("SUCCEEDED", "CANCELLED")


def get_run(session: Session, code: str, actor: User | None = None) -> WorkflowRun:
    run = session.scalar(select(WorkflowRun).where(WorkflowRun.code == code))
    if run is None or (actor is not None and session.get(DecisionPackage, run.package_id).case.organization_id
                       != actor.organization_id):
        raise DomainError(404, "NOT_FOUND", f"Run {code} was not found.")
    return run


def gate(session: Session, pkg: DecisionPackage) -> tuple[ApprovalRecord, ExecutionAuthorization]:
    """Execution gate (BR-003, BR-012, BR-013, AC-04): approved + authorized + current + hash intact. Fails closed."""
    if pkg.state != "APPROVED":
        raise DomainError(409, "NOT_APPROVED", f"Package v{pkg.version} is {pkg.state.lower()}; only an approved, "
                                               "current package can be executed.")
    latest = cases.latest_package(session, pkg.case)
    if latest is None or latest.id != pkg.id:
        raise DomainError(409, "PACKAGE_NOT_CURRENT", "A newer package version exists.")
    approval = session.scalar(select(ApprovalRecord).where(ApprovalRecord.package_id == pkg.id,
                                                           ApprovalRecord.decision == "APPROVE"))
    auth = session.scalar(select(ExecutionAuthorization).where(ExecutionAuthorization.package_id == pkg.id))
    if approval is None:
        raise DomainError(409, "NOT_APPROVED", "No approval record exists for this package.")
    if auth is None:
        raise DomainError(403, "EXECUTION_NOT_AUTHORIZED",
                          "Decision approval does not authorize execution. An approver must authorize it first.")
    actual = content_hash(pkg.content)
    if not (actual == pkg.content_hash == approval.package_hash == auth.package_hash):
        raise DomainError(409, "HASH_MISMATCH", "Package content no longer matches the approved snapshot.")
    approvals.assert_rate_card_valid(session, pkg)
    connectors.assert_enabled(session, pkg.case.organization_id, auth.actions)
    return approval, auth


def _new_code(session: Session) -> str:
    n = session.scalar(select(WorkflowRun.id).order_by(WorkflowRun.id.desc()).limit(1)) or 0
    return f"EX-{n + 81:04d}"


def enqueue(session: Session, run: WorkflowRun, actor: User) -> None:
    pkg = session.get(DecisionPackage, run.package_id)
    run.status = "QUEUED"
    session.add(OutboxEvent(organization_id=pkg.case.organization_id, kind="run.advance", run_id=run.id,
                            actor_id=actor.id))


def start(session: Session, actor: User, pkg: DecisionPackage, simulate: str) -> WorkflowRun:
    require(session, actor, "workflow.run", pkg.case_id, f"package v{pkg.version}")
    if simulate not in sandbox.SIMULATIONS:
        raise DomainError(422, "VALIDATION_ERROR", "Unknown simulation mode.", {"field": "simulate"})
    _, auth = gate(session, pkg)
    if session.scalar(select(WorkflowRun).where(WorkflowRun.package_id == pkg.id)):
        raise DomainError(409, "RUN_EXISTS", "This package already has a run. Recover that run instead of starting "
                                             "another one.")
    run = WorkflowRun(code=_new_code(session), case_id=pkg.case_id, package_id=pkg.id,
                      package_hash=pkg.content_hash, status="QUEUED", simulate=simulate, started_by=actor.id)
    session.add(run)
    session.flush()
    steps = [("verify_snapshot", "Verify approved snapshot", "Karsa", 1)]
    steps += [(a, ACTION_CATALOG[a][0], ACTION_CATALOG[a][1], 3) for a in auth.actions]
    steps += [("verify_receipts", "Read-back verification", "Sandbox connectors", 2)]
    for pos, (key, label, target, max_attempts) in enumerate(steps):
        session.add(WorkflowStep(
            run_id=run.id, position=pos, key=key, label=label, target=target, status="PENDING",
            max_attempts=max_attempts,
            idempotency_key=f"pkg{pkg.id}-{pkg.content_hash[7:19]}:{key}" if key.startswith(WRITE_PREFIXES) else None,
        ))
    session.flush()
    session.refresh(run, ["steps"])
    audit.record(session, actor, "workflow.queued", "run", run.code,
                 f"Sandbox run {run.code} queued for package v{pkg.version}"
                 + (f" (simulation: {sandbox.SIMULATIONS[simulate]})." if simulate != "none" else "."),
                 pkg.case_id, {"simulate": simulate})
    enqueue(session, run, actor)
    cases.refresh_status(session, pkg.case)
    return run


def _attempt(session: Session, actor: User, step: WorkflowStep, outcome: str, detail: str, kind="attempt"):
    now = utcnow()
    session.add(StepAttempt(step_id=step.id, number=step.attempts, kind=kind, outcome=outcome, detail=detail,
                            actor_id=actor.id, started_at=step.started_at or now, finished_at=now))


def _manual(step: WorkflowStep) -> bool:
    return bool(step.attempt_log) and step.attempt_log[-1].kind == "manual"


def _run_step(session: Session, actor: User, run: WorkflowRun, step: WorkflowStep, pkg: DecisionPackage) -> str:
    step.status, step.started_at = "RUNNING", step.started_at or utcnow()
    step.attempts += 1
    if step.key == "verify_snapshot":
        ok = content_hash(pkg.content) == run.package_hash == pkg.content_hash
        outcome = "SUCCEEDED" if ok else "FAILED"
        detail = (f"Recomputed SHA-256 matches the approved hash {run.package_hash[:19]}…" if ok
                  else "Recomputed hash does not match the approved snapshot. Execution stopped (fail closed).")
    elif step.key == "verify_receipts":
        writes = [s for s in run.steps if s.idempotency_key]
        manual = [s for s in writes if _manual(s)]
        auto = [s for s in writes if not _manual(s)]
        found = [sandbox.read_back(session, s.idempotency_key) for s in auto]
        ok = all(r is not None and r.payload.get("package_hash") == run.package_hash for r in found)
        outcome = "SUCCEEDED" if ok else "FAILED"
        detail = (f"{len(found)} of {len(writes)} sandbox records read back and matched the approved hash"
                  + (f"; {len(manual)} confirmed manually by an operator." if manual else ".") if ok
                  else "Read-back did not find every record with the approved hash.")
    else:
        enabled = {a for c in connectors.for_org(session, pkg.case.organization_id) if c.enabled for a in c.actions}
        if step.key not in enabled:
            outcome, detail = "FAILED", "Connector disabled by an admin before this step ran. Nothing was sent."
        else:
            p = pkg.content["pricing"]
            payload = {"package_hash": run.package_hash, "case": pkg.content["case"]["code"],
                       "client": pkg.content["case"]["client"], "fee_idr": p["inputs"]["proposed_fee_idr"],
                       "target_leads": p["inputs"]["target_units"], "duration_weeks": p["inputs"]["duration_weeks"],
                       "run": run.code}
            res = sandbox.write(session, step.key, step.idempotency_key, payload, run.simulate, step.attempts)
            outcome, detail = res.outcome, res.detail
            if res.record:
                step.external_ref = res.record.external_ref
    step.status = outcome
    step.last_error = None if outcome == "SUCCEEDED" else detail
    step.finished_at = utcnow()
    _attempt(session, actor, step, outcome, detail)
    audit.record(session, actor, f"workflow.step.{outcome.lower()}", "run", run.code,
                 f"{step.label} — attempt {step.attempts}: {detail}", run.case_id,
                 {"step": step.key, "attempt": step.attempts})
    return outcome


def _open_incident(session: Session, actor: User | None, run: WorkflowRun, step: WorkflowStep | None, title: str,
                   detail: str) -> Incident:
    inc = session.scalar(select(Incident).where(Incident.run_id == run.id, Incident.status == "OPEN"))
    pkg = session.get(DecisionPackage, run.package_id)
    if inc is None:
        inc = Incident(organization_id=pkg.case.organization_id, case_id=run.case_id, run_id=run.id,
                       step_key=step.key if step else None, title=title, detail=detail,
                       opened_by=actor.id if actor else None)
        session.add(inc)
        session.flush()
        audit.record(session, actor, "incident.opened", "incident", inc.id, f"Incident #{inc.id}: {title}",
                     run.case_id, organization_id=pkg.case.organization_id)
        notifications.notify_roles(session, pkg.case.organization_id, ("AUTOMATION_ENGINEER",), "incident.opened",
                                   f"Exception: {run.code}", title, f"/workflows/{run.code}")
    return inc


def _finish(session: Session, actor: User, run: WorkflowRun) -> None:
    statuses = [s.status for s in run.steps]
    wrote = any(s.status == "SUCCEEDED" and s.idempotency_key for s in run.steps)
    if all(s == "SUCCEEDED" for s in statuses):
        run.status = "SUCCEEDED"
    elif "UNKNOWN_OUTCOME" in statuses:
        run.status = "UNKNOWN_OUTCOME"
    elif "FAILED" in statuses:
        run.status = "PARTIAL" if wrote else "FAILED"
    pkg = session.get(DecisionPackage, run.package_id)
    if run.status not in ("RUNNING", "QUEUED"):
        run.finished_at = utcnow()
        label = {"SUCCEEDED": "verified", "UNKNOWN_OUTCOME": "stopped — outcome unknown, reconciliation required",
                 "PARTIAL": "stopped — partially completed", "FAILED": "failed"}[run.status]
        audit.record(session, actor, f"workflow.{run.status.lower()}", "run", run.code, f"Run {run.code} {label}.",
                     run.case_id)
        owner = pkg.case.owner_id
        notifications.notify_users(session, pkg.case.organization_id, {owner}, f"run.{run.status.lower()}",
                                   f"Run {run.code} {label}", f"{pkg.case.client_name} — {pkg.case.title}",
                                   f"/workflows/{run.code}")
        stuck = [s for s in run.steps if s.status == "FAILED" and s.attempts >= s.max_attempts]
        if stuck:
            _open_incident(session, None, run, stuck[0], f"{stuck[0].label} failed after {stuck[0].attempts} "
                           "attempt(s)", f"{stuck[0].last_error} Manual recovery is required.")
    cases.refresh_status(session, pkg.case)


def advance(session: Session, actor: User, run: WorkflowRun) -> None:
    """Run every pending step in order until one does not succeed. Safe to call more than once."""
    if run.status in TERMINAL:
        return
    pkg = session.get(DecisionPackage, run.package_id)
    run.status = "RUNNING"
    for step in run.steps:
        if step.status == "SUCCEEDED":
            continue
        if step.status in ("PENDING", "BLOCKED"):
            outcome = _run_step(session, actor, run, step, pkg)
            if outcome != "SUCCEEDED":
                for later in run.steps:
                    if later.position > step.position and later.status == "PENDING":
                        later.status = "BLOCKED"
                        later.last_error = f"Waiting on step {step.position + 1}: {step.label}."
                break
        else:
            break
    _finish(session, actor, run)


def _step(run: WorkflowRun, key: str) -> WorkflowStep:
    for s in run.steps:
        if s.key == key:
            return s
    raise DomainError(404, "NOT_FOUND", f"Step '{key}' was not found.")


def _unblock_after(run: WorkflowRun, step: WorkflowStep) -> None:
    for later in run.steps:
        if later.position > step.position and later.status == "BLOCKED":
            later.status, later.last_error = "PENDING", None


def _not_terminal(run: WorkflowRun) -> None:
    if run.status in TERMINAL:
        raise DomainError(409, "RUN_CLOSED", f"Run {run.code} is {run.status.lower()}.")
    if run.status in ("QUEUED", "RUNNING"):
        raise DomainError(409, "RUN_BUSY", f"Run {run.code} is {run.status.lower()}; wait for it to stop.")


def retry(session: Session, actor: User, run: WorkflowRun, key: str) -> WorkflowRun:
    require(session, actor, "workflow.recover", run.case_id, f"run {run.code}")
    _not_terminal(run)
    step = _step(run, key)
    if step.status == "UNKNOWN_OUTCOME":
        raise DomainError(409, "BLIND_RETRY_BLOCKED", "The outcome of the last attempt is unknown. Check the target "
                                                      "system (reconcile) before any retry.")
    if step.status != "FAILED":
        raise DomainError(409, "NOT_RETRYABLE", f"Step is {step.status.lower()}; only failed steps can be retried.")
    if step.attempts >= step.max_attempts:
        raise DomainError(409, "ATTEMPTS_EXHAUSTED", f"All {step.max_attempts} attempts used. Resolve it manually or "
                                                     "cancel the run from the incident.")
    pkg = session.get(DecisionPackage, run.package_id)
    gate(session, pkg)
    audit.record(session, actor, "workflow.retry", "run", run.code,
                 f"{actor.name} queued a retry of “{step.label}” (attempt {step.attempts + 1} of {step.max_attempts})"
                 " with the same idempotency key.", run.case_id)
    step.status = "PENDING"
    _unblock_after(run, step)
    enqueue(session, run, actor)
    cases.refresh_status(session, pkg.case)
    return run


def reconcile(session: Session, actor: User, run: WorkflowRun, key: str) -> WorkflowRun:
    require(session, actor, "workflow.recover", run.case_id, f"run {run.code}")
    _not_terminal(run)
    step = _step(run, key)
    if step.status != "UNKNOWN_OUTCOME":
        raise DomainError(409, "NOT_UNKNOWN", "Reconciliation is only needed when the outcome is unknown.")
    pkg = session.get(DecisionPackage, run.package_id)
    rec = sandbox.read_back(session, step.idempotency_key)
    if rec:
        step.status, step.external_ref = "SUCCEEDED", rec.external_ref
        step.last_error, step.finished_at = None, utcnow()
        detail = f"Reconciled: {rec.external_ref} exists in the sandbox with the approved hash. No second write sent."
        _attempt(session, actor, step, "RECONCILED_FOUND", detail, "reconcile")
        audit.record(session, actor, "workflow.reconciled", "run", run.code, f"{step.label}: {detail}", run.case_id)
        _unblock_after(run, step)
        gate(session, pkg)
        enqueue(session, run, actor)
    else:
        step.status = "FAILED"
        step.last_error = "Reconciled: no record found in the target. Safe to retry with the same key."
        _attempt(session, actor, step, "RECONCILED_NOT_FOUND", step.last_error, "reconcile")
        audit.record(session, actor, "workflow.reconciled", "run", run.code, f"{step.label}: {step.last_error}",
                     run.case_id)
        _finish(session, actor, run)
    cases.refresh_status(session, pkg.case)
    return run


def resolve_manually(session: Session, actor: User, run: WorkflowRun, key: str, external_ref: str,
                     note: str) -> WorkflowRun:
    """Operator repair: the operator confirms the effect exists (e.g. created by hand) and records the reference."""
    require(session, actor, "incident.manage", run.case_id, f"run {run.code}")
    _not_terminal(run)
    step = _step(run, key)
    if step.status not in ("FAILED", "UNKNOWN_OUTCOME"):
        raise DomainError(409, "NOT_RESOLVABLE", "Only failed or unknown steps can be resolved manually.")
    note, ref = (note or "").strip(), (external_ref or "").strip()
    if len(note) < 10:
        raise DomainError(422, "REASON_REQUIRED", "Describe what you checked or did (10+ characters).", {"field": "note"})
    if step.idempotency_key and len(ref) < 3:
        raise DomainError(422, "VALIDATION_ERROR", "Enter the external reference you verified in the target system.",
                          {"field": "external_ref"})
    step.status, step.external_ref = "SUCCEEDED", ref or step.external_ref
    step.last_error, step.finished_at = None, utcnow()
    _attempt(session, actor, step, "RESOLVED_MANUALLY", f"{actor.name}: {note}" + (f" (ref {ref})" if ref else ""),
             "manual")
    audit.record(session, actor, "workflow.resolved_manually", "run", run.code,
                 f"{step.label} resolved manually by {actor.name}: {note}", run.case_id, {"external_ref": ref})
    _unblock_after(run, step)
    pkg = session.get(DecisionPackage, run.package_id)
    enqueue(session, run, actor)
    cases.refresh_status(session, pkg.case)
    return run


def escalate(session: Session, actor: User, run: WorkflowRun, note: str) -> Incident:
    require(session, actor, "workflow.recover", run.case_id, f"run {run.code}")
    if run.status in TERMINAL:
        raise DomainError(409, "RUN_CLOSED", f"Run {run.code} is {run.status.lower()}.")
    if len((note or "").strip()) < 10:
        raise DomainError(422, "REASON_REQUIRED", "Describe the problem for the operator (10+ characters).",
                          {"field": "note"})
    bad = next((s for s in run.steps if s.status in ("FAILED", "UNKNOWN_OUTCOME")), None)
    return _open_incident(session, actor, run, bad, f"Escalated by {actor.name}", note.strip())


def cancel(session: Session, actor: User, run: WorkflowRun, reason: str) -> WorkflowRun:
    """Cancel a stopped run. Completed sandbox writes are NOT deleted: they are listed for manual compensation."""
    require(session, actor, "incident.manage", run.case_id, f"run {run.code}")
    _not_terminal(run)
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise DomainError(422, "REASON_REQUIRED", "Explain why the run is cancelled (10+ characters).",
                          {"field": "reason"})
    done = [{"step": s.label, "external_ref": s.external_ref} for s in run.steps
            if s.idempotency_key and s.status == "SUCCEEDED" and s.external_ref]
    for s in run.steps:
        if s.status in ("PENDING", "BLOCKED", "FAILED", "UNKNOWN_OUTCOME"):
            s.status, s.last_error = "CANCELLED", f"Cancelled: {reason}"
    run.status, run.cancelled_reason, run.finished_at = "CANCELLED", reason, utcnow()
    inc = _open_incident(session, actor, run, None, f"Run {run.code} cancelled", reason)
    inc.compensation = done
    audit.record(session, actor, "workflow.cancelled", "run", run.code,
                 f"Run {run.code} cancelled by {actor.name}: {reason}. "
                 + (f"{len(done)} completed sandbox write(s) need manual compensation." if done else
                    "No external writes were completed."), run.case_id, {"compensation": done})
    pkg = session.get(DecisionPackage, run.package_id)
    cases.refresh_status(session, pkg.case)
    return run


def incidents(session: Session, actor: User, status: str | None = None) -> list[Incident]:
    stmt = select(Incident).where(Incident.organization_id == actor.organization_id)
    if status:
        stmt = stmt.where(Incident.status == status)
    return list(session.scalars(stmt.order_by(Incident.id.desc())))


def resolve_incident(session: Session, actor: User, incident_id: int, resolution: str) -> Incident:
    require(session, actor, "incident.manage", None, f"incident {incident_id}")
    inc = session.get(Incident, incident_id)
    if inc is None or inc.organization_id != actor.organization_id:
        raise DomainError(404, "NOT_FOUND", "Incident was not found.")
    if inc.status != "OPEN":
        raise DomainError(409, "ALREADY_RESOLVED", "Incident is already resolved.")
    if len((resolution or "").strip()) < 10:
        raise DomainError(422, "REASON_REQUIRED", "Describe the resolution (10+ characters).", {"field": "resolution"})
    run = session.get(WorkflowRun, inc.run_id) if inc.run_id else None
    if run is not None and run.status not in TERMINAL:
        raise DomainError(409, "RUN_STILL_OPEN", "Resolve, retry or cancel the run before closing the incident.")
    inc.status, inc.resolution, inc.resolved_by, inc.resolved_at = "RESOLVED", resolution.strip(), actor.id, utcnow()
    audit.record(session, actor, "incident.resolved", "incident", inc.id, f"Incident #{inc.id} resolved: {resolution}",
                 inc.case_id)
    return inc
