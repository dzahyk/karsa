import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, ArrowLeftRight, Ban, BarChart3, Calendar, Check, CheckCircle2, ClipboardList, Download, FileText, FlaskConical, Play, ShieldCheck,
  Target, UserPen, Wallet,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, can } from "../api";
import { Badge, Callout, Dialog, ErrorMessage, ErrorState, Field, LoadingRows, Panel, StatusBadge, SyntheticTag, useToast } from "../components/ui";
import { dateTime, idr, int, pct, shortHash, valueDisplay } from "../format";
import { useSession } from "../session";
import type { Approval, DiffEntry, PackageDetail, PackageSummary, RunDetail } from "../types";

function fmt(kind: string, v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object" && !Array.isArray(v)) {
    const o = v as { value: string | null; state: string | null };
    return `${valueDisplay(kind, o.value)}${o.state ? ` (${o.state.toLowerCase()})` : ""}`;
  }
  if (Array.isArray(v)) return v.length ? v.join("; ") : "—";
  if (kind === "idr") return idr(v as number);
  if (kind === "bp") return pct(v as number);
  if (kind === "weeks") return `${v} weeks`;
  if (kind === "integer") return int(v as number);
  return String(v);
}

function DiffList({ diff }: { diff: DiffEntry[] }) {
  return (
    <div>
      {diff.map((d) => (
        <div key={d.field} className="diff-row">
          <span style={{ fontWeight: 600 }}>{d.label}</span>
          {d.kind === "list" && d.field === "assumptions" ? (
            <span className="small">
              {(d.after as string[]).map((x) => <div key={x}>+ {x}</div>)}
              {(d.before as string[]).map((x) => <div key={x} className="diff-before">− {x}</div>)}
            </span>
          ) : (
            <span><span className="diff-before">{fmt(d.kind, d.before)}</span> <span aria-label="changed to">→</span> <span className="diff-after">{fmt(d.kind, d.after)}</span></span>
          )}
        </div>
      ))}
    </div>
  );
}

