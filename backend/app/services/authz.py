from __future__ import annotations

from sqlalchemy.orm import Session

from ..domain.permissions import ROLES, can
from ..models import User
from . import audit
from .errors import DomainError


def require(session: Session, actor: User, permission: str, case_id: int | None = None,
            entity: str = "-") -> None:
    """Server-side permission gate for reads and writes. Denials are audited (spec AC-08)."""
    if can(actor.role, permission):
        return
    session.rollback()
    audit.record(session, actor, "security.denied", "permission", permission,
                 f"{actor.name} ({ROLES.get(actor.role, actor.role)}) was denied '{permission}' on {entity}.",
                 case_id=case_id, detail={"permission": permission, "entity": entity})
    session.commit()
    raise DomainError(403, "FORBIDDEN",
                      f"Your role ({ROLES.get(actor.role, actor.role)}) is not allowed to do this.",
                      {"permission": permission})
