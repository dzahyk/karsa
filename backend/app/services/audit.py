from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditEvent, User
from ..security import request_id_var


def record(session: Session, actor: User | None, verb: str, entity_type: str, entity_id: str | int,
           summary: str, case_id: int | None = None, detail: dict | None = None,
           organization_id: str | None = None) -> AuditEvent:
    ev = AuditEvent(
        case_id=case_id,
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else "SYSTEM",
        verb=verb,
        entity_type=entity_type,
        entity_id=str(entity_id),
        summary=summary,
        detail=detail or {},
        request_id=request_id_var.get(),
        organization_id=organization_id or (actor.organization_id if actor else None),
    )
    session.add(ev)
    return ev
