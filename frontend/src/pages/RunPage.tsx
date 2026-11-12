import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Ban, Check, ChevronRight, Download, HelpCircle, Loader2, Pause, Play, RefreshCw, Search, ShieldCheck, Siren, Wrench, X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, can } from "../api";
import { Callout, Dialog, ErrorMessage, ErrorState, Field, LoadingRows, Panel, StatusBadge, useToast } from "../components/ui";
import { dateTime, shortHash } from "../format";
import { useSession } from "../session";
import type { RunDetail, RunStep } from "../types";
import { AuditTable } from "./ActivityPage";

const DOT: Record<string, [string, typeof Check]> = {
  SUCCEEDED: ["ok", Check], FAILED: ["fail", X], UNKNOWN_OUTCOME: ["unknown", HelpCircle], RUNNING: ["run", Loader2], CANCELLED: ["", Ban],
};
const ACTIVE = ["QUEUED", "RUNNING"];

function seconds(a: string | null, b: string | null) {
  if (!a || !b) return null;
  return `${Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000))}s`;
}

export function RunPage() {
  const { runCode = "" } = useParams();
  const [live, setLive] = useState(true);
  const q = useQuery({
    queryKey: ["run", runCode], queryFn: () => api.get<RunDetail>(`/runs/${runCode}`),
    refetchInterval: (query) => (live && ACTIVE.includes(query.state.data?.status ?? "") ? 1000 : false),
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [announce, setAnnounce] = useState("");
  const prev = useRef<string | undefined>(undefined);
  useEffect(() => {
    const st = q.data?.status;
    if (prev.current && ACTIVE.includes(prev.current) && st && !ACTIVE.includes(st)) setAnnounce(`Run ${runCode} finished: ${st.replace("_", " ").toLowerCase()}.`);
    prev.current = st;
  }, [q.data?.status, runCode]);
  if (q.isLoading) return <div className="page"><LoadingRows rows={8} label="Loading run" /></div>;
  if (q.error || !q.data) return <div className="page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  const r = q.data;
  const firstProblem = r.steps.find((s) => !["SUCCEEDED", "PENDING", "BLOCKED"].includes(s.status));
  const step = r.steps.find((s) => s.key === selected) ?? firstProblem ?? r.steps[r.steps.length - 1];
  const ok = r.status === "SUCCEEDED";
  const active = ACTIVE.includes(r.status);
  return (
    <div className="page">
      <div className="sr-only" aria-live="polite">{announce}</div>
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/workflows">Workflows</Link><ChevronRight size={14} aria-hidden="true" />
        <Link to={`/cases/${r.case.code}`} className="mono">{r.case.code}</Link><ChevronRight size={14} aria-hidden="true" />
        <span className="mono" aria-current="page">{r.code}</span>
      </nav>
      <div className="page-head">
        <div>
          <div className="row wrap" style={{ gap: 12 }}>
            <h1 className="page-title"><span className="mono">{r.code}</span> · Execution status</h1>
            <span className="badge brand">Sandbox</span>
          </div>
          <p className="page-sub">{r.case.client_name} — {r.case.title} · approved package v{r.package.version} <span className="hash">({shortHash(r.package_hash)}…)</span> · queued {dateTime(r.started_at)} by {r.started_by.name}</p>
          {r.simulate !== "none" && <p className="small" style={{ marginTop: 6, color: "var(--copper)" }}>Failure injection (demo): {r.simulation_label}</p>}
          <div className="row wrap" style={{ marginTop: 8 }}>
            <a className="btn btn-ghost btn-sm" href={`/api/v1/runs/${r.code}/log.json`} download><Download size={14} aria-hidden="true" />Download run log</a>
            {active && (
              <button className="btn btn-ghost btn-sm" onClick={() => setLive(!live)} aria-pressed={!live}>
                {live ? <><Pause size={14} aria-hidden="true" />Pause live updates</> : <><Play size={14} aria-hidden="true" />Resume live updates</>}
              </button>)}
          </div>
        </div>
        <div className={`callout ${ok ? "success" : active ? "info" : r.status === "CANCELLED" ? "warning" : r.status === "UNKNOWN_OUTCOME" ? "warning" : "critical"}`} style={{ minWidth: 260 }}>
          {ok ? <ShieldCheck size={20} aria-hidden="true" /> : active ? <Loader2 size={20} className="spin" aria-hidden="true" /> : <AlertTriangle size={20} aria-hidden="true" />}
          <div><strong>{ok ? "Verified" : active ? (r.status === "QUEUED" ? "Queued" : "Running") : r.status === "CANCELLED" ? "Cancelled" : "Not completed"}</strong>
            <div className="small">{ok ? "Every write was read back from the sandbox with the approved hash." : active ? "The outbox worker is processing this run." :
              r.status === "CANCELLED" ? r.cancelled_reason : r.status === "UNKNOWN_OUTCOME" ? "Outcome unknown — reconciliation required." : "Execution stopped — action required."}</div></div>
        </div>
      </div>

      {r.incident && <IncidentPanel r={r} />}

      <div className="grid-2" style={{ gridTemplateColumns: "minmax(280px, 0.8fr) minmax(0, 1.6fr)" }}>
        <Panel title="Execution timeline" subtitle={`${r.steps.length} steps · ${r.steps_done} succeeded`}>
          <ol className="timeline" aria-label="Steps">
            {r.steps.map((s, i) => {
              const [cls, Icon] = DOT[s.status] ?? ["", () => <span>{i + 1}</span>];
              return (
                <li key={s.key} className={s.status === "SUCCEEDED" ? "ok" : ""}>
                  <span className={`tl-dot ${cls}`}><Icon size={15} aria-hidden="true" className={s.status === "RUNNING" ? "spin" : undefined} /></span>
                  <button className={`step-card ${cls === "fail" ? "fail" : cls === "unknown" ? "unknown" : ""}`} aria-current={step.key === s.key} onClick={() => setSelected(s.key)}>
                    <div className="row between"><strong>{s.label}</strong>{seconds(s.started_at, s.finished_at) && <span className="badge neutral mono">{seconds(s.started_at, s.finished_at)}</span>}</div>
                    <div className="small muted">{s.status === "BLOCKED" ? "Waiting on an earlier step" : s.status.replace("_", " ").toLowerCase()}{s.finished_at && ` · ${dateTime(s.finished_at)}`}</div>
                  </button>
                </li>);
            })}
          </ol>
          <button className="btn btn-ghost btn-sm" onClick={() => q.refetch()}><RefreshCw size={14} aria-hidden="true" />Refresh</button>
        </Panel>
        <StepDetail r={r} s={step} />
      </div>
      <div style={{ marginTop: 20 }}>
        <Panel title="Audit log" subtitle="Key execution events for this workflow." flush><AuditTable events={[...r.events].reverse()} /></Panel>
      </div>
    </div>
  );
}

type Act = { kind: "retry" | "reconcile" | "resolve" | "escalate" | "cancel"; label: string };

function useRunAction(r: RunDetail) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api.post<RunDetail>(`/runs/${r.code}/${path}`, body),
    onSuccess: (d) => {
      qc.setQueryData(["run", r.code], d);
      qc.invalidateQueries();
      toast(ACTIVE.includes(d.status) ? "Queued — the worker is processing it." : `Run is now ${d.status.replace("_", " ").toLowerCase()}.`);
    },
  });
}

