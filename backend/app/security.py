"""Password hashing (scrypt), server-side sessions and request context."""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import AuthSession, User

SESSION_COOKIE = "df_session"
CSRF_COOKIE = "df_csrf"
SESSION_TTL = timedelta(hours=8)
_N, _R, _P = 2**14, 8, 1

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, dk = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(got.hex(), dk)
    except (ValueError, TypeError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session, user: User) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    session.add(AuthSession(token_hash=_hash_token(token), csrf_token=csrf, user_id=user.id,
                            expires_at=utcnow() + SESSION_TTL))
    return token, csrf


def resolve_session(session: Session, token: str | None) -> AuthSession | None:
    if not token:
        return None
    s = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
    if s is None or s.revoked or s.expires_at < utcnow():
        return None
    return s


def revoke(session: Session, token: str | None) -> None:
    s = resolve_session(session, token)
    if s:
        s.revoked = True
