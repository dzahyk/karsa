"""Workspace administration: rate card versions, connector switches, users, global audit."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import AuditEvent, Connector, RateCard, User
from . import audit
from .authz import require
from .errors import DomainError


def rate_cards(session: Session, actor: User) -> list[RateCard]:
    return list(session.scalars(select(RateCard).where(RateCard.organization_id == actor.organization_id)
                                .order_by(RateCard.valid_from.desc(), RateCard.id.desc())))


def create_rate_card(session: Session, actor: User, data: dict) -> RateCard:
    """New version becomes current now; the previous card ends now, so packages priced on it must be repriced."""
    require(session, actor, "manage.rate_cards", entity="rate card")
    fields = ("unit_cost_conservative_idr", "unit_cost_expected_idr", "unit_cost_aggressive_idr", "fixed_cost_idr",
              "margin_floor_bp", "capacity_leads_per_week")
    for f in fields:
        v = data.get(f)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > 10**12:
            raise DomainError(422, "VALIDATION_ERROR", "Enter whole, non-negative numbers.", {"field": f})
    if not (data["unit_cost_aggressive_idr"] <= data["unit_cost_expected_idr"] <= data["unit_cost_conservative_idr"]):
        raise DomainError(422, "VALIDATION_ERROR", "Unit costs must be aggressive ≤ expected ≤ conservative.",
                          {"field": "unit_cost_expected_idr"})
    if not (0 < data["margin_floor_bp"] < 10000) or data["capacity_leads_per_week"] < 1:
        raise DomainError(422, "VALIDATION_ERROR", "Margin floor must be between 0 and 100% and capacity at least 1.",
                          {"field": "margin_floor_bp"})
    now = utcnow()
    current = rate_cards(session, actor)
    n = session.scalar(select(func.count()).select_from(RateCard)
                       .where(RateCard.organization_id == actor.organization_id)) or 0
    for c in current:
        if c.valid_to > now:
            c.valid_to = now
    card = RateCard(code=f"RC-{n + 3}", name=(data.get("name") or "Campaign lead generation rate card").strip()[:200],
                    organization_id=actor.organization_id, created_by=actor.id, valid_from=now,
                    valid_to=now + timedelta(days=365), notes=(data.get("notes") or "").strip()[:1000],
                    **{f: data[f] for f in fields})
    session.add(card)
    session.flush()
    audit.record(session, actor, "rate_card.created", "rate_card", card.code,
                 f"{actor.name} published rate card {card.code}; previous versions ended now. Packages priced on an "
                 "older card must be repriced before approval or execution (BR-013).")
    return card


def set_connector(session: Session, actor: User, key: str, enabled: bool, reason: str) -> Connector:
    require(session, actor, "manage.integrations", entity=f"connector {key}")
    c = session.scalar(select(Connector).where(Connector.organization_id == actor.organization_id,
                                               Connector.key == key))
    if c is None:
        raise DomainError(404, "NOT_FOUND", "Connector was not found.")
    if len((reason or "").strip()) < 5:
        raise DomainError(422, "REASON_REQUIRED", "Give a reason for the change.", {"field": "reason"})
    c.enabled, c.updated_by, c.updated_at = enabled, actor.id, utcnow()
    audit.record(session, actor, "connector.enabled" if enabled else "connector.disabled", "connector", key,
                 f"{actor.name} {'enabled' if enabled else 'disabled'} {c.name}: {reason}")
    return c


def global_audit(session: Session, actor: User, verb: str | None, actor_id: str | None, limit: int,
                 offset: int) -> tuple[list[AuditEvent], int]:
    require(session, actor, "audit.read", entity="audit log")
    stmt = select(AuditEvent).where(AuditEvent.organization_id == actor.organization_id)
    if verb:
        stmt = stmt.where(AuditEvent.verb.like(f"{verb}%"))
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(session.scalars(stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)))
    return rows, total
