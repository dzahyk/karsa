import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, Lock, RotateCcw } from "lucide-react";
import { Fragment, useState } from "react";
import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { api, can } from "../api";
import { Callout, Dialog, ErrorMessage, ErrorState, Field, LoadingRows, StatusBadge, SyntheticTag, useToast } from "../components/ui";
import { useSession } from "../session";
import { dateTime } from "../format";
import type { CaseDetail } from "../types";

export type CaseCtx = { c: CaseDetail; refetch: () => void };
export const useCase = () => useOutletContext<CaseCtx>();
export const caseKey = (code: string) => ["case", code];

const LATER = ["AWAITING_APPROVAL", "CHANGES_REQUESTED", "REJECTED", "APPROVED", "AUTHORIZED", "EXECUTING", "EXECUTION_ATTENTION", "COMPLETED"];
const DECIDED = ["APPROVED", "AUTHORIZED", "EXECUTING", "EXECUTION_ATTENTION", "COMPLETED"];

function steps(c: CaseDetail) {
  const reqDone = c.requirements.every((r) => !r.critical || r.state === "CONFIRMED");
  const reqBlocked = c.requirements.some((r) => r.critical && (r.state === "MISSING" || r.state === "CONFLICTING"));
  const pkg = c.latest_package && c.latest_package.state !== "SUPERSEDED" ? c.latest_package : null;
  return [
    { key: "intake", label: "Intake", to: "requirements", state: "done" },
    { key: "requirements", label: "Requirements", to: "requirements", state: reqDone ? "done" : reqBlocked ? "blocked" : "todo" },
    { key: "feasibility", label: "Feasibility", to: "feasibility", state: pkg || LATER.includes(c.status) ? "done" : "todo" },
    { key: "package", label: "Decision package", to: "package", state: pkg ? "done" : "todo" },
    { key: "approval", label: "Approval", to: pkg ? `/approvals/${pkg.id}` : "package",
      state: DECIDED.includes(c.status) ? "done" : ["REJECTED", "CHANGES_REQUESTED"].includes(c.status) ? "blocked" : "todo" },
    { key: "execution", label: "Execution", to: c.latest_run ? `/workflows/${c.latest_run.code}` : "package",
      state: c.status === "COMPLETED" ? "done" : c.status === "EXECUTION_ATTENTION" ? "blocked" : "todo" },
  ];
}

export function CaseLayout() {
  const { code = "" } = useParams();
  const q = useQuery({ queryKey: caseKey(code), queryFn: () => api.get<CaseDetail>(`/cases/${code}`) });
  if (q.isLoading) return <div className="page"><LoadingRows rows={6} label="Loading case" /></div>;
  if (q.error || !q.data) return <div className="page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  const c = q.data;
  const st = steps(c);
  const currentIdx = Math.max(0, st.findIndex((s) => s.state !== "done"));
  return (
    <div className="page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/cases">Cases</Link><ChevronRight size={14} aria-hidden="true" /><span aria-current="page" className="mono">{c.code}</span>
      </nav>
      <div className="case-head">
        <div>
          <div className="row wrap" style={{ gap: 12 }}>
            <h1 className="page-title">{c.client_name} — {c.title}</h1>
            <StatusBadge status={c.status} />
          </div>
          <div className="case-meta">
            <span className="mono">{c.code}</span><span className="sep" />
            <span>Owner: {c.owner.name}</span><span className="sep" />
            <span>Next: <strong style={{ color: "var(--ink)" }}>{c.next_action}</strong></span><span className="sep" />
            <span>Updated {dateTime(c.updated_at)}</span><span className="sep" />
            <SyntheticTag />
          </div>
        </div>
      </div>
      <nav className="stepper" aria-label="Case progress">
        {st.map((s, i) => (
          <Fragment key={s.key}>
            {i > 0 && <span className={`step-line ${st[i - 1].state === "done" ? "done" : ""}`} aria-hidden="true" />}
            <Link to={s.to} className={`step ${s.state === "done" ? "done" : ""} ${s.state === "blocked" ? "blocked" : ""} ${i === currentIdx ? "current" : ""}`}
              aria-current={i === currentIdx ? "step" : undefined}>
              <span className="dot" aria-hidden="true">{s.state === "done" ? <Check size={14} /> : i + 1}</span>
              {s.label}
              <span className="sr-only">{s.state === "done" ? "(complete)" : s.state === "blocked" ? "(blocked)" : "(not started)"}</span>
            </Link>
          </Fragment>
        ))}
      </nav>
      <nav className="row wrap" aria-label="Case sections" style={{ gap: 6, marginBottom: 20, borderBottom: "1px solid var(--hairline)" }}>
        {[["requirements", "Requirements & evidence"], ["feasibility", "Feasibility & pricing"], ["package", "Decision package"], ["activity", "Activity & audit"]].map(([to, label]) => (
          <NavLink key={to} to={to} className={({ isActive }) => `btn btn-ghost ${isActive ? "active-tab" : ""}`}
            style={({ isActive }) => ({ borderRadius: 0, borderBottom: `2px solid ${isActive ? "var(--brand)" : "transparent"}`, color: isActive ? "var(--ink)" : undefined, marginBottom: -1 })}>
            {label}
          </NavLink>
        ))}
      </nav>
      {c.lock_reason && (
        <div style={{ marginBottom: 16 }}>
          <Callout tone={c.can_reopen ? "warning" : "info"} icon={<Lock size={18} aria-hidden="true" />} title="Locked.">
            {c.lock_reason} <ReopenButton c={c} />
          </Callout>
        </div>
      )}
      <Outlet context={{ c, refetch: q.refetch } satisfies CaseCtx} />
    </div>
  );
}

function ReopenButton({ c }: { c: CaseDetail }) {
  const { user } = useSession();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post(`/cases/${c.code}/reopen`, { reason }),
    onSuccess: () => { qc.invalidateQueries(); toast(`${c.code} reopened. Revise it and create a new package version.`); setOpen(false); },
  });
  if (!c.can_reopen || !can(user, "case.reopen")) return null;
  return (
    <>
      <button className="btn btn-outline btn-sm" style={{ marginLeft: 8 }} onClick={() => setOpen(true)}><RotateCcw size={14} aria-hidden="true" />Reopen case</button>
      <Dialog open={open} onClose={() => setOpen(false)} title={`Reopen ${c.code}?`}
        footer={<><button className="btn btn-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="btn btn-primary" form="reopen" disabled={m.isPending || reason.trim().length < 5}>Reopen</button></>}>
        <form id="reopen" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <p className="small">The current package is marked superseded. Its approval and audit history stay untouched; a new version will need a new review.</p>
          <Field label="Why is the case reopened?">{({ id }) => <textarea id={id} className="textarea" style={{ minHeight: 70 }} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
          {m.error ? <ErrorMessage error={m.error} /> : null}
        </form>
      </Dialog>
    </>
  );
}
