"""Role → permission map, enforced on the server for reads and writes (spec §3.9, §4.4)."""

from __future__ import annotations

ROLES = {
    "ANALYST": "Deal Desk Analyst",
    "APPROVER": "Commercial Manager (Approver)",
    "AUTOMATION_ENGINEER": "Automation Engineer",
    "EVAL_ANALYST": "AI Evaluation Analyst",
    "TRANSFORMATION_LEAD": "Transformation Lead",
    "AUDITOR": "Auditor (read-only)",
    "ADMIN": "Workspace Admin",
}

PERMISSIONS: dict[str, set[str]] = {
    "ANALYST": {
        "cases.read", "approvals.read", "workflows.read",
        "case.create", "requirement.edit", "clarification.manage", "feasibility.run", "package.create",
        "case.reopen", "workflow.run",
    },
    "APPROVER": {"cases.read", "approvals.read", "workflows.read", "impact.read", "package.review",
                 "execution.authorize"},
    "AUTOMATION_ENGINEER": {"cases.read", "workflows.read", "workflow.run", "workflow.recover", "incident.manage"},
    "EVAL_ANALYST": {"eval.read", "eval.run", "eval.adjudicate"},
    "TRANSFORMATION_LEAD": {"cases.read", "impact.read"},
    "AUDITOR": {"cases.read", "approvals.read", "workflows.read", "eval.read", "impact.read", "audit.read"},
    "ADMIN": {"audit.read", "manage.rate_cards", "manage.integrations", "users.read"},
}

# Navigation modules and the read permission each needs (the UI hides what the server would refuse).
MODULES = {
    "cases": "cases.read", "approvals": "approvals.read", "workflows": "workflows.read",
    "evaluation": "eval.read", "impact": "impact.read", "manage": "users.read", "audit": "audit.read",
}


def can(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def modules(role: str) -> list[str]:
    return [m for m, p in MODULES.items() if can(role, p)]