export function ReviewPage() {
  const { packageId = "" } = useParams();
  const { user } = useSession();
  const q = useQuery({ queryKey: ["package", packageId], queryFn: () => api.get<PackageDetail>(`/packages/${packageId}`) });
  const [decision, setDecision] = useState<null | "APPROVE" | "REJECT" | "REQUEST_CHANGES">(null);
  const [authOpen, setAuthOpen] = useState(false);
  if (q.isLoading) return <div className="page"><LoadingRows rows={8} label="Loading package" /></div>;
  if (q.error || !q.data) return <div className="page"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div>;
  const p = q.data;
  const ct = p.content;
  const pr = ct.pricing;
  const canReview = can(user, "package.review");
  const reviewable = p.state === "IN_REVIEW" && p.is_current;
  const blocked = p.approval_blockers.length > 0 || p.rate_card_expired;
  const myApproval = p.approvals.some((a) => a.decision === "APPROVE" && a.actor.id === user?.id && a.package_version === p.version);
  const approvalsHere = p.approvals.filter((a) => a.decision === "APPROVE" && a.package_version === p.version);
  const prevDecision = [...p.approvals].reverse().find((a) => a.package_version === p.version);
  const actions = (mobile: boolean) => canReview && reviewable ? (
    <div className={mobile ? "sticky-actions show-mobile" : "action-bar hide-mobile"}>
      <button className="btn btn-outline" onClick={() => setDecision("REQUEST_CHANGES")}>Request changes</button>
      <button className="btn btn-danger" onClick={() => setDecision("REJECT")}>Reject</button>
      <button className={`btn btn-primary ${mobile ? "full" : ""}`} onClick={() => setDecision("APPROVE")} disabled={blocked || myApproval}
        title={myApproval ? "You already approved; a different approver must give the second approval." : undefined}>
        <Check size={18} aria-hidden="true" />{p.required_approvals > 1 ? `Approve (${approvalsHere.length + 1} of ${p.required_approvals})` : "Approve decision"}
      </button>
    </div>
  ) : null;
  return (
    <div className="page">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/approvals"><ArrowLeft size={14} aria-hidden="true" style={{ verticalAlign: -2 }} /> Approvals</Link>
        <span>/</span><Link to={`/cases/${ct.case.code}/package`} className="mono">{ct.case.code}</Link>
      </nav>
      <div className="page-head" style={{ marginBottom: 14 }}>
        <div>
          <div className="section-title" style={{ marginBottom: 4 }}>Approval review</div>
          <h1 className="page-title">{ct.case.client} — {ct.case.title}</h1>
          <div className="row wrap" style={{ marginTop: 10, gap: 8 }}>
            <span className="badge outline">Package v{p.version}{p.is_current ? " (current)" : ""}</span>
            <StatusBadge status={p.state} label={p.state !== "IN_REVIEW" ? undefined : myApproval ? "Awaiting second approver" : canReview ? "Pending your approval" : "In review"} />
            <StatusBadge status={p.risk_level} />
            <SyntheticTag />
          </div>
        </div>
        <div className="stack tight" style={{ alignItems: "flex-end" }}>
          <span className="row" style={{ gap: 8, fontWeight: 600 }}>
            {blocked ? <Ban size={18} color="var(--critical)" aria-hidden="true" /> : <CheckCircle2 size={18} color="var(--success)" aria-hidden="true" />}
            {p.approval_blockers.length} critical unresolved issue{p.approval_blockers.length === 1 ? "" : "s"}
          </span>
          <span className="hash" title={p.content_hash}>Snapshot SHA-256 {shortHash(p.content_hash)}…</span>
          <span className="row" style={{ gap: 6 }}>
            <a className="btn btn-ghost btn-sm" href={`/api/v1/packages/${p.id}/export.md`} download><Download size={14} aria-hidden="true" />Markdown</a>
            <a className="btn btn-ghost btn-sm" href={`/api/v1/packages/${p.id}/export.json`} download><Download size={14} aria-hidden="true" />JSON</a>
          </span>
        </div>
      </div>

      <div className="stack">
        {!p.is_current && <Callout tone="critical" title="This version is no longer current.">{p.superseded_reason ?? "A newer version exists."} It cannot be approved or executed. <Link to={`/cases/${ct.case.code}/package`}>See versions</Link></Callout>}
        {p.state === "CHANGES_REQUESTED" && prevDecision && <Callout tone="warning" title={`Changes requested by ${prevDecision.actor.name}:`}>{prevDecision.note}</Callout>}
        {p.state === "REJECTED" && prevDecision && <Callout tone="critical" title={`Rejected by ${prevDecision.actor.name}:`}>{prevDecision.note}</Callout>}
        {p.approval_blockers.length > 0 && <Callout tone="critical" title="Approval is blocked.">{p.approval_blockers.map((b) => b.message).join(" ")}</Callout>}
        {p.rate_card_expired && p.state !== "SUPERSEDED" && <Callout tone="critical" title={`Rate card ${pr.rate_card} is no longer valid.`}>This package cannot be approved, authorized or executed. The analyst must reprice it on the current rate card and create a new version (BR-013).</Callout>}
        {p.disabled_connectors.length > 0 && <Callout tone="warning" title="Connector disabled.">{p.disabled_connectors.join(", ")} is switched off by an admin; authorization and execution are blocked until it is re-enabled.</Callout>}
        {p.required_approvals > 1 && <ApprovalSlots p={p} approvals={approvalsHere} />}
        {myApproval && reviewable && <Callout tone="info">You have approved. A different approver must give the second approval.</Callout>}
        {ct.exception && <Callout tone="warning" title={`Margin exception requested by ${ct.exception.requested_by}:`}>{ct.exception.reason}</Callout>}
        {!canReview && reviewable && <Callout tone="info">You are acting as {user?.name} ({user?.role_label}). Only a Commercial Manager can decide; switch role in the header to try it.</Callout>}

        <div className="grid-2">
          <div className="stack">
            <Panel title="Decision summary" subtitle="Proposed decision, commercial terms and the evidence behind them.">
              <div className="callout brand" style={{ marginBottom: 16 }}>
                <Target size={18} aria-hidden="true" color="var(--brand)" />
                <div><strong>Decision proposal</strong><p style={{ marginTop: 4 }}>{ct.recommendation}</p>
                  <p className="xs muted" style={{ marginTop: 6 }}>{ct.recommendation_basis}</p></div>
              </div>
              <div className="metric-row" style={{ border: "1px solid var(--hairline)", borderRadius: 8 }}>
                <div className="metric"><div className="label"><Wallet size={15} aria-hidden="true" />Proposed fee</div><div className="value mono">{idr(pr.inputs.proposed_fee_idr)}</div><div className="sub">Total est. cost {idr(pr.total_cost_idr)}</div></div>
                <div className="metric"><div className="label"><BarChart3 size={15} aria-hidden="true" />Est. gross margin</div><div className="value mono" style={{ color: pr.margin_bp < pr.margin_floor_bp ? "var(--critical)" : undefined }}>{pr.margin_pct}</div><div className="sub">Policy floor {pct(pr.margin_floor_bp)}</div></div>
                <div className="metric"><div className="label"><Calendar size={15} aria-hidden="true" />Delivery</div><div className="value">{pr.inputs.duration_weeks} weeks</div><div className="sub">{int(pr.inputs.target_units)} qualified leads</div></div>
              </div>
              <div className="show-mobile" style={{ marginTop: 16 }}>
                <div className="section-title">What changed?</div>
                {p.previous && p.diff.length ? <DiffList diff={p.diff} /> : <p className="small muted">{p.previous ? "No differences from the previous version." : "First version."}</p>}
                <Link to={`/cases/${ct.case.code}/requirements`} className="btn btn-secondary" style={{ width: "100%", marginTop: 10 }}>View evidence & full scope</Link>
              </div>
              <details style={{ marginTop: 12 }}>
                <summary className="small" style={{ cursor: "pointer", fontWeight: 600 }}>Calculation trace — rate card {pr.rate_card}, {pr.scenario} scenario</summary>
                <ol className="mono xs" style={{ margin: "8px 0 0", paddingLeft: 18 }}>{pr.trace.map((t) => <li key={t}>{t}</li>)}</ol>
                <p className="xs muted">Calculated {dateTime(pr.calculated_at)} · {pr.formula_version}</p>
              </details>
            </Panel>

            {ct.options && (
              <Panel title="Options considered" subtitle="Same scope and fee; unit cost varies by delivery scenario." flush>
                <div className="table-wrap"><table className="table">
                  <thead><tr><th>Option</th><th className="right">Total cost</th><th className="right">Margin</th></tr></thead>
                  <tbody>{ct.options.map((o) => (
                    <tr key={o.scenario} className={o.recommended ? "selected" : ""}>
                      <td>{o.label}{o.recommended && <strong> · recommended</strong>}<div className="xs muted">{o.description}</div></td>
                      <td className="right mono">{idr(o.total_cost_idr)}</td>
                      <td className="right mono" style={{ color: o.below_floor ? "var(--critical)" : undefined }}>{o.margin_pct}</td>
                    </tr>))}</tbody>
                </table></div>
                {ct.capacity && <p className="small" style={{ padding: "10px 16px" }}>Capacity: {int(ct.capacity.required_per_week)} leads/week needed of {int(ct.capacity.capacity_per_week)} available ({ct.capacity.utilization_pct}% utilization).</p>}
              </Panel>
            )}
            <Panel title="Scope & requirements" subtitle="Each value with its status and the source text it came from." flush>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Requirement</th><th>Value</th><th>Status</th></tr></thead>
                <tbody>{ct.requirements.map((r) => (
                  <tr key={r.key}>
                    <td style={{ fontWeight: 600, verticalAlign: "top" }}>{r.label}{r.critical && <div className="xs muted" style={{ fontWeight: 400 }}>Critical</div>}</td>
                    <td style={{ verticalAlign: "top" }}>
                      <div className={r.value_type === "text" ? "" : "mono"}>{valueDisplay(r.value_type, r.value)}</div>
                      {r.overridden && <div className="xs" style={{ color: "var(--warning)" }}>Overridden by analyst — source says {valueDisplay(r.value_type, r.source_value ?? null)}</div>}
                      {r.source ? <div className="xs muted" style={{ marginTop: 4 }}>Source: “{r.source.quote.length > 120 ? r.source.quote.slice(0, 120) + "…" : r.source.quote}” — {r.source.document}</div>
                        : <div className="xs muted" style={{ marginTop: 4 }}>No source text</div>}
                      {r.source?.verification === "analyst_recorded" && <div style={{ marginTop: 4 }}><Badge tone="warning" icon={<UserPen size={12} aria-hidden="true" />}>Analyst-recorded {r.source.channel} · {r.source.reference}</Badge></div>}
                    </td>
                    <td style={{ verticalAlign: "top" }}><StatusBadge status={r.state} /></td>
                  </tr>))}
                </tbody>
              </table></div>
            </Panel>
          </div>

          <div className="stack">
            <Panel title={p.previous ? `Changes since previous version (v${p.previous.version} → v${p.version})` : "Changes since previous version"}
              actions={<ArrowLeftRight size={18} aria-hidden="true" color="var(--brand)" />}>
              {p.previous_reviews.filter((a) => a.note).map((a) => (
                <div key={a.id} className="callout warning" style={{ marginBottom: 10 }}>
                  <FileText size={16} aria-hidden="true" />
                  <div className="small"><strong>v{a.package_version} review — {a.decision === "REQUEST_CHANGES" ? "changes requested" : a.decision.toLowerCase()} by {a.actor.name}:</strong> “{a.note}”</div>
                </div>))}
              {!p.previous ? <p className="small muted">First version — nothing to compare.</p> :
                p.diff.length === 0 ? <p className="small muted">No differences in requirements, pricing, assumptions or actions.</p> : <DiffList diff={p.diff} />}
            </Panel>
            <Panel title="Evidence references" actions={<FileText size={18} aria-hidden="true" color="var(--brand)" />}>
              <ul className="stack tight" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {ct.evidence.map((e, i) => (
                  <li key={e.sha256} className="row between small" style={{ borderBottom: "1px solid var(--hairline)", paddingBottom: 8 }}>
                    <span><span className="mono muted">E{i + 1}</span> {e.document}</span>
                    <span className="muted">{e.citations} citation{e.citations === 1 ? "" : "s"}</span>
                  </li>
                ))}
              </ul>
              <Link to={`/cases/${ct.case.code}/requirements`} className="btn btn-ghost" style={{ marginTop: 8 }}>View evidence in context</Link>
            </Panel>
            {ct.fit_gap && ct.fit_gap.length > 0 && (
              <Panel title="Fit-gap against service catalogue" subtitle="Requested items matched to standard services (synthetic catalogue).">
                <ul className="stack tight small" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {ct.fit_gap.map((g, i) => (
                    <li key={i} className="row between" style={{ borderBottom: "1px solid var(--hairline)", paddingBottom: 6 }}>
                      <span>{g.requested}<span className="xs muted"> · {g.from}</span></span>
                      {g.capability ? <Badge tone="success">{g.capability}</Badge> : <Badge tone="warning">Gap — custom scoping</Badge>}
                    </li>))}
                </ul>
              </Panel>
            )}
            <Panel title="Assumptions" actions={<FlaskConical size={18} aria-hidden="true" color="var(--brand)" />}>
              <ul style={{ margin: 0, paddingLeft: 18 }} className="small stack tight">{ct.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            </Panel>
            <Panel title="Risks & open items">
              {ct.risks.length ? <ul style={{ margin: 0, paddingLeft: 18 }} className="small stack tight">{ct.risks.map((r) => <li key={r}>{r}</li>)}</ul> : <p className="small muted">No risk flags raised by the rules.</p>}
            </Panel>
            <Panel title="Resulting downstream actions" subtitle="Only after a separate execution authorization. All targets are sandboxes." actions={<ClipboardList size={18} aria-hidden="true" color="var(--brand)" />}>
              <ul className="stack tight" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {ct.proposed_actions.map((a) => (
                  <li key={a.action}><div style={{ fontWeight: 600 }}>{a.label}</div><div className="small muted">{a.target} — {a.description}</div></li>
                ))}
              </ul>
            </Panel>
            {p.approvals.length > 0 && (
              <Panel title="Review history">
                <ul className="stack tight" style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {p.approvals.map((a) => (
                    <li key={a.id} className="small"><StatusBadge status={{ APPROVE: "APPROVED", REJECT: "REJECTED", REQUEST_CHANGES: "CHANGES_REQUESTED" }[a.decision]} />{" "}
                      <strong>{a.actor.name}</strong> · v{a.package_version} · {dateTime(a.created_at)}{a.note && <div className="muted">“{a.note}”</div>}
                      <div className="hash">hash {shortHash(a.package_hash)}…</div></li>
                  ))}
                </ul>
              </Panel>
            )}
          </div>
        </div>

        {p.state === "APPROVED" && <Execution p={p} onAuthorize={() => setAuthOpen(true)} />}

        <Callout tone="info" title="Execution authorization is separate.">Approving confirms the decision and terms for this exact snapshot. It does not create anything in the CRM or tracker; that needs a separate authorization.</Callout>
        {actions(false)}
        {actions(true)}
      </div>
      {decision && <DecisionDialog p={p} decision={decision} onClose={() => setDecision(null)} />}
      {authOpen && <AuthorizeDialog p={p} onClose={() => setAuthOpen(false)} />}
    </div>
  );
}

function DecisionDialog({ p, decision, onClose }: { p: PackageDetail; decision: "APPROVE" | "REJECT" | "REQUEST_CHANGES"; onClose: () => void }) {
  const [note, setNote] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const m = useMutation({
    mutationFn: () => api.post<Approval>(`/packages/${p.id}/review`, { decision, note: note || null, package_hash: p.content_hash, version: p.version }),
    onSuccess: (rec) => {
      qc.invalidateQueries();
      if (decision === "APPROVE" && rec.package_state === "IN_REVIEW") toast("Your approval is recorded. A second, different approver must confirm before the decision is approved.");
      else toast({ APPROVE: "Decision approved and recorded. Execution still needs authorization.", REJECT: "Proposal rejected and returned to the analyst.", REQUEST_CHANGES: "Changes requested. The analyst will prepare a new version." }[decision]);
      onClose();
    },
  });
  const stale = m.error instanceof ApiError && m.error.code === "APPROVAL_SNAPSHOT_CHANGED";
  const noteRequired = decision !== "APPROVE" || p.risk_level === "HIGH";
  const title = { APPROVE: "Approve this decision?", REJECT: "Reject this proposal?", REQUEST_CHANGES: "Request changes?" }[decision];
  const latest = useQuery({ queryKey: ["packages", p.content.case.code], queryFn: () => api.get<PackageSummary[]>(`/cases/${p.content.case.code}/packages`), enabled: stale });
  return (
    <Dialog open onClose={onClose} title={title}
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className={`btn ${decision === "REJECT" ? "btn-danger" : "btn-primary"}`} form="decision" disabled={m.isPending || (noteRequired && !note.trim())}>
          {m.isPending ? "Submitting…" : { APPROVE: "Approve decision", REJECT: "Reject proposal", REQUEST_CHANGES: "Request changes" }[decision]}
        </button></>}>
      <form id="decision" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <p className="small">
          {p.content.case.client} — {p.content.case.title}, package v{p.version} (<span className="mono">{shortHash(p.content_hash)}</span>):
          fee {idr(p.content.pricing.inputs.proposed_fee_idr)}, estimated margin {p.content.pricing.margin_pct}, {p.content.pricing.inputs.duration_weeks} weeks.
        </p>
        {decision === "APPROVE" && <Callout tone="info">Your approval is bound to this snapshot hash. If anything changes later, the approval is invalidated. No external action starts now.</Callout>}
        <Field label={noteRequired ? "Reviewer note (required)" : "Reviewer note (optional)"}
          hint={decision === "APPROVE" && p.risk_level === "HIGH" ? "High risk: explain the exception (e.g. why a below-floor margin is acceptable)." : "Visible to the analyst and kept in the audit trail."}>
          {({ id, describedBy }) => <textarea id={id} className="textarea" style={{ minHeight: 90 }} value={note} onChange={(e) => setNote(e.target.value)} aria-describedby={describedBy} />}
        </Field>
        {stale ? (
          <Callout tone="critical" title="The package changed after you opened it.">
            Load the latest version before deciding.{" "}
            {latest.data?.[0] && <button type="button" className="btn btn-ghost" onClick={() => { onClose(); nav(`/approvals/${latest.data![0].id}`); }}>Open v{latest.data[0].version}</button>}
          </Callout>
        ) : m.error ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

const CONFIRM_TEXT: Record<string, string> = {
  "crm.create_opportunity": "Create one sandbox CRM opportunity",
  "tracker.create_project": "Create one sandbox tracker project",
  "tracker.attach_spec": "Attach the package specification to that tracker project",
};

function AuthorizeDialog({ p, onClose }: { p: PackageDetail; onClose: () => void }) {
  const actions = p.content.proposed_actions;
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post(`/packages/${p.id}/authorize`, { package_hash: p.content_hash, confirmed_actions: actions.filter((a) => checked[a.action]).map((a) => a.action), note }),
    onSuccess: () => { qc.invalidateQueries(); toast("Execution authorized for the sandbox actions you confirmed."); onClose(); },
  });
  const all = actions.every((a) => checked[a.action]);
  return (
    <Dialog open onClose={onClose} title="Authorize execution"
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="authorize" disabled={!all || m.isPending}><ShieldCheck size={18} aria-hidden="true" />{m.isPending ? "Authorizing…" : "Authorize these actions"}</button></>}>
      <form id="authorize" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <p className="small">Confirm each write action. They run only against the approved snapshot <span className="mono">{shortHash(p.content_hash)}</span>.</p>
        <fieldset className="stack tight" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="label" style={{ marginBottom: 8 }}>Actions to authorize</legend>
          {actions.map((a) => (
            <label key={a.action} className="check radio">
              <input type="checkbox" checked={!!checked[a.action]} onChange={(e) => setChecked({ ...checked, [a.action]: e.target.checked })} />
              <span><strong>{CONFIRM_TEXT[a.action] ?? a.label}</strong> <span className="muted">({a.target})</span><div className="small muted">{a.description}</div></span>
            </label>
          ))}
        </fieldset>
        <Callout tone="warning">These are simulated sandbox connectors. No real CRM or project tracker is connected in this demo.</Callout>
        <Field label="Note (optional)">{({ id }) => <input id={id} className="input" value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        {m.error ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function Execution({ p, onAuthorize }: { p: PackageDetail; onAuthorize: () => void }) {
  const { user } = useSession();
  const [simulate, setSimulate] = useState("none");
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const start = useMutation({
    mutationFn: () => api.post<RunDetail>(`/packages/${p.id}/runs`, { simulate }),
    onSuccess: (r) => { qc.invalidateQueries(); toast(`Run ${r.code} queued. The worker is processing it.`); nav(`/workflows/${r.code}`); },
  });
  const run = p.runs[0];
  return (
    <Panel title="Execution" subtitle="Approval and execution are recorded as separate events.">
      <ol className="timeline">
        <li className="ok"><span className="tl-dot ok"><Check size={15} aria-hidden="true" /></span>
          <div><strong>Decision approved</strong><div className="small muted">{p.approvals.filter((a) => a.decision === "APPROVE").map((a) => `${a.actor.name} · ${dateTime(a.created_at)}`).join("")}</div></div></li>
        <li className={p.authorization ? "ok" : ""}><span className={`tl-dot ${p.authorization ? "ok" : ""}`}>{p.authorization ? <Check size={15} aria-hidden="true" /> : 2}</span>
          <div><strong>Execution authorized</strong>
            {p.authorization ? <div className="small muted">{p.authorization.actor.name} · {dateTime(p.authorization.created_at)} · {p.authorization.actions.length} sandbox action(s)</div> : (
              <div className="row wrap" style={{ marginTop: 6 }}>
                <span className="small muted">Not yet authorized.</span>
                {can(user, "execution.authorize") ? <button className="btn btn-primary btn-sm" onClick={onAuthorize}><ShieldCheck size={16} aria-hidden="true" />Authorize execution</button>
                  : <span className="small muted">Requires the Commercial Manager role.</span>}
              </div>)}
          </div></li>
        <li><span className={`tl-dot ${run ? (run.status === "SUCCEEDED" ? "ok" : "fail") : ""}`}>{run ? <Play size={14} aria-hidden="true" /> : 3}</span>
          <div><strong>Sandbox workflow</strong>
            {run ? <div className="small"><Link to={`/workflows/${run.code}`} className="mono">{run.code}</Link> · <StatusBadge status={run.status} /> · {run.steps_done}/{run.steps_total} steps</div> :
              p.authorization ? (
                can(user, "workflow.run") ? (
                  <div className="row wrap" style={{ marginTop: 6, gap: 10 }}>
                    <label className="small" htmlFor="simulate">Failure injection (demo)</label>
                    <select id="simulate" className="select" style={{ width: "auto" }} value={simulate} onChange={(e) => setSimulate(e.target.value)}>
                      <option value="none">None</option>
                      <option value="tracker_timeout_before_commit">Tracker timeout before commit (retry is safe)</option>
                      <option value="tracker_timeout_after_commit">Tracker commits, response lost (outcome unknown)</option>
                    </select>
                    <button className="btn btn-primary btn-sm" onClick={() => start.mutate()} disabled={start.isPending}><Play size={15} aria-hidden="true" />{start.isPending ? "Running…" : "Run sandbox workflow"}</button>
                  </div>) : <div className="small muted">An Analyst or Automation Engineer can start the run.</div>
              ) : <div className="small muted">Waits for authorization.</div>}
            {start.error ? <ErrorMessage error={start.error} /> : null}
          </div></li>
      </ol>
    </Panel>
  );
}

function ApprovalSlots({ p, approvals }: { p: PackageDetail; approvals: Approval[] }) {
  return (
    <section className="panel" style={{ padding: "14px 18px" }} aria-label="Approval slots">
      <div className="row between wrap" style={{ marginBottom: 8 }}>
        <strong>Two-person approval required (high risk)</strong>
        <span className="small muted">{approvals.length} of {p.required_approvals} approvals recorded</span>
      </div>
      <div className="slots">
        {Array.from({ length: p.required_approvals }, (_, i) => {
          const a = approvals[i];
          return (
            <div key={i} className={`slot ${a ? "filled" : ""}`}>
              <div className="xs muted">Approver {i + 1}</div>
              {a ? <><strong>{a.actor.name}</strong><div className="xs muted">{dateTime(a.created_at)}{a.note ? ` — “${a.note}”` : ""}</div></>
                : <span className="muted">Waiting for {i === 0 ? "an" : "a different"} approver</span>}
            </div>);
        })}
      </div>
    </section>
  );
}
