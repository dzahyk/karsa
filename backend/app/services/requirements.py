"""Requirement review, clarification and re-extraction. Every change is recorded with actor and reason."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..domain.catalog import BY_KEY, normalize_value
from ..domain.extraction import ExtractionResult
from ..domain.hashing import text_hash
from ..models import Case, Clarification, Requirement, RequirementChange, SourceDocument, User
from . import audit, cases, packages
from .errors import DomainError

ACTIONS = ("confirm", "edit", "mark_missing", "not_applicable")
CHANNELS = ("email", "call", "meeting", "document", "chat")


def assert_editable(session: Session, case: Case) -> None:
    reason = cases.lock_reason(session, case)
    if reason:
        raise DomainError(409, "CASE_LOCKED", reason)


def _get(case: Case, key: str) -> Requirement:
    for r in case.requirements:
        if r.key == key:
            return r
    raise DomainError(404, "NOT_FOUND", f"Requirement '{key}' was not found.")


def _check_version(r: Requirement, expected: int | None) -> None:
    if expected is not None and expected != r.version:
        raise DomainError(409, "VERSION_CONFLICT",
                          f"{r.label} was changed by someone else after you opened it. Reload to see the latest "
                          "value before saving.", {"expected_version": expected, "current_version": r.version,
                                                   "current_value": r.value, "current_state": r.state})


def _log(session: Session, actor: User, r: Requirement, action: str, from_state: str, from_value: str | None,
         reason: str | None) -> None:
    session.add(RequirementChange(requirement_id=r.id, case_id=r.case_id, actor_id=actor.id, action=action,
                                  from_state=from_state, to_state=r.state, from_value=from_value,
                                  to_value=r.value, reason=reason))
    r.version += 1
    r.updated_by, r.updated_at = actor.id, utcnow()


def update(session: Session, actor: User, case: Case, key: str, action: str, value: str | None,
           reason: str | None, expected_version: int | None = None) -> Requirement:
    assert_editable(session, case)
    r = _get(case, key)
    _check_version(r, expected_version)
    reason = (reason or "").strip() or None
    before_state, before_value = r.state, r.value
    if action == "confirm":
        if r.state == "CONFLICTING":
            raise DomainError(422, "CHOOSE_VALUE", "Pick one of the conflicting values (edit) before confirming.")
        if not r.value:
            raise DomainError(422, "NO_VALUE", "There is no value to confirm. Enter one or ask a clarification.")
        if r.state == "CONFIRMED":
            return r
        r.state = "CONFIRMED"
        summary = f"{r.label} confirmed: {r.value}."
    elif action == "edit":
        if not reason:
            raise DomainError(422, "REASON_REQUIRED", "Explain why the value is being changed.", {"field": "reason"})
        try:
            new_value = normalize_value(r.value_type, value)
        except ValueError as e:
            raise DomainError(422, "VALIDATION_ERROR", str(e), {"field": "value"}) from e
        chosen = next((c for c in r.candidates if c["value"] == new_value), None)
        if chosen:  # resolving a conflict: keep the provenance of the chosen candidate
            s = chosen["span"]
            r.span_start, r.span_end, r.quote = s["start"], s["end"], s["quote"]
            r.source_document_id = chosen["source_document_id"]
            r.extracted_value = new_value
            r.origin = "extractor"
            r.note = f"Conflict resolved by analyst: {reason}"
        else:
            # the original source stays visible as provenance; `overridden` flags that the value differs from it
            r.origin = "analyst"
            r.note = f"Analyst override: {reason}"
        r.value, r.state = new_value, "CONFIRMED"
        summary = f"{r.label} changed from {before_value or '—'} to {new_value}. Reason: {reason}"
    elif action == "mark_missing":
        if not reason:
            raise DomainError(422, "REASON_REQUIRED", "Explain why this is missing.", {"field": "reason"})
        r.state, r.value, r.note = "MISSING", None, f"Marked missing: {reason}"
        summary = f"{r.label} marked missing. Reason: {reason}"
    elif action == "not_applicable":
        if r.critical:
            raise DomainError(422, "CRITICAL_REQUIREMENT", "Critical requirements cannot be marked not applicable.")
        if not reason:
            raise DomainError(422, "REASON_REQUIRED", "Explain why this does not apply.", {"field": "reason"})
        r.state, r.value, r.note = "NOT_APPLICABLE", None, f"Not applicable: {reason}"
        summary = f"{r.label} marked not applicable. Reason: {reason}"
    else:
        raise DomainError(422, "VALIDATION_ERROR", f"Unknown action '{action}'.")
    _log(session, actor, r, action, before_state, before_value, reason)
    audit.record(session, actor, f"requirement.{action}", "requirement", r.key, summary, case.id,
                 {"from": {"state": before_state, "value": before_value}, "to": {"state": r.state, "value": r.value}})
    packages.supersede_active(session, actor, case, f"{r.label} changed after the package was frozen.")
    return r


def overridden(r: Requirement) -> bool:
    return r.origin == "analyst" and r.quote is not None and r.value != r.extracted_value


def history(session: Session, case: Case) -> list[RequirementChange]:
    return list(session.scalars(select(RequirementChange).where(RequirementChange.case_id == case.id)
                                .order_by(RequirementChange.id.desc())))


def list_clarifications(session: Session, case: Case) -> list[Clarification]:
    return list(session.scalars(select(Clarification).where(Clarification.case_id == case.id)
                                .order_by(Clarification.id)))


def ask(session: Session, actor: User, case: Case, requirement_key: str | None, question: str) -> Clarification:
    assert_editable(session, case)
    question = question.strip()
    if len(question) < 5:
        raise DomainError(422, "VALIDATION_ERROR", "Write a question of at least 5 characters.", {"field": "question"})
    if requirement_key and requirement_key not in BY_KEY:
        raise DomainError(422, "VALIDATION_ERROR", "Unknown requirement.", {"field": "requirement_key"})
    c = Clarification(case_id=case.id, requirement_key=requirement_key, question=question, asked_by=actor.id)
    session.add(c)
    session.flush()
    audit.record(session, actor, "clarification.asked", "clarification", c.id, f"Question: {question}", case.id)
    return c


def suggest(session: Session, actor: User, case: Case) -> list[Clarification]:
    """Create questions from the known required-field list for each unresolved critical requirement."""
    open_keys = {c.requirement_key for c in list_clarifications(session, case) if c.status == "OPEN"}
    created = []
    for r in case.requirements:
        if r.critical and r.state in ("MISSING", "CONFLICTING", "DRAFT") and r.key not in open_keys:
            q = BY_KEY[r.key].question
            if r.state == "CONFLICTING":
                vals = ", ".join(c["span"]["quote"] for c in r.candidates)
                q = f"The brief mentions different values for {r.label.lower()} ({vals}). Which one applies?"
            elif r.state == "DRAFT":
                q = f"Please confirm {r.label.lower()}: is “{r.quote}” correct?"
            created.append(ask(session, actor, case, r.key, q))
    return created


def answer(session: Session, actor: User, case: Case, clarification_id: int, answer_text: str,
           answered_by_name: str, apply_value: str | None, apply: bool, channel: str, reference: str,
           client_excerpt: str | None = None, expected_version: int | None = None) -> Clarification:
    """Record a client answer. If the client's own words are pasted (excerpt), they become client_text evidence;
    otherwise the answer is stored as `analyst_recorded` evidence and flagged as such everywhere it is shown."""
    assert_editable(session, case)
    c = session.get(Clarification, clarification_id)
    if c is None or c.case_id != case.id:
        raise DomainError(404, "NOT_FOUND", "Clarification was not found.")
    if c.status != "OPEN":
        raise DomainError(409, "ALREADY_ANSWERED", "This question has already been answered.")
    text, who = answer_text.strip(), answered_by_name.strip()
    excerpt = (client_excerpt or "").strip() or None
    ref = (reference or "").strip()
    if len(text) < 2:
        raise DomainError(422, "VALIDATION_ERROR", "Enter the answer.", {"field": "answer"})
    if not who:
        raise DomainError(422, "VALIDATION_ERROR", "Say who gave the answer (e.g. the client contact).",
                          {"field": "answered_source"})
    if channel not in CHANNELS:
        raise DomainError(422, "VALIDATION_ERROR", "Choose how the answer was received.", {"field": "channel"})
    if len(ref) < 3:
        raise DomainError(422, "VALIDATION_ERROR",
                          "Add a reference someone else can check (email subject and date, call date, meeting notes).",
                          {"field": "reference"})
    r = None
    new_value = None
    if apply:
        if not c.requirement_key:
            raise DomainError(422, "VALIDATION_ERROR", "This question is not linked to a requirement.")
        r = _get(case, c.requirement_key)
        _check_version(r, expected_version)
        raw = apply_value if (apply_value and apply_value.strip()) else (text if r.value_type == "text" else None)
        try:
            new_value = normalize_value(r.value_type, raw)
        except ValueError as e:
            raise DomainError(422, "VALIDATION_ERROR", f"Value to apply: {e}", {"field": "apply_value"}) from e
    content = excerpt or text
    verification = "client_text" if excerpt else "analyst_recorded"
    doc = SourceDocument(case_id=case.id, kind="clarification",
                         title=f"Clarification #{c.id} — {channel} from {who}", content=content,
                         sha256=text_hash(content), created_by=actor.id, verification=verification,
                         channel=channel, reference=ref)
    session.add(doc)
    session.flush()
    c.status, c.answer, c.answered_source = "ANSWERED", text, who
    c.channel, c.reference = channel, ref
    c.answered_by, c.answered_at, c.source_document_id = actor.id, utcnow(), doc.id
    audit.record(session, actor, "clarification.answered", "clarification", c.id,
                 f"Answer recorded from {who} via {channel} ({ref}); evidence: "
                 f"{'client text' if excerpt else 'analyst-recorded'}.", case.id)
    if r is not None:
        before_state, before_value = r.state, r.value
        r.value, r.state, r.origin = new_value, "CONFIRMED", "clarification"
        r.extracted_value = new_value
        r.source_document_id, r.span_start, r.span_end, r.quote = doc.id, 0, len(content), content
        r.note = f"Confirmed through clarification #{c.id} ({channel}: {ref})."
        r.candidates = []
        c.applied = True
        _log(session, actor, r, "clarification", before_state, before_value, f"Answered via clarification #{c.id}")
        audit.record(session, actor, "requirement.clarified", "requirement", r.key,
                     f"{r.label} set to {new_value} from clarification #{c.id}.", case.id)
        packages.supersede_active(session, actor, case, f"{r.label} changed after the package was frozen.")
    return c


def reextract(session: Session, actor: User, case: Case, result: ExtractionResult) -> int:
    """Re-run extraction on the stored brief. Only fields no human has touched are replaced."""
    assert_editable(session, case)
    brief = session.scalar(select(SourceDocument).where(SourceDocument.case_id == case.id,
                                                        SourceDocument.kind == "brief"))
    changed = 0
    for r in case.requirements:
        f = result.fields.get(r.key)
        if f is None or r.updated_by is not None or r.origin != "extractor":
            continue
        new = (f.state, f.value, f.span.start if f.span else None, f.span.end if f.span else None)
        if new == (r.state, r.value, r.span_start, r.span_end) and f.candidates == [
                {k: v for k, v in c.items() if k != "source_document_id"} for c in r.candidates]:
            continue
        r.state, r.value, r.extracted_value, r.note = f.state, f.value, f.value, f.note
        r.span_start, r.span_end = (f.span.start, f.span.end) if f.span else (None, None)
        r.quote = f.span.quote if f.span else None
        r.source_document_id = brief.id if (f.span or f.candidates) else None
        r.candidates = [{**c, "source_document_id": brief.id} for c in f.candidates]
        r.version += 1
        changed += 1
    case.flags = [{"kind": fl.kind, "message": fl.message, "span": fl.span.__dict__} for fl in result.flags]
    case.action_hints = result.action_hints
    case.extractor = result.extractor
    audit.record(session, actor, "extraction.rerun", "case", case.code,
                 f"Extraction re-run with {result.extractor}: {changed} untouched field(s) updated; "
                 "human-reviewed fields were kept.", case.id)
    if changed:
        packages.supersede_active(session, actor, case, "Extraction re-run changed draft requirements.")
    cases.refresh_status(session, case)
    return changed
