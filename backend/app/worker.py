"""Outbox worker. Claims events with a lease (a crashed worker's events are re-claimed after LEASE) and advances
workflow runs. Runs as a background thread inside the API by default, or standalone: `python -m app.worker`."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import timedelta

from sqlalchemy import or_, select, update

from .db import SessionLocal, utcnow
from .models import OutboxEvent, User, WorkflowRun

log = logging.getLogger("decisionflow.worker")
LEASE = timedelta(seconds=30)
MAX_ATTEMPTS = 5


def claim(session_factory=SessionLocal) -> int | None:
    with session_factory() as s:
        now = utcnow()
        ev = s.scalar(select(OutboxEvent).where(or_(
            OutboxEvent.state == "PENDING",
            (OutboxEvent.state == "CLAIMED") & (OutboxEvent.claimed_at < now - LEASE),
        )).order_by(OutboxEvent.id).limit(1))
        if ev is None:
            return None
        token = secrets.token_hex(8)
        res = s.execute(update(OutboxEvent).where(OutboxEvent.id == ev.id, OutboxEvent.state == ev.state,
                                                  OutboxEvent.claim_token.is_(ev.claim_token))
                        .values(state="CLAIMED", claim_token=token, claimed_at=now))
        s.commit()
        return ev.id if res.rowcount == 1 else None


def process(event_id: int, session_factory=SessionLocal) -> None:
    from .services import execution

    with session_factory() as s:
        ev = s.get(OutboxEvent, event_id)
        try:
            run = s.get(WorkflowRun, ev.run_id)
            actor = s.get(User, ev.actor_id)
            if run is not None and run.status not in execution.TERMINAL:
                execution.advance(s, actor, run)
            ev.state, ev.processed_at = "DONE", utcnow()
            s.commit()
        except Exception as exc:  # keep the worker alive; the event is retried with a bounded count
            s.rollback()
            ev = s.get(OutboxEvent, event_id)
            ev.attempts += 1
            ev.last_error = type(exc).__name__
            ev.state = "FAILED" if ev.attempts >= MAX_ATTEMPTS else "PENDING"
            s.commit()
            log.exception("outbox event %s failed", event_id)


def drain(session_factory=SessionLocal, limit: int = 200) -> int:
    n = 0
    while n < limit and (eid := claim(session_factory)) is not None:
        process(eid, session_factory)
        n += 1
    return n


class BackgroundWorker:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="outbox-worker", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop.is_set():
            try:
                if drain(limit=20) == 0:
                    self._stop.wait(self.interval)
            except Exception:
                log.exception("worker loop error")
                self._stop.wait(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("outbox worker started")
    while True:
        if drain() == 0:
            time.sleep(0.5)
