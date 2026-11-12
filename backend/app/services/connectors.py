"""Connector manifest checks: an action may run only if its connector is registered and enabled."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Connector
from .errors import DomainError

MANIFEST = [
    {"key": "crm", "name": "CRM (sandbox)", "actions": ["crm.create_opportunity"], "risk_class": "medium",
     "supports_idempotency": True, "supports_read_after_write": True},
    {"key": "tracker", "name": "Project tracker (sandbox)", "actions": ["tracker.create_project", "tracker.attach_spec"],
     "risk_class": "low", "supports_idempotency": True, "supports_read_after_write": True},
]


def for_org(session: Session, org_id: str) -> list[Connector]:
    return list(session.scalars(select(Connector).where(Connector.organization_id == org_id).order_by(Connector.id)))


def assert_enabled(session: Session, org_id: str, actions: list[str]) -> None:
    by_action = {a: c for c in for_org(session, org_id) for a in c.actions}
    for a in actions:
        c = by_action.get(a)
        if c is None:
            raise DomainError(409, "CONNECTOR_MISSING", f"No connector is registered for action '{a}'.")
        if not c.enabled:
            raise DomainError(409, "CONNECTOR_DISABLED",
                              f"{c.name} is disabled by an admin. Execution is blocked until it is re-enabled.",
                              {"connector": c.key, "action": a})
