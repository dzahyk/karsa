from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.providers import AnthropicProvider, get_provider
from ..config import get_settings
from ..db import get_session, utcnow
from ..domain.hashing import text_hash
from ..domain.permissions import ROLES, can
from ..evaluation import runner
from ..evaluation.runner import ADJUDICATIONS, CATEGORIES, GATE
from ..models import (
    AppMeta,
    Artifact,
    AuditEvent,
    DecisionPackage,
    EvalCase,
    EvalDataset,
    EvalResult,
    EvalRun,
    ExecutionAuthorization,
    ImpactCohortCase,
    Incident,
    Notification,
    RateCard,
    SourceDocument,
    User,
    WorkflowRun,
)
from ..sandbox.connectors import SIMULATIONS
from ..security import CSRF_COOKIE, SESSION_COOKIE, SESSION_TTL, create_session, revoke, verify_password
from ..services import (
    admin,
    approvals,
    cases,
    connectors,
    execution,
    exports,
    feasibility,
    impact,
    intake,
    notifications,
    packages,
    requirements,
)
from ..services.authz import require
from ..services.errors import DomainError
from . import serializers as S
from .deps import actor, users_by_id

router = APIRouter(prefix="/api/v1")
SCENARIO_RE = "^(conservative|expected|aggressive)$"


# ---------- request bodies (validated server-side) ----------
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class DemoLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)


class CaseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    client_name: str = Field(min_length=2, max_length=200)
    brief: str = Field(min_length=20, max_length=20000)
    owner_id: str | None = None


class RequirementIn(BaseModel):
    action: str = Field(pattern="^(confirm|edit|mark_missing|not_applicable)$")
    value: str | None = Field(default=None, max_length=1000)
    reason: str | None = Field(default=None, max_length=1000)
    version: int | None = None


class QuestionIn(BaseModel):
    requirement_key: str | None = None
    question: str = Field(min_length=5, max_length=1000)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=2, max_length=4000)
    answered_source: str = Field(min_length=1, max_length=200)
    channel: str = Field(pattern="^(email|call|meeting|document|chat)$")
    reference: str = Field(min_length=3, max_length=300)
    client_excerpt: str | None = Field(default=None, max_length=8000)
    apply: bool = True
    apply_value: str | None = Field(default=None, max_length=1000)
    version: int | None = None


class PricingIn(BaseModel):
    scenario: str = Field(default="expected", pattern=SCENARIO_RE)
    inputs: dict
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    based_on_run_id: int | None = None
    check_base: bool = False


class PackageIn(BaseModel):
    exception_reason: str | None = Field(default=None, max_length=2000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT|REQUEST_CHANGES)$")
    note: str | None = Field(default=None, max_length=2000)
    package_hash: str
    version: int


class AuthorizeIn(BaseModel):
    package_hash: str
    confirmed_actions: list[str]
    note: str | None = Field(default=None, max_length=2000)


class RunIn(BaseModel):
    simulate: str = "none"


class ResolveIn(BaseModel):
    external_ref: str = Field(default="", max_length=120)
    note: str = Field(min_length=1, max_length=2000)


class EvalRunIn(BaseModel):
    dataset_id: int
    provider: str = Field(default="demo", pattern="^(demo|anthropic)$")


class AdjudicateIn(BaseModel):
    status: str = Field(pattern="^(confirmed_failure|ground_truth_issue|acceptable)$")
    note: str = Field(min_length=5, max_length=2000)


class RateCardIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    unit_cost_conservative_idr: int
    unit_cost_expected_idr: int
    unit_cost_aggressive_idr: int
    fixed_cost_idr: int
    margin_floor_bp: int
    capacity_leads_per_week: int
    notes: str | None = Field(default=None, max_length=1000)


class ConnectorIn(BaseModel):
    enabled: bool
    reason: str = Field(min_length=1, max_length=500)


# ---------- auth ----------
def _set_session(response: Response, token: str, csrf: str) -> None:
    s = get_settings()
    age = int(SESSION_TTL.total_seconds())
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=s.cookie_secure, max_age=age,
                        path="/")
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, samesite="lax", secure=s.cookie_secure, max_age=age,
                        path="/")


def _login(session: Session, response: Response, u: User, how: str) -> dict:
    token, csrf = create_session(session, u)
    from ..services import audit

    audit.record(session, u, "auth.login", "user", u.id, f"{u.name} signed in ({how}).")
    session.commit()
    _set_session(response, token, csrf)
    return {"user": S.user(u), "csrf_token": csrf}


