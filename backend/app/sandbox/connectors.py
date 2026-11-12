"""Simulated CRM and project tracker. NOT real integrations.

Writes are rows in ``sandbox_records`` with a unique idempotency key, so replaying the same key returns
the existing record instead of creating a duplicate (spec BR-007, AC-05). Failure modes are injected on
purpose for the demo and are labelled as simulated everywhere they appear.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SandboxRecord

PREFIX = {"crm.create_opportunity": "OPP-SBX", "tracker.create_project": "PRJ-SBX",
          "tracker.attach_spec": "ATT-SBX"}
SIMULATIONS = {
    "none": "No injected failure",
    "tracker_timeout_before_commit": "Tracker times out before committing (first attempt) — safe to retry",
    "tracker_timeout_after_commit": "Tracker commits but the response is lost (first attempt) — outcome unknown",
}


@dataclass
class WriteResult:
    outcome: str  # SUCCEEDED | FAILED | UNKNOWN_OUTCOME
    record: SandboxRecord | None
    detail: str
    replayed: bool = False


def read_back(session: Session, idempotency_key: str) -> SandboxRecord | None:
    return session.scalar(select(SandboxRecord).where(SandboxRecord.idempotency_key == idempotency_key))


def _commit(session: Session, action: str, key: str, payload: dict) -> tuple[SandboxRecord, bool]:
    existing = read_back(session, key)
    if existing:
        return existing, True
    rec = SandboxRecord(system=action.split(".")[0], action=action, idempotency_key=key, external_ref="pending",
                        payload=payload)
    session.add(rec)
    session.flush()
    rec.external_ref = f"{PREFIX[action]}-{rec.id:05d}"
    return rec, False


def write(session: Session, action: str, key: str, payload: dict, simulate: str, attempt: int) -> WriteResult:
    tracker = action.startswith("tracker.create_project")
    if tracker and simulate == "tracker_timeout_before_commit" and attempt == 1:
        return WriteResult("FAILED", None, "Connection timed out after 30 s (simulated). The tracker did not "
                                           "receive the request; nothing was created.")
    if tracker and simulate == "tracker_timeout_after_commit" and attempt == 1:
        _commit(session, action, key, payload)  # the target commits…
        return WriteResult("UNKNOWN_OUTCOME", None, "Timed out waiting for the tracker's response (simulated). "
                                                    "The project may or may not exist.")  # …but we never hear back
    rec, replayed = _commit(session, action, key, payload)
    detail = (f"Idempotent replay: existing record {rec.external_ref} returned, no duplicate created."
              if replayed else f"Created {rec.external_ref} in the {rec.system.upper()} sandbox.")
    return WriteResult("SUCCEEDED", rec, detail, replayed)
