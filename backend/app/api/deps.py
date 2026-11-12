from __future__ import annotations

import hmac

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import User
from ..security import SESSION_COOKIE, resolve_session
from ..services.errors import DomainError

SAFE = {"GET", "HEAD", "OPTIONS"}


def actor(request: Request, session: Session = Depends(get_session)) -> User:
    """Authenticated user from the session cookie. Mutations also need the matching CSRF header."""
    s = resolve_session(session, request.cookies.get(SESSION_COOKIE))
    if s is None:
        raise DomainError(401, "NOT_AUTHENTICATED", "Your session has expired or you are not signed in.")
    u = session.get(User, s.user_id)
    if u is None or not u.active:
        raise DomainError(401, "NOT_AUTHENTICATED", "This account is not active.")
    if request.method not in SAFE:
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent, s.csrf_token):
            raise DomainError(403, "CSRF_FAILED", "Security token missing or invalid. Reload the page and try again.")
    request.state.user_id = u.id
    return u


def users_by_id(session: Session) -> dict[str, User]:
    return {u.id: u for u in session.scalars(select(User))}
