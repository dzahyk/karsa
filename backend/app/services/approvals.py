"""Human approval and execution authorization — two separate acts (spec §2.5, §4.8)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.hashing import content_hash
from ..models import ApprovalRecord, DecisionPackage, ExecutionAuthorization, User
from . import audit, cases, connectors, feasibility, notifications, packages
from .authz import require
from .errors import DomainError

DECISIONS = ("APPROVE", "REJECT", "REQUEST_CHANGES")


def _assert_current(session: Session, pkg: DecisionPackage, package_hash: str, version: int) -> None:
    latest = cases.latest_package(session, pkg.case)
    if pkg.content_hash != package_hash or pkg.version != version or latest is None or latest.id != pkg.id \
            or pkg.state == "SUPERSEDED":
        raise DomainError(409, "APPROVAL_SNAPSHOT_CHANGED",
                          "The package changed after you opened it. Load the latest version before deciding.",
                          {"expected_version": version, "current_version": latest.version if latest else None,
                           "expected_hash": package_hash, "current_hash": latest.content_hash if latest else None})


def assert_rate_card_valid(session: Session, pkg: DecisionPackage) -> None:
    """BR-013: pricing on an expired or replaced rate card must be repriced and re-reviewed."""
    code = pkg.content["pricing"]["rate_card"]
    card = feasibility.card_by_code(session, pkg.case.organization_id, code)
    if card is None or feasibility.card_expired(card):
        raise DomainError(409, "RATE_CARD_EXPIRED",
                          f"Rate card {code} used by this package is no longer valid. Reprice the case and create a "
                          "new package version.", {"rate_card": code})


def approvals_for(session: Session, pkg: DecisionPackage) -> list[ApprovalRecord]:
    return list(session.scalars(select(ApprovalRecord).where(ApprovalRecord.package_id == pkg.id,
                                                             ApprovalRecord.decision == "APPROVE")))


def review(session: Session, actor: User, pkg: DecisionPackage, decision: str, note: str | None,
           package_hash: str, version: int) -> ApprovalRecord:
    require(session, actor, "package.review", pkg.case_id, f"package v{pkg.version}")
    if decision not in DECISIONS:
        raise DomainError(422, "VALIDATION_ERROR", "Decision must be APPROVE, REJECT or REQUEST_CHANGES.")
    _assert_current(session, pkg, package_hash, version)
    if pkg.state != "IN_REVIEW":
        raise DomainError(409, "NOT_IN_REVIEW", f"Package v{pkg.version} is {pkg.state.lower()}, not in review.")
    if pkg.created_by == actor.id:
        audit.record(session, actor, "security.denied", "package", pkg.id,
                     "Segregation of duties: the package author tried to review their own package.", pkg.case_id)
        session.commit()
        raise DomainError(403, "SOD_VIOLATION", "You prepared this package, so you cannot review it.")
    note = (note or "").strip() or None
    if decision in ("REJECT", "REQUEST_CHANGES") and not note:
        raise DomainError(422, "NOTE_REQUIRED", "A reviewer note is required to reject or request changes.",
                          {"field": "note"})
    prior = approvals_for(session, pkg)
    if decision == "APPROVE":
        if any(a.actor_id == actor.id for a in prior):
            raise DomainError(409, "ALREADY_APPROVED", "You already approved this package. A different approver "
                              "must give the second approval.")
        if content_hash(pkg.content) != pkg.content_hash:
            raise DomainError(409, "HASH_MISMATCH", "Stored package content does not match its hash.")
        blockers = packages.validate_for_approval(pkg.content)
        if blockers:
            raise DomainError(422, "APPROVAL_BLOCKED", "Critical information is incomplete; the package cannot be "
                              "approved.", {"blockers": blockers})
        assert_rate_card_valid(session, pkg)
        if pkg.risk_level == "HIGH" and not note:
            raise DomainError(422, "NOTE_REQUIRED", "High-risk packages need an exception note to approve.",
                              {"field": "note"})
    rec = ApprovalRecord(package_id=pkg.id, package_hash=pkg.content_hash, package_version=pkg.version,
                         actor_id=actor.id, decision=decision, note=note)
    session.add(rec)
    case = pkg.case
    link = f"/approvals/{pkg.id}"
    owners = {pkg.created_by, case.owner_id}
    if decision == "APPROVE" and len(prior) + 1 < pkg.required_approvals:
        session.flush()
        audit.record(session, actor, "package.approve_partial", "package", pkg.id,
                     f"Approval {len(prior) + 1} of {pkg.required_approvals} recorded by {actor.name} for package "
                     f"v{pkg.version}; a second approver is required (high risk)." + (f" Note: {note}" if note else ""),
                     pkg.case_id, {"hash": pkg.content_hash})
        notifications.notify_roles(session, case.organization_id, ("APPROVER",), "package.second_approval",
                                   f"Second approval needed: {case.client_name} v{pkg.version}",
                                   f"{actor.name} approved; a different approver must confirm (high risk).", link,
                                   exclude=actor.id)
        cases.refresh_status(session, case)
        return rec
    pkg.state = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REQUEST_CHANGES": "CHANGES_REQUESTED"}[decision]
    session.flush()
    verb = {"APPROVE": "approved", "REJECT": "rejected", "REQUEST_CHANGES": "returned for changes"}[decision]
    audit.record(session, actor, f"package.{decision.lower()}", "package", pkg.id,
                 f"Package v{pkg.version} {verb} by {actor.name}." + (f" Note: {note}" if note else ""),
                 pkg.case_id, {"hash": pkg.content_hash})
    notifications.notify_users(session, case.organization_id, owners, f"package.{decision.lower()}",
                               f"{case.code} v{pkg.version} {verb}", note or f"Decision by {actor.name}.", link)
    if decision == "APPROVE":
        notifications.notify_roles(session, case.organization_id, ("APPROVER",), "package.needs_authorization",
                                   f"Authorize execution: {case.client_name} v{pkg.version}",
                                   "The decision is approved; execution still needs a separate authorization.", link)
    cases.refresh_status(session, case)
    return rec


def authorize(session: Session, actor: User, pkg: DecisionPackage, package_hash: str,
              confirmed_actions: list[str], note: str | None) -> ExecutionAuthorization:
    require(session, actor, "execution.authorize", pkg.case_id, f"package v{pkg.version}")
    _assert_current(session, pkg, package_hash, pkg.version)
    if pkg.state != "APPROVED":
        raise DomainError(409, "NOT_APPROVED", "Only an approved decision can be authorized for execution.")
    if session.scalar(select(ExecutionAuthorization).where(ExecutionAuthorization.package_id == pkg.id)):
        raise DomainError(409, "ALREADY_AUTHORIZED", "Execution is already authorized for this package.")
    assert_rate_card_valid(session, pkg)
    expected = [a["action"] for a in pkg.content["proposed_actions"]]  # package order = execution order
    if sorted(confirmed_actions) != sorted(expected):
        raise DomainError(422, "ACTIONS_NOT_CONFIRMED",
                          "Confirm exactly the downstream actions listed in the package.", {"expected": expected})
    connectors.assert_enabled(session, pkg.case.organization_id, expected)
    auth = ExecutionAuthorization(package_id=pkg.id, package_hash=pkg.content_hash, actor_id=actor.id,
                                  actions=expected, note=(note or "").strip() or None)
    session.add(auth)
    session.flush()
    audit.record(session, actor, "execution.authorized", "package", pkg.id,
                 f"{actor.name} authorized {len(expected)} sandbox action(s) for package v{pkg.version}.",
                 pkg.case_id, {"actions": expected, "hash": pkg.content_hash})
    case = pkg.case
    notifications.notify_roles(session, case.organization_id, ("AUTOMATION_ENGINEER",), "execution.authorized",
                               f"Ready to run: {case.client_name} v{pkg.version}",
                               f"{actor.name} authorized {len(expected)} sandbox action(s).", f"/approvals/{pkg.id}")
    notifications.notify_users(session, case.organization_id, {case.owner_id}, "execution.authorized",
                               f"{case.code} authorized for execution", f"Authorized by {actor.name}.",
                               f"/approvals/{pkg.id}")
    cases.refresh_status(session, case)
    return auth


def records(session: Session, pkg: DecisionPackage) -> list[ApprovalRecord]:
    return list(session.scalars(select(ApprovalRecord).where(ApprovalRecord.package_id == pkg.id)
                                .order_by(ApprovalRecord.id)))