@router.post("/auth/login")
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    u = session.scalar(select(User).where(User.username == body.username.strip().lower()))
    if u is None or not u.active or not verify_password(body.password, u.password_hash):
        raise DomainError(401, "INVALID_CREDENTIALS", "Username or password is incorrect.")
    return _login(session, response, u, "password")


@router.post("/auth/demo-login")
def demo_login(body: DemoLoginIn, response: Response, session: Session = Depends(get_session)):
    """One-click sign-in for the synthetic demo accounts. Disabled when DEMO_MODE=false."""
    if not get_settings().demo_mode:
        raise DomainError(404, "NOT_FOUND", "Demo sign-in is disabled.")
    u = session.scalar(select(User).where(User.username == body.username.strip().lower()))
    if u is None or not u.active:
        raise DomainError(401, "INVALID_CREDENTIALS", "Unknown demo account.")
    return _login(session, response, u, "demo account")


@router.post("/auth/logout")
def logout(request: Request, response: Response, session: Session = Depends(get_session), u: User = Depends(actor)):
    revoke(session, request.cookies.get(SESSION_COOKIE))
    session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, session: Session = Depends(get_session), u: User = Depends(actor)):
    from ..security import resolve_session

    s = resolve_session(session, request.cookies.get(SESSION_COOKIE))
    unread = session.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == u.id, Notification.read_at.is_(None))) or 0
    return {"user": S.user(u), "csrf_token": s.csrf_token, "unread_notifications": unread}


@router.get("/auth/demo-accounts")
def demo_accounts(session: Session = Depends(get_session)):
    if not get_settings().demo_mode:
        raise DomainError(404, "NOT_FOUND", "Demo accounts are not listed outside demo mode.")
    order = ["ANALYST", "APPROVER", "AUTOMATION_ENGINEER", "EVAL_ANALYST", "TRANSFORMATION_LEAD", "AUDITOR", "ADMIN"]
    users = sorted(session.scalars(select(User).where(User.active.is_(True))),
                   key=lambda u: (u.organization_id != "org_northstar", order.index(u.role) if u.role in order else 99, u.name))
    return [{"username": u.username, "name": u.name, "role": u.role, "role_label": ROLES.get(u.role, u.role),
             "title": u.title, "organization_id": u.organization_id} for u in users]


# ---------- meta ----------
@router.get("/health")
def health(session: Session = Depends(get_session)):
    s = get_settings()
    p = get_provider(s)
    seeded = session.get(AppMeta, "seeded_at")
    age = None
    if seeded:
        from datetime import datetime

        age = (utcnow() - datetime.fromisoformat(seeded.value)).days
    expired = [c.code for c in session.scalars(select(RateCard)) if feasibility.card_expired(c)]
    current_ok = any(not feasibility.card_expired(c) for c in session.scalars(select(RateCard)))
    return {"status": "ok", "ai_provider": s.ai_provider, "extractor": p.name, "extractor_label": p.label,
            "anthropic_configured": s.ai_provider == "anthropic", "synthetic_data": True, "demo_mode": s.demo_mode,
            "auth": "session cookie + CSRF (demo accounts available in demo mode)",
            "demo_data_age_days": age, "rate_card_valid": current_ok, "expired_rate_cards": expired,
            "worker": "background thread" if s.worker_enabled else "external (python -m app.worker)"}


@router.get("/users")
def list_users(session: Session = Depends(get_session), u: User = Depends(actor)):
    return [S.user(x) for x in session.scalars(select(User).where(User.organization_id == u.organization_id)
                                                .order_by(User.role, User.name))]