function StepDetail({ r, s }: { r: RunDetail; s: RunStep }) {
  const { user } = useSession();
  const act = useRunAction(r);
  const [dialog, setDialog] = useState<Act | null>(null);
  const recover = can(user, "workflow.recover");
  const manage = can(user, "incident.manage");
  const closed = ["SUCCEEDED", "CANCELLED"].includes(r.status);
  const busy = ACTIVE.includes(r.status) || act.isPending;
  return (
    <Panel title={s.label} subtitle={`Execution step · ${s.target}`} actions={<StatusBadge status={s.status} />}>
      <div className="stack">
        {s.status === "FAILED" && <Callout tone="critical" title="Step failed.">{s.last_error}</Callout>}
        {s.status === "UNKNOWN_OUTCOME" && <Callout tone="warning" title="Outcome unknown.">{s.last_error} Blind retry is disabled — check the target system first.</Callout>}
        {(s.status === "BLOCKED" || s.status === "CANCELLED") && <Callout tone="info">{s.last_error}</Callout>}
        <div className="grid-2 even" style={{ gap: 20 }}>
          <div>
            <div className="section-title">Technical details</div>
            <dl className="kv">
              <dt>Target</dt><dd>{s.target}</dd>
              <dt>Attempts</dt><dd>{s.attempts} of {s.max_attempts}</dd>
              <dt>Idempotency</dt><dd>{s.idempotency_key ? <><ShieldCheck size={14} color="var(--success)" aria-hidden="true" style={{ verticalAlign: -2 }} /> <span className="mono xs">{s.idempotency_key}</span></> : "Not a write step"}</dd>
              <dt>External ref</dt><dd className="mono">{s.external_ref ?? "—"}</dd>
              <dt>Finished</dt><dd>{dateTime(s.finished_at)}</dd>
            </dl>
          </div>
          <div>
            <div className="section-title">Recovery</div>
            {closed ? <p className="small muted">This run is {r.status.toLowerCase()}; no further action.</p> : (
              <div className="stack tight">
                {s.can_reconcile && <>
                  <p className="small">Read the target by idempotency key. If the record exists it is linked without a second write; if not, a retry becomes safe.</p>
                  <button className="btn btn-primary" disabled={!recover || busy} onClick={() => act.mutate({ path: `steps/${s.key}/reconcile` })}><Search size={16} aria-hidden="true" />Check target system</button>
                  <span className="xs muted">Blind retry is disabled while the outcome is unknown.</span>
                </>}
                {s.can_retry && <>
                  <p className="small">Nothing was created on the last attempt, so retrying with the same key is safe. Attempt {s.attempts + 1} of {s.max_attempts}.</p>
                  <button className="btn btn-primary" disabled={!recover || busy} onClick={() => act.mutate({ path: `steps/${s.key}/retry` })}><RefreshCw size={16} aria-hidden="true" />Review and retry</button>
                </>}
                {s.status === "FAILED" && !s.can_retry && <p className="small">Automatic retries are used up or not allowed for this step. Resolve it manually or cancel the run.</p>}
                {s.can_resolve && <button className="btn btn-secondary" disabled={!manage || busy} onClick={() => setDialog({ kind: "resolve", label: "Resolve manually" })}><Wrench size={16} aria-hidden="true" />Resolve manually</button>}
                {["FAILED", "UNKNOWN_OUTCOME", "PARTIAL"].includes(r.status) && <>
                  {!r.incident && <button className="btn btn-secondary" disabled={!recover || busy} onClick={() => setDialog({ kind: "escalate", label: "Escalate to operator" })}><Siren size={16} aria-hidden="true" />Escalate to operator</button>}
                  <button className="btn btn-danger" disabled={!manage || busy} onClick={() => setDialog({ kind: "cancel", label: "Cancel run" })}><Ban size={16} aria-hidden="true" />Cancel run</button>
                </>}
                {!recover && (s.can_retry || s.can_reconcile) && <p className="xs muted">Recovery needs the Automation Engineer role.</p>}
              </div>
            )}
            {act.error ? <ErrorMessage error={act.error} /> : null}
          </div>
        </div>
        {s.attempt_log.length > 0 && (
          <div>
            <div className="section-title">Attempt history</div>
            <ul className="stack tight small" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {s.attempt_log.map((a, i) => (
                <li key={i} style={{ borderTop: "1px solid var(--hairline)", paddingTop: 8 }}>
                  <StatusBadge status={/FOUND$|MANUALLY$/.test(a.outcome) || a.outcome === "SUCCEEDED" ? "SUCCEEDED" : a.outcome.startsWith("RECONCILED") ? "FAILED" : a.outcome}
                    label={`${a.kind === "reconcile" ? "Reconcile" : a.kind === "manual" ? "Manual" : `Attempt ${a.number}`}: ${a.outcome.replace(/_/g, " ").toLowerCase()}`} />
                  <div style={{ marginTop: 4 }}>{a.detail}</div>
                  <div className="xs muted">{a.actor.name} · {dateTime(a.at)}</div>
                </li>))}
            </ul>
          </div>
        )}
      </div>
      {dialog && <ActionDialog r={r} s={s} act={dialog} onClose={() => setDialog(null)} />}
    </Panel>
  );
}

