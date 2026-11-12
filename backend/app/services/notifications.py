"""In-app notifications (no email/Slack: those need a permissioned connector — spec FR-020)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Notification, User


def notify_roles(session: Session, org_id: str, roles: tuple[str, ...], kind: str, title: str, body: str, link: str,
                 exclude: str | None = None) -> None:
    for u in session.scalars(select(User).where(User.organization_id == org_id, User.role.in_(roles),
                                                User.active.is_(True))):
        if u.id != exclude:
            session.add(Notification(organization_id=org_id, user_id=u.id, kind=kind, title=title, body=body,
                                     link=link))


def notify_users(session: Session, org_id: str, user_ids: set[str], kind: str, title: str, body: str, link: str,
                 exclude: str | None = None) -> None:
    for uid in user_ids - {exclude}:
        session.add(Notification(organization_id=org_id, user_id=uid, kind=kind, title=title, body=body, link=link))


def for_user(session: Session, user: User, limit: int = 30) -> list[Notification]:
    return list(session.scalars(select(Notification).where(Notification.user_id == user.id)
                                .order_by(Notification.id.desc()).limit(limit)))


def mark_read(session: Session, user: User, notification_id: int | None = None) -> None:
    stmt = select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if notification_id is not None:
        stmt = stmt.where(Notification.id == notification_id)
    for n in session.scalars(stmt):
        n.read_at = utcnow()
