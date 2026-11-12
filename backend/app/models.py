"""Relational model (spec §3.5, adapted for the demo). All money columns are whole-rupiah integers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuthSession(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(80), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(80))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AppMeta(Base):
    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    client_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), index=True)
    next_action: Mapped[str] = mapped_column(String(200), default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    extractor: Mapped[str] = mapped_column(String(60))
    flags: Mapped[list] = mapped_column(JSON, default=list)
    action_hints: Mapped[list] = mapped_column(JSON, default=list)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    owner: Mapped[User] = relationship()
    requirements: Mapped[list[Requirement]] = relationship(back_populates="case", order_by="Requirement.position")


class SourceDocument(Base):
    __tablename__ = "source_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # brief | clarification
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(80))
    # client_text = words written by the client (brief, pasted email excerpt);
    # analyst_recorded = an analyst's note of what the client said (no original attached)
    verification: Mapped[str] = mapped_column(String(30), default="client_text")
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)  # email | call | meeting | document
    reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page_breaks: Mapped[list] = mapped_column(JSON, default=list)  # char offsets where pages 2..n start
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Artifact(Base):
    """Original uploaded file (untrusted). Text is extracted from it; the bytes are kept for provenance."""

    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(80), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    pages: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Requirement(Base):
    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("case_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    value_type: Mapped[str] = mapped_column(String(20))
    critical: Mapped[bool] = mapped_column(Boolean)
    state: Mapped[str] = mapped_column(String(20))
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    origin: Mapped[str] = mapped_column(String(30))  # extractor | analyst | clarification
    extracted_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # what the source said
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic concurrency
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="requirements")
    source: Mapped[SourceDocument | None] = relationship()


class RequirementChange(Base):
    __tablename__ = "requirement_changes"
    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    from_state: Mapped[str] = mapped_column(String(20))
    to_state: Mapped[str] = mapped_column(String(20))
    from_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Clarification(Base):
    __tablename__ = "clarifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    requirement_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN | ANSWERED
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answered_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    asked_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    answered_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RateCard(Base):
    __tablename__ = "rate_cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    unit_cost_conservative_idr: Mapped[int] = mapped_column(Integer)
    unit_cost_expected_idr: Mapped[int] = mapped_column(Integer)
    unit_cost_aggressive_idr: Mapped[int] = mapped_column(Integer)
    fixed_cost_idr: Mapped[int] = mapped_column(Integer)
    margin_floor_bp: Mapped[int] = mapped_column(Integer)
    capacity_leads_per_week: Mapped[int] = mapped_column(Integer, default=400)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_to: Mapped[datetime] = mapped_column(DateTime)
    notes: Mapped[str] = mapped_column(Text)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class FeasibilityRun(Base):
    __tablename__ = "feasibility_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    rate_card_id: Mapped[int] = mapped_column(ForeignKey("rate_cards.id"))
    scenario: Mapped[str] = mapped_column(String(20))
    inputs: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    valid: Mapped[bool] = mapped_column(Boolean)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    rate_card: Mapped[RateCard] = relationship()


class DecisionPackage(Base):
    __tablename__ = "decision_packages"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(30), index=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    required_approvals: Mapped[int] = mapped_column(Integer, default=1)
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("decision_packages.id"), nullable=True)
    superseded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Case] = relationship()


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("decision_packages.id"), index=True)
    package_hash: Mapped[str] = mapped_column(String(80))
    package_version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(30))  # APPROVE | REJECT | REQUEST_CHANGES
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ExecutionAuthorization(Base):
    __tablename__ = "execution_authorizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("decision_packages.id"), unique=True)
    package_hash: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    actions: Mapped[list] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("decision_packages.id"), index=True)
    package_hash: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30))
    simulate: Mapped[str] = mapped_column(String(40), default="none")
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    steps: Mapped[list[WorkflowStep]] = relationship(order_by="WorkflowStep.position", back_populates="run")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("run_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    target: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")
    attempt_log: Mapped[list[StepAttempt]] = relationship(order_by="StepAttempt.id")


class StepAttempt(Base):
    __tablename__ = "step_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    step_id: Mapped[int] = mapped_column(ForeignKey("workflow_steps.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # attempt | reconcile
    outcome: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SandboxRecord(Base):
    """Rows 'written' to the simulated CRM / project tracker. Unique idempotency key = no duplicates."""

    __tablename__ = "sandbox_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    system: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(60))
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True)
    external_ref: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditEvent(Base):
    """Append-only: the API exposes no update or delete for this table."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    verb: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class EvalDataset(Base):
    __tablename__ = "eval_datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text)
    manifest_hash: Mapped[str] = mapped_column(String(80))
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class EvalCase(Base):
    __tablename__ = "eval_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("eval_datasets.id"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    split: Mapped[str] = mapped_column(String(20), default="dev")  # dev (used for tuning) | heldout (never)
    category: Mapped[str] = mapped_column(String(80))
    brief: Mapped[str] = mapped_column(Text)
    expected: Mapped[dict] = mapped_column(JSON)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("eval_datasets.id"), index=True)
    extractor_version: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(30), default="demo")
    status: Mapped[str] = mapped_column(String(20))
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    started_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class EvalResult(Base):
    __tablename__ = "eval_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    eval_case_id: Mapped[int] = mapped_column(ForeignKey("eval_cases.id"))
    outcome: Mapped[str] = mapped_column(String(10))  # PASS | FAIL
    failure_categories: Mapped[list] = mapped_column(JSON, default=list)
    checks: Mapped[list] = mapped_column(JSON, default=list)
    actual: Mapped[dict] = mapped_column(JSON, default=dict)
    adjudication: Mapped[str | None] = mapped_column(String(30), nullable=True)
    adjudication_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjudicated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    adjudicated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    eval_case: Mapped[EvalCase] = relationship()


class ImpactCohortCase(Base):
    """Synthetic cohort generated by a fixed-seed generator (seed.py). Not real operating data."""

    __tablename__ = "impact_cohort_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    period: Mapped[str] = mapped_column(String(20))  # baseline | assisted
    flow: Mapped[str] = mapped_column(String(20))  # manual | assisted
    segment: Mapped[str] = mapped_column(String(60))
    handler_id: Mapped[str] = mapped_column(String(20), default="")  # synthetic analyst id
    created_at: Mapped[datetime] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean)
    approved: Mapped[bool] = mapped_column(Boolean)
    verified: Mapped[bool] = mapped_column(Boolean)
    overridden: Mapped[bool] = mapped_column(Boolean)
    override_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    workflow_status: Mapped[str | None] = mapped_column(String(30), nullable=True)


class Connector(Base):
    """Connector manifest (spec §3.7). The model cannot change it; only an admin can enable/disable."""

    __tablename__ = "connectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    actions: Mapped[list] = mapped_column(JSON)
    risk_class: Mapped[str] = mapped_column(String(20))
    supports_idempotency: Mapped[bool] = mapped_column(Boolean)
    supports_read_after_write: Mapped[bool] = mapped_column(Boolean)
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OutboxEvent(Base):
    """Transactional outbox: written in the same transaction as the run; a worker claims it with a lease."""

    __tablename__ = "outbox_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    state: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING|CLAIMED|DONE|FAILED
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claim_token: Mapped[str | None] = mapped_column(String(40), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Incident(Base):
    """Exception queue entry needing human recovery (spec FR-013)."""

    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)
    step_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")  # OPEN | RESOLVED
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text)
    compensation: Mapped[list] = mapped_column(JSON, default=list)  # external refs that need manual follow-up
    opened_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(200))
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