@router.get("/policy")
def policy(session: Session = Depends(get_session), u: User = Depends(actor)):
    card = feasibility.current_rate_card(session, u.organization_id)
    return {"thresholds": {"margin_floor_bp": card.margin_floor_bp, "capacity_leads_per_week": card.capacity_leads_per_week,
                           "dual_approval_when": "risk = HIGH (margin below floor or instruction-like text in brief)",
                           "max_write_attempts": 3, "session_hours": int(SESSION_TTL.total_seconds() // 3600),
                           "eval_gate": GATE},
            "rules": [
                {"id": "BR-001", "rule": "No approval while critical fields are missing/conflicting", "where": "packages, approvals"},
                {"id": "BR-002", "rule": "Prices use versioned rate cards and deterministic integer maths", "where": "pricing"},
                {"id": "BR-003", "rule": "Approval only applies to the same snapshot hash", "where": "approvals, execution"},
                {"id": "BR-004", "rule": "Changes after freezing invalidate the package", "where": "requirements, pricing"},
                {"id": "BR-005", "rule": "Writes need an allowlisted, enabled connector and authorization", "where": "execution"},
                {"id": "BR-006", "rule": "High risk needs two different approvers", "where": "approvals"},
                {"id": "BR-007", "rule": "Retries are idempotent; duplicates are replayed", "where": "sandbox, worker"},
                {"id": "BR-008", "rule": "Model output is a labelled draft until a human confirms it", "where": "requirements"},
                {"id": "BR-009", "rule": "Material claims need a source or an assumption label", "where": "extraction, packages"},
                {"id": "BR-012", "rule": "Executor never skips APPROVED", "where": "execution gate"},
                {"id": "BR-013", "rule": "Expired rate card forces repricing and re-review", "where": "approvals, execution"},
                {"id": "BR-014", "rule": "The AI cannot call URLs, SQL or the filesystem", "where": "AI provider has no tools"},
            ]}


# ---------- cases ----------
def _case_payload(session: Session, c, users) -> dict:
    docs = session.scalars(select(SourceDocument).where(SourceDocument.case_id == c.id).order_by(SourceDocument.id))
    pkg = cases.latest_package(session, c)
    run = cases.latest_run(session, pkg) if pkg else None
    artifacts = {a.id: a for a in session.scalars(select(Artifact).join(
        SourceDocument, SourceDocument.artifact_id == Artifact.id).where(SourceDocument.case_id == c.id))}
    return S.case_summary(c) | {
        "description": c.description, "extractor": c.extractor, "flags": c.flags, "action_hints": c.action_hints,
        "requirements": [S.requirement(r) for r in c.requirements],
        "documents": [S.document(d) | ({"artifact": {"id": d.artifact_id, "filename": artifacts[d.artifact_id].filename,
                                                     "mime": artifacts[d.artifact_id].mime,
                                                     "pages": artifacts[d.artifact_id].pages,
                                                     "sha256": artifacts[d.artifact_id].sha256}}
                                       if d.artifact_id in artifacts else {}) for d in docs],
        "latest_package": S.package_summary(pkg, users) if pkg else None,
        "latest_run": S.run_summary(run, users) if run else None,
        "lock_reason": cases.lock_reason(session, c), "reopen_count": c.reopen_count,
        "can_reopen": bool(pkg and (pkg.state == "REJECTED" or (run is not None and run.status == "CANCELLED"))),
    }


@router.get("/cases")
def list_cases(group: str | None = None, q: str | None = Query(default=None, max_length=100),
               limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
               session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity="cases")
    items, counts, total = cases.list_cases(session, u, group, q, limit, offset)
    return {"items": [S.case_summary(c) for c in items], "counts": counts, "total": total, "limit": limit,
            "offset": offset}


def _owner(session: Session, u: User, owner_id: str | None) -> User:
    owner = session.get(User, owner_id) if owner_id else u
    if owner is None or owner.role != "ANALYST" or owner.organization_id != u.organization_id:
        raise DomainError(422, "VALIDATION_ERROR", "Owner must be a Deal Desk Analyst in your organisation.",
                          {"field": "owner_id"})
    return owner


@router.post("/cases", status_code=201)
def create_case(body: CaseIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "case.create", entity="new case")
    owner = _owner(session, u, body.owner_id)
    provider = get_provider(get_settings())
    c = cases.create_case(session, u, title=body.title, client_name=body.client_name, brief=body.brief,
                          owner=owner, extraction=provider.extract(body.brief), provider_label=provider.label)
    session.commit()
    return S.case_summary(c)


@router.post("/cases/upload", status_code=201)
async def create_case_from_file(title: str = Form(min_length=3, max_length=200),
                                client_name: str = Form(min_length=2, max_length=200),
                                owner_id: str | None = Form(default=None), file: UploadFile = File(...),
                                session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "case.create", entity="new case")
    owner = _owner(session, u, owner_id)
    data = await file.read(intake.MAX_BYTES + 1)
    text, breaks, pages, mime = intake.parse(file.filename or "upload", data)
    art = Artifact(organization_id=u.organization_id, filename=(file.filename or "upload")[:255], mime=mime,
                   size=len(data), sha256=text_hash(data.decode("latin-1")), data=data, pages=pages, uploaded_by=u.id)
    session.add(art)
    session.flush()
    provider = get_provider(get_settings())
    c = cases.create_case(session, u, title=title, client_name=client_name, brief=text, owner=owner,
                          extraction=provider.extract(text), provider_label=provider.label, artifact=art,
                          page_breaks=breaks)
    session.commit()
    return S.case_summary(c)


@router.get("/artifacts/{artifact_id}")
def download_artifact(artifact_id: int, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity="artifact")
    a = session.get(Artifact, artifact_id)
    if a is None or a.organization_id != u.organization_id:
        raise DomainError(404, "NOT_FOUND", "File was not found.")
    return Response(a.data, media_type=a.mime, headers={
        "Content-Disposition": f'attachment; filename="{a.filename}"', "X-Content-Type-Options": "nosniff"})


@router.get("/cases/{code}")
def case_detail(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    return _case_payload(session, c, users_by_id(session))


@router.post("/cases/{code}/reopen")
def reopen(code: str, body: ReasonIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "case.reopen", c.id, code)
    cases.reopen(session, u, c, body.reason)
    session.commit()
    return _case_payload(session, c, users_by_id(session))


@router.post("/cases/{code}/extract")
def reextract(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "requirement.edit", c.id, code)
    provider = get_provider(get_settings())
    brief = session.scalar(select(SourceDocument).where(SourceDocument.case_id == c.id, SourceDocument.kind == "brief"))
    changed = requirements.reextract(session, u, c, provider.extract(brief.content))
    session.commit()
    return {"changed": changed, "extractor": c.extractor}


@router.patch("/cases/{code}/requirements/{key}")
def update_requirement(code: str, key: str, body: RequirementIn, session: Session = Depends(get_session),
                       u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "requirement.edit", c.id, f"{code}/{key}")
    r = requirements.update(session, u, c, key, body.action, body.value, body.reason, body.version)
    session.commit()
    return S.requirement(r)


@router.get("/cases/{code}/requirements/history")
def requirement_history(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    users = users_by_id(session)
    return [S.change(ch, users) for ch in requirements.history(session, c)]


@router.get("/cases/{code}/clarifications")
def list_clarifications(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    users = users_by_id(session)
    return [S.clarification(q, users) for q in requirements.list_clarifications(session, c)]


@router.post("/cases/{code}/clarifications", status_code=201)
def ask(code: str, body: QuestionIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "clarification.manage", c.id, code)
    q = requirements.ask(session, u, c, body.requirement_key, body.question)
    session.commit()
    return S.clarification(q, users_by_id(session))


@router.post("/cases/{code}/clarifications/suggest", status_code=201)
def suggest(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "clarification.manage", c.id, code)
    created = requirements.suggest(session, u, c)
    session.commit()
    users = users_by_id(session)
    return [S.clarification(q, users) for q in created]


@router.post("/cases/{code}/clarifications/{cid}/answer")
def answer(code: str, cid: int, body: AnswerIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "clarification.manage", c.id, code)
    q = requirements.answer(session, u, c, cid, body.answer, body.answered_source, body.apply_value, body.apply,
                            body.channel, body.reference, body.client_excerpt, body.version)
    session.commit()
    return S.clarification(q, users_by_id(session))


# ---------- feasibility ----------
@router.get("/cases/{code}/feasibility")
def get_feasibility(code: str, scenario: str = Query(default="expected", pattern=SCENARIO_RE),
                    session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    card = feasibility.current_rate_card(session, u.organization_id)
    latest = feasibility.latest_run(session, c)
    inputs = latest.inputs if latest and latest.scenario == scenario else feasibility.default_inputs(c, card, scenario)
    return {"rate_card": feasibility.rate_card_dict(card), "scenario": scenario,
            "scenarios": {k: {"label": v[0], "description": v[2]} for k, v in feasibility.SCENARIOS.items()},
            "inputs": inputs, "defaults": feasibility.default_inputs(c, card, scenario),
            "assessment": feasibility.assess(c, card, inputs),
            "latest_run": S.feasibility_run(latest, users_by_id(session)),
            "lock_reason": cases.lock_reason(session, c)}


@router.post("/cases/{code}/feasibility/preview")
def preview(code: str, body: PricingIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    return feasibility.assess(c, feasibility.current_rate_card(session, u.organization_id), body.inputs)


@router.post("/cases/{code}/feasibility", status_code=201)
def save_feasibility(code: str, body: PricingIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "feasibility.run", c.id, code)
    packages.assert_editable(session, c)
    run = feasibility.save_run(session, u, c, body.scenario, body.inputs, body.assumptions, body.based_on_run_id,
                               body.check_base)
    session.commit()
    return S.feasibility_run(run, users_by_id(session))


# ---------- packages & approvals ----------
@router.get("/cases/{code}/packages")
def list_packages(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    users = users_by_id(session)
    pkgs = session.scalars(select(DecisionPackage).where(DecisionPackage.case_id == c.id)
                           .order_by(DecisionPackage.version.desc()))
    return [S.package_summary(p, users) for p in pkgs]


@router.post("/cases/{code}/packages", status_code=201)
def create_package(code: str, body: PackageIn | None = None, session: Session = Depends(get_session),
                   u: User = Depends(actor)):
    c = cases.get_case(session, code, u)
    require(session, u, "package.create", c.id, code)
    pkg = packages.create_package(session, u, c, body.exception_reason if body else None)
    session.commit()
    return S.package_summary(pkg, users_by_id(session))


def _read_package(session: Session, u: User, package_id: int) -> DecisionPackage:
    if not (can(u.role, "approvals.read") or can(u.role, "cases.read")):
        require(session, u, "approvals.read", entity=f"package {package_id}")
    return packages.get_package(session, package_id, u)


@router.get("/packages/{package_id}")
def package_detail(package_id: int, session: Session = Depends(get_session), u: User = Depends(actor)):
    pkg = _read_package(session, u, package_id)
    users = users_by_id(session)
    prev = session.get(DecisionPackage, pkg.previous_id) if pkg.previous_id else None
    latest = cases.latest_package(session, pkg.case)
    auth = session.scalar(select(ExecutionAuthorization).where(ExecutionAuthorization.package_id == pkg.id))
    runs = session.scalars(select(WorkflowRun).where(WorkflowRun.package_id == pkg.id).order_by(WorkflowRun.id))
    blockers = packages.validate_for_approval(pkg.content)
    card = feasibility.card_by_code(session, pkg.case.organization_id, pkg.content["pricing"]["rate_card"])
    disabled = [c.name for c in connectors.for_org(session, pkg.case.organization_id) if not c.enabled
                and set(c.actions) & {a["action"] for a in pkg.content["proposed_actions"]}]
    return S.package_summary(pkg, users) | {
        "content": pkg.content, "is_current": latest is not None and latest.id == pkg.id,
        "previous": S.package_summary(prev, users) if prev else None,
        "diff": packages.diff(prev.content if prev else None, pkg.content),
        "approvals": [S.approval(a, users) for a in approvals.records(session, pkg)],
        "previous_reviews": [S.approval(a, users) for a in approvals.records(session, prev)] if prev else [],
        "approvals_count": len(approvals.approvals_for(session, pkg)),
        "authorization": S.authorization(auth, users),
        "runs": [S.run_summary(r, users) for r in runs],
        "approval_blockers": blockers,
        "rate_card_expired": card is None or feasibility.card_expired(card),
        "disabled_connectors": disabled,
        "case_status": pkg.case.status,
    }


@router.get("/packages/{package_id}/export.md", response_class=PlainTextResponse)
def package_export_md(package_id: int, session: Session = Depends(get_session), u: User = Depends(actor)):
    pkg = _read_package(session, u, package_id)
    names = {x.id: x.name for x in users_by_id(session).values()}
    md = exports.package_markdown(pkg, approvals.records(session, pkg), names)
    return PlainTextResponse(md, media_type="text/markdown", headers={
        "Content-Disposition": f'attachment; filename="{pkg.case.code}-package-v{pkg.version}.md"'})


@router.get("/packages/{package_id}/export.json")
def package_export_json(package_id: int, session: Session = Depends(get_session), u: User = Depends(actor)):
    pkg = _read_package(session, u, package_id)
    users = users_by_id(session)
    body = {"package_id": pkg.id, "version": pkg.version, "state": pkg.state, "content_hash": pkg.content_hash,
            "content": pkg.content, "approvals": [S.approval(a, users) for a in approvals.records(session, pkg)],
            "synthetic": True}
    return Response(json.dumps(body, indent=2, ensure_ascii=False), media_type="application/json", headers={
        "Content-Disposition": f'attachment; filename="{pkg.case.code}-package-v{pkg.version}.json"'})


@router.get("/approvals")
def approval_inbox(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "approvals.read", entity="approvals")
    users = users_by_id(session)
    org = select(DecisionPackage).join(DecisionPackage.case).where(
        DecisionPackage.case.property.mapper.class_.organization_id == u.organization_id)
    pending = session.scalars(org.where(DecisionPackage.state == "IN_REVIEW").order_by(DecisionPackage.created_at))
    approved = session.scalars(org.where(DecisionPackage.state == "APPROVED"))
    to_authorize = [p for p in approved if not session.scalar(
        select(ExecutionAuthorization.id).where(ExecutionAuthorization.package_id == p.id))]
    recent = session.scalars(org.where(DecisionPackage.state.in_(("APPROVED", "REJECTED", "CHANGES_REQUESTED")))
                             .order_by(DecisionPackage.id.desc()).limit(10))
    pend = []
    for p in pending:
        mine = any(a.actor_id == u.id for a in approvals.approvals_for(session, p))
        pend.append(S.package_summary(p, users) | {"approvals_count": len(approvals.approvals_for(session, p)),
                                                   "approved_by_me": mine})
    return {"pending": pend,
            "awaiting_authorization": [S.package_summary(p, users) for p in to_authorize],
            "recent": [S.package_summary(p, users) for p in recent]}


@router.post("/packages/{package_id}/review")
def review(package_id: int, body: ReviewIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    pkg = packages.get_package(session, package_id, u)
    rec = approvals.review(session, u, pkg, body.decision, body.note, body.package_hash, body.version)
    session.commit()
    return S.approval(rec, users_by_id(session)) | {"package_state": pkg.state}


@router.post("/packages/{package_id}/authorize")
def authorize(package_id: int, body: AuthorizeIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    pkg = packages.get_package(session, package_id, u)
    auth = approvals.authorize(session, u, pkg, body.package_hash, body.confirmed_actions, body.note)
    session.commit()
    return S.authorization(auth, users_by_id(session))


# ---------- workflow runs & incidents ----------
def _run_payload(session: Session, run: WorkflowRun, users) -> dict:
    pkg = session.get(DecisionPackage, run.package_id)
    events = session.scalars(select(AuditEvent).where(AuditEvent.case_id == run.case_id,
                                                      AuditEvent.entity_id.in_((run.code, str(pkg.id))))
                             .order_by(AuditEvent.id))
    inc = session.scalar(select(Incident).where(Incident.run_id == run.id).order_by(Incident.id.desc()))
    return S.run_detail(run, users) | {
        "case": {"code": pkg.case.code, "title": pkg.case.title, "client_name": pkg.case.client_name},
        "package": {"id": pkg.id, "version": pkg.version, "state": pkg.state, "content_hash": pkg.content_hash},
        "simulation_label": SIMULATIONS.get(run.simulate),
        "events": [S.audit_event(e, users) for e in events],
        "incident": S.incident(inc, users, run.code, pkg.case.code) if inc else None,
    }


@router.get("/runs")
def list_runs(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "workflows.read", entity="runs")
    users = users_by_id(session)
    out = []
    for r in session.scalars(select(WorkflowRun).order_by(WorkflowRun.id.desc())):
        pkg = session.get(DecisionPackage, r.package_id)
        if pkg.case.organization_id != u.organization_id:
            continue
        out.append(S.run_summary(r, users) | {"case": {"code": pkg.case.code, "title": pkg.case.title,
                                                       "client_name": pkg.case.client_name},
                                              "package_version": pkg.version})
    ready = []
    for auth in session.scalars(select(ExecutionAuthorization).order_by(ExecutionAuthorization.id.desc())):
        pkg = session.get(DecisionPackage, auth.package_id)
        has_run = session.scalar(select(WorkflowRun.id).where(WorkflowRun.package_id == pkg.id))
        if pkg.case.organization_id == u.organization_id and pkg.state == "APPROVED" and not has_run:
            ready.append(S.package_summary(pkg, users))
    incs = []
    for i in execution.incidents(session, u):
        run = session.get(WorkflowRun, i.run_id) if i.run_id else None
        case = session.get(DecisionPackage, run.package_id).case if run else None
        incs.append(S.incident(i, users, run.code if run else None, case.code if case else None))
    return {"items": out, "ready": ready, "incidents": incs, "simulations": SIMULATIONS}


@router.post("/packages/{package_id}/runs", status_code=202)
def start_run(package_id: int, body: RunIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    pkg = packages.get_package(session, package_id, u)
    run = execution.start(session, u, pkg, body.simulate)
    session.commit()
    return _run_payload(session, run, users_by_id(session))


@router.get("/runs/{code}")
def run_detail(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "workflows.read", entity=code)
    run = execution.get_run(session, code, u)
    return _run_payload(session, run, users_by_id(session))


@router.get("/runs/{code}/log.json")
def run_log(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "workflows.read", entity=code)
    run = execution.get_run(session, code, u)
    body = _run_payload(session, run, users_by_id(session)) | {"exported_at": S.iso(utcnow()), "synthetic": True}
    return Response(json.dumps(body, indent=2, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{run.code}-log.json"'})


def _run_action(code: str, session: Session, u: User, fn, *args):
    run = execution.get_run(session, code, u)
    fn(session, u, run, *args)
    session.commit()
    return _run_payload(session, run, users_by_id(session))


@router.post("/runs/{code}/steps/{key}/retry")
def retry(code: str, key: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    return _run_action(code, session, u, execution.retry, key)


@router.post("/runs/{code}/steps/{key}/reconcile")
def reconcile(code: str, key: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    return _run_action(code, session, u, execution.reconcile, key)


@router.post("/runs/{code}/steps/{key}/resolve")
def resolve_step(code: str, key: str, body: ResolveIn, session: Session = Depends(get_session),
                 u: User = Depends(actor)):
    return _run_action(code, session, u, execution.resolve_manually, key, body.external_ref, body.note)


@router.post("/runs/{code}/escalate")
def escalate(code: str, body: ReasonIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    return _run_action(code, session, u, execution.escalate, body.reason)


@router.post("/runs/{code}/cancel")
def cancel(code: str, body: ReasonIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    return _run_action(code, session, u, execution.cancel, body.reason)


@router.post("/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int, body: ReasonIn, session: Session = Depends(get_session),
                     u: User = Depends(actor)):
    inc = execution.resolve_incident(session, u, incident_id, body.reason)
    session.commit()
    return S.incident(inc, users_by_id(session))


# ---------- audit & notifications ----------
@router.get("/cases/{code}/audit")
def case_audit(code: str, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "cases.read", entity=code)
    c = cases.get_case(session, code, u)
    users = users_by_id(session)
    events = session.scalars(select(AuditEvent).where(AuditEvent.case_id == c.id).order_by(AuditEvent.id.desc()))
    return [S.audit_event(e, users) for e in events]


@router.get("/audit")
def global_audit(verb: str | None = Query(default=None, max_length=60), actor_id: str | None = None,
                 limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                 session: Session = Depends(get_session), u: User = Depends(actor)):
    rows, total = admin.global_audit(session, u, verb, actor_id, limit, offset)
    users = users_by_id(session)
    return {"items": [S.audit_event(e, users) | {"request_id": e.request_id} for e in rows], "total": total}


@router.get("/notifications")
def list_notifications(session: Session = Depends(get_session), u: User = Depends(actor)):
    items = notifications.for_user(session, u)
    return {"items": [S.notification(n) for n in items], "unread": sum(1 for n in items if n.read_at is None)}


@router.post("/notifications/read")
def read_notifications(notification_id: int | None = None, session: Session = Depends(get_session),
                       u: User = Depends(actor)):
    notifications.mark_read(session, u, notification_id)
    session.commit()
    return {"ok": True}


# ---------- evaluation ----------
@router.get("/evaluations/datasets")
def datasets(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "eval.read", entity="evaluation")
    out = []
    for d in session.scalars(select(EvalDataset)):
        counts = dict(session.execute(select(EvalCase.split, func.count()).where(EvalCase.dataset_id == d.id)
                                      .group_by(EvalCase.split)).all())
        out.append({"id": d.id, "slug": d.slug, "name": d.name, "version": d.version, "description": d.description,
                    "manifest_hash": d.manifest_hash, "synthetic": d.synthetic, "cases": sum(counts.values()),
                    "splits": counts})
    return {"datasets": out, "providers": {"demo": True, "anthropic": get_settings().ai_provider == "anthropic"},
            "gate": GATE}


@router.get("/evaluations/runs")
def eval_runs(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "eval.read", entity="evaluation")
    users = users_by_id(session)
    return [{"id": r.id, "dataset_id": r.dataset_id, "extractor_version": r.extractor_version, "provider": r.provider,
             "status": r.status, "summary": r.summary, "started_by": S.user(users.get(r.started_by)),
             "started_at": S.iso(r.started_at), "duration_ms": r.duration_ms}
            for r in session.scalars(select(EvalRun).order_by(EvalRun.id.desc()))]


@router.post("/evaluations/runs", status_code=201)
def start_eval(body: EvalRunIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "eval.run", entity="evaluation run")
    ds = session.get(EvalDataset, body.dataset_id)
    if ds is None:
        raise DomainError(404, "NOT_FOUND", "Dataset was not found.")
    provider = None
    if body.provider == "anthropic":
        s = get_settings()
        if s.ai_provider != "anthropic":
            raise DomainError(409, "PROVIDER_NOT_CONFIGURED", "Set AI_PROVIDER=anthropic and ANTHROPIC_API_KEY on the "
                              "server to evaluate the Claude provider.")
        provider = AnthropicProvider(s)
    ev = runner.run(session, u, ds, provider)
    session.commit()
    return {"id": ev.id, "summary": ev.summary}


@router.get("/evaluations/runs/{run_id}")
def eval_run_detail(run_id: int, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "eval.read", entity="evaluation")
    ev = session.get(EvalRun, run_id)
    if ev is None:
        raise DomainError(404, "NOT_FOUND", "Evaluation run was not found.")
    users = users_by_id(session)
    ds = session.get(EvalDataset, ev.dataset_id)
    results = session.scalars(select(EvalResult).where(EvalResult.run_id == ev.id).order_by(EvalResult.id))
    prev = session.scalar(select(EvalRun).where(EvalRun.dataset_id == ev.dataset_id, EvalRun.id < ev.id)
                          .order_by(EvalRun.id.desc()).limit(1))
    return {"id": ev.id, "status": ev.status, "summary": ev.summary, "extractor_version": ev.extractor_version,
            "provider": ev.provider, "started_at": S.iso(ev.started_at), "duration_ms": ev.duration_ms,
            "started_by": S.user(users.get(ev.started_by)),
            "previous": {"id": prev.id, "summary": prev.summary} if prev else None,
            "dataset": {"id": ds.id, "name": ds.name, "version": ds.version, "manifest_hash": ds.manifest_hash},
            "categories": CATEGORIES, "adjudications": ADJUDICATIONS,
            "results": [{"id": r.id, "code": r.eval_case.code, "split": r.eval_case.split,
                         "category": r.eval_case.category, "outcome": r.outcome,
                         "failure_categories": r.failure_categories, "checks": r.checks, "actual": r.actual,
                         "brief": r.eval_case.brief, "expected": r.eval_case.expected,
                         "adjudication": r.adjudication, "adjudication_note": r.adjudication_note,
                         "adjudicated_by": S.user(users.get(r.adjudicated_by)) if r.adjudicated_by else None}
                        for r in results]}


@router.post("/evaluations/results/{result_id}/adjudicate")
def adjudicate(result_id: int, body: AdjudicateIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "eval.adjudicate", entity=f"eval result {result_id}")
    r = session.get(EvalResult, result_id)
    if r is None:
        raise DomainError(404, "NOT_FOUND", "Result was not found.")
    r.adjudication, r.adjudication_note, r.adjudicated_by, r.adjudicated_at = body.status, body.note.strip(), u.id, utcnow()
    from ..services import audit

    audit.record(session, u, "eval.adjudicated", "eval_result", r.id,
                 f"{u.name} adjudicated {r.eval_case.code}: {ADJUDICATIONS[body.status]} — {body.note.strip()}")
    session.commit()
    return {"ok": True}


# ---------- impact ----------
@router.get("/impact/summary")
def impact_summary(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "impact.read", entity="impact")
    return {"cohort": impact.summary(session), "live": impact.live(session, u.organization_id)}


@router.get("/impact/export.csv")
def impact_export(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "impact.read", entity="impact export")
    rows = list(session.scalars(select(ImpactCohortCase).order_by(ImpactCohortCase.code)))
    return Response(exports.cohort_csv(rows), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="impact-cohort-synthetic.csv"'})


# ---------- admin ----------
@router.get("/admin/rate-cards")
def admin_rate_cards(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "manage.rate_cards", entity="rate cards")
    return [feasibility.rate_card_dict(c) for c in admin.rate_cards(session, u)]


@router.post("/admin/rate-cards", status_code=201)
def admin_create_rate_card(body: RateCardIn, session: Session = Depends(get_session), u: User = Depends(actor)):
    card = admin.create_rate_card(session, u, body.model_dump())
    session.commit()
    return feasibility.rate_card_dict(card)


@router.get("/admin/connectors")
def admin_connectors(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "manage.integrations", entity="connectors")
    users = users_by_id(session)
    return [{"key": c.key, "name": c.name, "actions": c.actions, "risk_class": c.risk_class,
             "supports_idempotency": c.supports_idempotency, "supports_read_after_write": c.supports_read_after_write,
             "sandbox": c.sandbox, "enabled": c.enabled, "updated_at": S.iso(c.updated_at),
             "updated_by": S.user(users.get(c.updated_by)) if c.updated_by else None}
            for c in connectors.for_org(session, u.organization_id)]


@router.patch("/admin/connectors/{key}")
def admin_set_connector(key: str, body: ConnectorIn, session: Session = Depends(get_session),
                        u: User = Depends(actor)):
    c = admin.set_connector(session, u, key, body.enabled, body.reason)
    session.commit()
    return {"key": c.key, "enabled": c.enabled}


@router.get("/admin/users")
def admin_users(session: Session = Depends(get_session), u: User = Depends(actor)):
    require(session, u, "users.read", entity="users")
    return [S.user(x) | {"active": x.active} for x in session.scalars(
        select(User).where(User.organization_id == u.organization_id).order_by(User.role, User.name))]
