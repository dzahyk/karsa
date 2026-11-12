import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, can, fieldErrors } from "../api";
import { Callout, Dialog, ErrorMessage, ErrorState, Field, LoadingRows, Panel, StatusBadge, SyntheticTag, useToast } from "../components/ui";
import { dateOnly, idr, int, parseWhole, pct } from "../format";
import { useSession } from "../session";
import type { RateCard, User } from "../types";

type Connector = { key: string; name: string; actions: string[]; risk_class: string; supports_idempotency: boolean;
  supports_read_after_write: boolean; sandbox: boolean; enabled: boolean; updated_at: string; updated_by: User | null };
type Policy = { thresholds: Record<string, unknown>; rules: { id: string; rule: string; where: string }[] };
const TABS = ["Rate cards", "Integrations", "Policy rules", "Team"] as const;

export function ManagePage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("Rate cards");
  return (
    <div className="page">
      <div className="page-head"><div>
        <h1 className="page-title">Manage workspace</h1>
        <p className="page-sub">Rate card versions, connector switches, the rules the server enforces, and who has which role.</p>
      </div><SyntheticTag /></div>
      <div className="tabs" role="tablist" aria-label="Manage sections">
        {TABS.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      <div role="tabpanel" aria-label={tab}>
        {tab === "Rate cards" && <RateCards />}
        {tab === "Integrations" && <Integrations />}
        {tab === "Policy rules" && <PolicyRules />}
        {tab === "Team" && <Team />}
      </div>
    </div>
  );
}

function RateCards() {
  const { user } = useSession();
  const q = useQuery({ queryKey: ["rateCards"], queryFn: () => api.get<RateCard[]>("/admin/rate-cards") });
  const [open, setOpen] = useState(false);
  if (q.isLoading) return <LoadingRows />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <div className="stack">
      <Callout tone="info" title="Publishing a new version ends the current one now.">Packages priced on an older card can no longer be approved or executed until they are repriced (BR-013).</Callout>
      <Panel title="Versions" flush actions={can(user, "manage.rate_cards") && <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)}>New version</button>}>
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Code</th><th>Unit cost (cons. / exp. / aggr.)</th><th>Fixed</th><th>Margin floor</th><th>Capacity / week</th><th>Valid</th><th>Status</th></tr></thead>
          <tbody>{q.data!.map((c) => (
            <tr key={c.code}>
              <td className="mono">{c.code}</td>
              <td className="mono small">{idr(c.unit_cost_idr.conservative)} / {idr(c.unit_cost_idr.expected)} / {idr(c.unit_cost_idr.aggressive)}</td>
              <td className="mono small">{idr(c.fixed_cost_idr)}</td><td className="mono">{c.margin_floor_pct}</td>
              <td className="mono">{int(c.capacity_leads_per_week)}</td>
              <td className="small">{dateOnly(c.valid_from)} – {dateOnly(c.valid_to)}</td>
              <td>{c.expired ? <StatusBadge status="SUPERSEDED" label="Ended" /> : <StatusBadge status="CONFIRMED" label="Current" />}</td>
            </tr>))}</tbody>
        </table></div>
      </Panel>
      {open && <RateCardDialog current={q.data!.find((c) => !c.expired) ?? q.data![0]} onClose={() => setOpen(false)} />}
    </div>
  );
}