function ActionDialog({ r, s, act, onClose }: { r: RunDetail; s: RunStep; act: Act; onClose: () => void }) {
  const m = useRunAction(r);
  const [text, setText] = useState("");
  const [ref, setRef] = useState("");
  const submit = () => {
    if (act.kind === "resolve") m.mutate({ path: `steps/${s.key}/resolve`, body: { external_ref: ref, note: text } }, { onSuccess: onClose });
    else m.mutate({ path: act.kind, body: { reason: text } }, { onSuccess: onClose });
  };
  const done = r.steps.filter((x) => x.idempotency_key && x.status === "SUCCEEDED" && x.external_ref);
  return (
    <Dialog open onClose={onClose} title={`${act.label} — ${r.code}`}
      footer={<><button className="btn btn-secondary" onClick={onClose}>Back</button>
        <button className={`btn ${act.kind === "cancel" ? "btn-danger" : "btn-primary"}`} form="run-act" disabled={m.isPending || text.trim().length < 10 || (act.kind === "resolve" && !!s.idempotency_key && ref.trim().length < 3)}>{act.label}</button></>}>
      <form id="run-act" className="stack" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {act.kind === "resolve" && <>
          <p className="small">Use this only after you checked the target system yourself (e.g. the project was created by hand). Your note and the reference are kept in the audit trail; read-back verification will record it as operator-confirmed.</p>
          {s.idempotency_key && <Field label="External reference you verified">{({ id }) => <input id={id} className="input mono" value={ref} onChange={(e) => setRef(e.target.value)} />}</Field>}
        </>}
        {act.kind === "cancel" && <Callout tone="warning" title="Completed writes are not deleted.">
          {done.length ? <>These sandbox records stay and are listed for manual compensation: {done.map((d) => `${d.label} (${d.external_ref})`).join(", ")}.</> : "No external writes were completed."}
          {" "}After cancelling, an analyst can reopen the case to revise it.
        </Callout>}
        {act.kind === "escalate" && <p className="small">Opens an incident in the exception queue for an operator.</p>}
        <Field label={act.kind === "resolve" ? "What did you check or do? (10+ characters)" : "Reason (10+ characters)"}>{({ id }) =>
          <textarea id={id} className="textarea" style={{ minHeight: 80 }} value={text} onChange={(e) => setText(e.target.value)} />}</Field>
        {m.error ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function IncidentPanel({ r }: { r: RunDetail }) {
  const inc = r.incident!;
  const { user } = useSession();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post(`/incidents/${inc.id}/resolve`, { reason: text }),
    onSuccess: () => { qc.invalidateQueries(); toast(`Incident #${inc.id} resolved.`); setOpen(false); },
  });
  return (
    <div style={{ marginBottom: 20 }}>
      <Callout tone={inc.status === "OPEN" ? "critical" : "success"} icon={<Siren size={18} aria-hidden="true" />} title={`Incident #${inc.id} · ${inc.status === "OPEN" ? "open" : "resolved"}: ${inc.title}`}>
        {inc.detail}
        {inc.compensation.length > 0 && <div style={{ marginTop: 6 }}><strong>Manual compensation needed:</strong> {inc.compensation.map((c) => `${c.step} (${c.external_ref})`).join(", ")}</div>}
        {inc.resolution && <div style={{ marginTop: 6 }}>Resolution by {inc.resolved_by?.name}: {inc.resolution}</div>}
        {inc.status === "OPEN" && can(user, "incident.manage") && ["SUCCEEDED", "CANCELLED"].includes(r.status) &&
          <div style={{ marginTop: 8 }}><button className="btn btn-outline btn-sm" onClick={() => setOpen(true)}>Resolve incident</button></div>}
      </Callout>
      <Dialog open={open} onClose={() => setOpen(false)} title={`Resolve incident #${inc.id}`}
        footer={<><button className="btn btn-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="btn btn-primary" form="inc" disabled={m.isPending || text.trim().length < 10}>Resolve</button></>}>
        <form id="inc" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
          <Field label="Resolution (10+ characters)">{({ id }) => <textarea id={id} className="textarea" style={{ minHeight: 80 }} value={text} onChange={(e) => setText(e.target.value)} />}</Field>
          {m.error ? <ErrorMessage error={m.error} /> : null}
        </form>
      </Dialog>
    </div>
  );
}