function RateCardDialog({ current, onClose }: { current: RateCard; onClose: () => void }) {
  const [f, setF] = useState({
    unit_cost_conservative_idr: String(current.unit_cost_idr.conservative), unit_cost_expected_idr: String(current.unit_cost_idr.expected),
    unit_cost_aggressive_idr: String(current.unit_cost_idr.aggressive), fixed_cost_idr: String(current.fixed_cost_idr),
    margin_floor_pct: String(current.margin_floor_bp / 100), capacity_leads_per_week: String(current.capacity_leads_per_week), notes: "",
  });
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post<RateCard>("/admin/rate-cards", {
      unit_cost_conservative_idr: parseWhole(f.unit_cost_conservative_idr), unit_cost_expected_idr: parseWhole(f.unit_cost_expected_idr),
      unit_cost_aggressive_idr: parseWhole(f.unit_cost_aggressive_idr), fixed_cost_idr: parseWhole(f.fixed_cost_idr),
      margin_floor_bp: Math.round(Number(f.margin_floor_pct) * 100), capacity_leads_per_week: parseWhole(f.capacity_leads_per_week), notes: f.notes,
    }),
    onSuccess: (c) => { qc.invalidateQueries(); toast(`Rate card ${c.code} published.`); onClose(); },
  });
  const errs = fieldErrors(m.error);
  const fields: [keyof typeof f, string, string][] = [
    ["unit_cost_conservative_idr", "Unit cost — conservative (Rp)", "unit_cost_conservative_idr"], ["unit_cost_expected_idr", "Unit cost — expected (Rp)", "unit_cost_expected_idr"],
    ["unit_cost_aggressive_idr", "Unit cost — aggressive (Rp)", "unit_cost_aggressive_idr"], ["fixed_cost_idr", "Fixed cost (Rp)", "fixed_cost_idr"],
    ["margin_floor_pct", "Margin floor (%)", "margin_floor_bp"], ["capacity_leads_per_week", "Delivery capacity (leads / week)", "capacity_leads_per_week"],
  ];
  return (
    <Dialog open onClose={onClose} title="Publish a new rate card version"
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="rc" disabled={m.isPending}>Publish</button></>}>
      <form id="rc" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <div className="grid-2 even" style={{ gap: 12 }}>
          {fields.map(([k, label, ek]) => (
            <Field key={k} label={label} error={errs[ek]}>{({ id, describedBy, invalid }) =>
              <input id={id} className="input num" inputMode="decimal" value={f[k]} aria-describedby={describedBy} aria-invalid={invalid} onChange={(e) => setF({ ...f, [k]: e.target.value })} />}</Field>
          ))}
        </div>
        <Field label="Notes">{({ id }) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />}</Field>
        <Callout tone="warning">Current version {current.code} ends immediately. Synthetic demo values only.</Callout>
        {m.error && !Object.keys(errs).length ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function Integrations() {
  const { user } = useSession();
  const q = useQuery({ queryKey: ["connectors"], queryFn: () => api.get<Connector[]>("/admin/connectors") });
  const [edit, setEdit] = useState<Connector | null>(null);
  if (q.isLoading) return <LoadingRows />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <Panel title="Connectors" subtitle="Manifests are fixed in code; the model cannot change them. Only an admin can switch a connector off or on." flush>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Connector</th><th>Allowed actions</th><th>Risk</th><th>Idempotent</th><th>Read-back</th><th>Status</th><th /></tr></thead>
        <tbody>{q.data!.map((c) => (
          <tr key={c.key}>
            <td><strong>{c.name}</strong>{c.sandbox && <div className="xs muted">Simulated sandbox — no real system</div>}</td>
            <td className="mono xs">{c.actions.join(", ")}</td><td>{c.risk_class}</td>
            <td>{c.supports_idempotency ? "Yes" : "No"}</td><td>{c.supports_read_after_write ? "Yes" : "No"}</td>
            <td>{c.enabled ? <StatusBadge status="CONFIRMED" label="Enabled" /> : <StatusBadge status="BLOCKED" label="Disabled" />}
              {c.updated_by && <div className="xs muted">by {c.updated_by.name}</div>}</td>
            <td>{can(user, "manage.integrations") && <button className="btn btn-secondary btn-sm" onClick={() => setEdit(c)}>{c.enabled ? "Disable" : "Enable"}</button>}</td>
          </tr>))}</tbody>
      </table></div>
      {edit && <ConnectorDialog c={edit} onClose={() => setEdit(null)} />}
    </Panel>
  );
}

function ConnectorDialog({ c, onClose }: { c: Connector; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.patch(`/admin/connectors/${c.key}`, { enabled: !c.enabled, reason }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["connectors"] }); toast(`${c.name} ${c.enabled ? "disabled" : "enabled"}.`); onClose(); },
  });
  return (
    <Dialog open onClose={onClose} title={`${c.enabled ? "Disable" : "Enable"} ${c.name}?`}
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className={`btn ${c.enabled ? "btn-danger" : "btn-primary"}`} form="conn" disabled={m.isPending || reason.trim().length < 5}>{c.enabled ? "Disable" : "Enable"}</button></>}>
      <form id="conn" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        {c.enabled && <Callout tone="warning">While disabled, authorizations and runs that need {c.actions.join(" / ")} are blocked.</Callout>}
        <Field label="Reason (recorded in the audit log)">{({ id }) => <input id={id} className="input" value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        {m.error ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function PolicyRules() {
  const q = useQuery({ queryKey: ["policy"], queryFn: () => api.get<Policy>("/policy") });
  if (q.isLoading) return <LoadingRows />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const t = q.data!.thresholds as { margin_floor_bp: number; capacity_leads_per_week: number; dual_approval_when: string; max_write_attempts: number; session_hours: number };
  return (
    <div className="stack">
      <Panel title="Thresholds in force">
        <dl className="kv small">
          <dt>Margin floor</dt><dd>{pct(t.margin_floor_bp)} (from the current rate card)</dd>
          <dt>Delivery capacity</dt><dd>{int(t.capacity_leads_per_week)} qualified leads per week</dd>
          <dt>Dual approval</dt><dd>{t.dual_approval_when}</dd>
          <dt>Write attempts</dt><dd>{t.max_write_attempts} per step, same idempotency key</dd>
          <dt>Session length</dt><dd>{t.session_hours} hours</dd>
        </dl>
      </Panel>
      <Panel title="Rules enforced by the server" flush>
        <div className="table-wrap"><table className="table">
          <thead><tr><th>ID</th><th>Rule</th><th>Enforced in</th></tr></thead>
          <tbody>{q.data!.rules.map((r) => <tr key={r.id}><td className="mono">{r.id}</td><td>{r.rule}</td><td className="small muted">{r.where}</td></tr>)}</tbody>
        </table></div>
      </Panel>
    </div>
  );
}

function Team() {
  const q = useQuery({ queryKey: ["adminUsers"], queryFn: () => api.get<(User & { active: boolean })[]>("/admin/users") });
  if (q.isLoading) return <LoadingRows />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return (
    <Panel title="People and roles" subtitle="Roles decide what each person can read and do; the server checks every request." flush>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Modules</th></tr></thead>
        <tbody>{q.data!.map((u) => <tr key={u.id}><td><strong>{u.name}</strong><div className="xs muted">{u.title}</div></td><td className="mono small">{u.username}</td><td>{u.role_label}</td><td className="small">{u.modules.join(", ") || "—"}</td></tr>)}</tbody>
      </table></div>
    </Panel>
  );
}
