import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, FileCheck2, Info, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, can } from "../api";
import { Badge, Callout, ErrorMessage, ErrorState, LoadingRows, Panel, StatusBadge, SyntheticTag, useToast } from "../components/ui";
import { dateOnly, dateTime, idr, int, parseWhole, pct, relative } from "../format";
import { useSession } from "../session";
import type { Assessment, Feasibility, PackageSummary } from "../types";
import { caseKey, useCase } from "./CaseLayout";

const FIELDS: { key: string; label: string; prefix?: string; hint: (f: Feasibility) => string }[] = [
  { key: "target_units", label: "Target (qualified leads)", hint: () => "From the confirmed requirement “Target”." },
  { key: "unit_cost_idr", label: "Unit cost per lead", prefix: "Rp", hint: (f) => `Rate card ${f.rate_card.code}, ${f.scenario} scenario.` },
  { key: "fixed_cost_idr", label: "Fixed cost (total)", prefix: "Rp", hint: (f) => `Rate card ${f.rate_card.code}: setup, creative and reporting.` },
  { key: "proposed_fee_idr", label: "Proposed fee (total)", prefix: "Rp", hint: () => "Defaults to the client's stated budget." },
  { key: "duration_weeks", label: "Duration (weeks)", hint: () => "From the confirmed timeline." },
];

type Raw = Record<string, string>;
const toRaw = (inputs: Record<string, number | null>): Raw =>
  Object.fromEntries(FIELDS.map((f) => [f.key, inputs[f.key] === null || inputs[f.key] === undefined ? "" : int(inputs[f.key])]));
const toInputs = (raw: Raw) => Object.fromEntries(FIELDS.map((f) => [f.key, parseWhole(raw[f.key] ?? "")]));

export function FeasibilityPage() {
  const { c } = useCase();
  const { user } = useSession();
  const [scenario, setScenario] = useState("expected");
  const q = useQuery({ queryKey: ["feasibility", c.code, scenario], queryFn: () => api.get<Feasibility>(`/cases/${c.code}/feasibility?scenario=${scenario}`) });
  const [raw, setRaw] = useState<Raw | null>(null);
  const [assumptions, setAssumptions] = useState("");
  const [exceptionReason, setExceptionReason] = useState("");
  useEffect(() => { if (q.data) { setRaw(toRaw(q.data.inputs)); setAssumptions((q.data.latest_run?.assumptions ?? []).join("\n")); } }, [q.data]);
  const inputs = raw ? toInputs(raw) : null;
  const [debounced, setDebounced] = useState(inputs);
  const key = JSON.stringify(inputs);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { const t = setTimeout(() => setDebounced(inputs), 300); return () => clearTimeout(t); }, [key]);
  const preview = useQuery({
    queryKey: ["preview", c.code, JSON.stringify(debounced)],
    queryFn: () => api.post<Assessment>(`/cases/${c.code}/feasibility/preview`, { scenario, inputs: debounced }),
    enabled: !!debounced, placeholderData: (prev) => prev,
  });
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const save = useMutation({
    mutationFn: () => api.post(`/cases/${c.code}/feasibility`, { scenario, inputs, assumptions: assumptions.split("\n"),
      based_on_run_id: q.data?.latest_run?.id ?? null, check_base: true }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["feasibility", c.code] }); qc.invalidateQueries({ queryKey: caseKey(c.code) }); qc.invalidateQueries({ queryKey: ["cases"] }); toast("Calculation saved with rate card version and formula."); },
  });
  const createPkg = useMutation({
    mutationFn: () => api.post<PackageSummary>(`/cases/${c.code}/packages`, { exception_reason: exceptionReason || null }),
    onSuccess: (p) => { qc.invalidateQueries(); toast(`Decision package v${p.version} frozen and sent for review.`); nav(`/approvals/${p.id}`); },
  });
  if (q.isLoading || !raw) return <LoadingRows rows={8} label="Loading pricing" />;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const f = q.data;
  const a = preview.data ?? f.assessment;
  const r = a.result;
  const issues = Object.fromEntries(r.issues.map((i) => [i.field, i.message]));
  const latest = f.latest_run;
  const unsaved = !latest || latest.scenario !== scenario || JSON.stringify(latest.inputs) !== JSON.stringify(inputs) ||
    (latest.assumptions.join("\n") !== assumptions.split("\n").map((s) => s.trim()).filter(Boolean).join("\n"));
  const reqBlockers = a.blockers.filter((b) => b.code === "REQUIREMENT_NOT_CONFIRMED");
  const otherBlockers = a.blockers.filter((b) => b.code !== "REQUIREMENT_NOT_CONFIRMED" && !b.code.startsWith("INPUT_"));
  const belowFloor = r.valid && (r.margin_bp ?? 0) < f.rate_card.margin_floor_bp;
  const needsException = belowFloor && exceptionReason.trim().length < 20;
  const locked = !!f.lock_reason;
  const canPackage = !unsaved && a.blockers.length === 0 && can(user, "package.create") && !locked && !needsException;
  const conflict = save.error instanceof ApiError && save.error.code === "VERSION_CONFLICT";
  const activePkg = c.latest_package && ["IN_REVIEW", "APPROVED", "CHANGES_REQUESTED"].includes(c.latest_package.state) ? c.latest_package : null;
  const busy = preview.isFetching;
  return (
    <div className="stack">
      <div className="row wrap between">
        <div className="row wrap" style={{ gap: 12 }}>
          <h2 style={{ fontSize: 22, fontWeight: 650 }}>Feasibility & pricing</h2>
          {a.blockers.length > 0
            ? <Badge tone="warning" icon={<AlertTriangle size={14} aria-hidden="true" />}>Clarification required before approval</Badge>
            : <Badge tone="success" icon={<CheckCircle2 size={14} aria-hidden="true" />}>Ready for a decision package</Badge>}
        </div>
        <div className="small muted">Rate card <span className="mono">{f.rate_card.code}</span> · valid {dateOnly(f.rate_card.valid_from)} – {dateOnly(f.rate_card.valid_to)} · <SyntheticTag text="Illustrative rates" /></div>
      </div>

      <div className="row wrap" role="group" aria-label="Scenario">
        {Object.entries(f.scenarios).map(([k, s]) => (
          <button key={k} className="chip" aria-pressed={scenario === k} onClick={() => { setScenario(k); setRaw(null); }} title={s.description}>{s.label}</button>
        ))}
        <span className="small muted">{f.scenarios[scenario].description}</span>
      </div>

      {f.rate_card.expired && <Callout tone="critical" title={`Rate card ${f.rate_card.code} has expired.`}>Pricing is blocked until an admin publishes a current version.</Callout>}
      {activePkg && <Callout tone="info" title={`Package v${activePkg.version} is ${activePkg.state.toLowerCase().replace("_", " ")}.`}>Saving a different calculation invalidates it; a new version and a new review will be required.</Callout>}

      <div className="grid-2 even">
        <Panel title="Pricing inputs" subtitle="Assumptions you can change. Values are whole rupiah." id="inputs-title">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} noValidate>
            {FIELDS.map((fd) => {
              const id = `in-${fd.key}`;
              const err = issues[fd.key] ?? (raw[fd.key] !== "" && parseWhole(raw[fd.key]) === null ? "Enter a whole number." : undefined);
              const fromDefault = f.defaults[fd.key] !== null && parseWhole(raw[fd.key]) === f.defaults[fd.key];
              return (
                <div key={fd.key} className="field" style={{ display: "grid", gridTemplateColumns: "minmax(150px, 1fr) minmax(160px, 1fr)", alignItems: "center", gap: "4px 16px" }}>
                  <label htmlFor={id}>{fd.label}</label>
                  <div className={fd.prefix ? "input-affix" : ""}>
                    {fd.prefix && <span className="prefix" aria-hidden="true">{fd.prefix}</span>}
                    <input id={id} className="input num" inputMode="numeric" value={raw[fd.key]} aria-invalid={!!err}
                      aria-describedby={`${id}-hint${err ? ` ${id}-err` : ""}`}
                      onChange={(e) => setRaw({ ...raw, [fd.key]: e.target.value })} disabled={!can(user, "feasibility.run") || locked} />
                  </div>
                  <span id={`${id}-hint`} className="hint" style={{ gridColumn: "1 / -1" }}>{fromDefault ? fd.hint(f) : "Changed from the default — recorded when you save."}</span>
                  {err && <span id={`${id}-err`} className="error" style={{ gridColumn: "1 / -1" }}><XCircle size={14} aria-hidden="true" />{err}</span>}
                </div>
              );
            })}
            <div className="field">
              <label htmlFor="assumptions">Additional assumptions (one per line)</label>
              <textarea id="assumptions" className="textarea" style={{ minHeight: 70 }} value={assumptions} onChange={(e) => setAssumptions(e.target.value)}
                disabled={!can(user, "feasibility.run") || locked} placeholder="e.g. Client supplies creative assets in week 1" />
            </div>
          </form>
        </Panel>

        <Panel title="Calculated results" subtitle={`Computed by the server with integer rupiah (${r.formula_version}). Not produced by AI.`}
          actions={busy ? <span className="small muted row"><Loader2 size={14} className="spin" aria-hidden="true" />Recalculating…</span> : null}>
          <div aria-live="polite" aria-busy={busy}>
            {!r.valid ? (
              <Callout tone="warning" title="Cannot calculate yet.">Fix the highlighted inputs: {r.issues.map((i) => i.message).join(" ")}</Callout>
            ) : (
              <table className="table" style={{ fontSize: 15 }}>
                <tbody>
                  <tr><th scope="row" style={{ background: "none", position: "static" }}>Variable cost<div className="xs muted" style={{ fontWeight: 400 }}>Target × unit cost</div></th><td className="right mono" style={{ fontSize: 17, fontWeight: 600 }}>{idr(r.variable_cost_idr)}</td></tr>
                  <tr><th scope="row" style={{ background: "none", position: "static" }}>Total estimated cost<div className="xs muted" style={{ fontWeight: 400 }}>Variable cost + fixed cost</div></th><td className="right mono" style={{ fontSize: 17, fontWeight: 600 }}>{idr(r.total_cost_idr)}</td></tr>
                  <tr><th scope="row" style={{ background: "none", position: "static" }}>Gross profit<div className="xs muted" style={{ fontWeight: 400 }}>Proposed fee − total cost</div></th><td className="right mono" style={{ fontSize: 17 }}>{idr(r.gross_profit_idr)}</td></tr>
                  <tr><th scope="row" style={{ background: "none", position: "static" }}>Estimated gross margin<div className="xs muted" style={{ fontWeight: 400 }}>(Fee − total cost) ÷ fee · floor {f.rate_card.margin_floor_pct}</div></th>
                    <td className="right"><span className="mono" style={{ fontSize: 22, fontWeight: 700, color: (r.margin_bp ?? 0) < f.rate_card.margin_floor_bp ? "var(--critical)" : "var(--brand-strong)" }}>{pct(r.margin_bp)}</span></td></tr>
                </tbody>
              </table>
            )}
            <details style={{ marginTop: 12 }}>
              <summary className="small" style={{ cursor: "pointer", fontWeight: 600 }}>View calculation trace</summary>
              <ol className="mono xs" style={{ margin: "8px 0 0", paddingLeft: 18 }}>{r.trace.map((t) => <li key={t}>{t}</li>)}</ol>
            </details>
            <p className="small muted" style={{ marginTop: 10 }}>Margin is before overhead and delivery risk. A positive margin does not prove the work is operationally feasible.</p>
          </div>
        </Panel>
      </div>

      <div className="grid-2 even">
        <Panel title="Capacity check" subtitle={`Delivery capacity from rate card ${f.rate_card.code}: ${int(f.rate_card.capacity_leads_per_week)} verified qualified leads per week.`}>
          {a.capacity ? (
            <div className="stack tight">
              <div className="row between"><span>Required per week</span><strong className="mono">{int(a.capacity.required_per_week)}</strong></div>
              <div className="util-track" role="img" aria-label={`Utilization ${a.capacity.utilization_pct}%`}>
                <div className="util-fill" style={{ width: `${Math.min(100, a.capacity.utilization_pct)}%`, background: a.capacity.utilization_pct > 100 ? "var(--critical)" : a.capacity.utilization_pct > 85 ? "var(--warning)" : undefined }} />
              </div>
              <div className="small muted">{a.capacity.utilization_pct}% of weekly capacity{a.capacity.utilization_pct > 100 ? " — not feasible as scoped" : a.capacity.utilization_pct > 85 ? " — tight; little room for slippage" : ""}.</div>
            </div>
          ) : <p className="small muted">Enter valid inputs to check capacity.</p>}
        </Panel>
        <Panel title="Scenario comparison" subtitle="Same target, fee and duration; only the unit cost changes." flush>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Scenario</th><th className="right">Unit cost</th><th className="right">Total cost</th><th className="right">Margin</th></tr></thead>
            <tbody>{Object.entries(a.scenario_comparison).map(([k, o]) => (
              <tr key={k} className={k === scenario ? "selected" : ""}>
                <td>{o.label}{k === scenario && <span className="xs muted"> · selected</span>}</td>
                <td className="right mono">{idr(o.unit_cost_idr)}</td><td className="right mono">{idr(o.total_cost_idr)}</td>
                <td className="right mono" style={{ color: o.below_floor ? "var(--critical)" : undefined }}>{o.margin_pct ?? "—"}{o.below_floor && " ▼"}</td>
              </tr>))}</tbody>
          </table></div>
        </Panel>
      </div>

      <Panel title="Operational readiness" subtitle="Everything that must be true before a decision package can go to approval.">
        <div className="stack tight">
          {c.requirements.filter((x) => x.critical).map((x) => (
            <div key={x.key} className="row between" style={{ borderBottom: "1px solid var(--hairline)", padding: "8px 0" }}>
              <span style={{ fontWeight: 600 }}>{x.label}</span>
              <span className="row" style={{ gap: 12 }}>
                {x.state !== "CONFIRMED" && <Link className="small" to="../requirements">Resolve</Link>}
                <StatusBadge status={x.state} />
              </span>
            </div>
          ))}
          {[...otherBlockers, ...a.warnings].map((b) => (
            <Callout key={b.code} tone={a.warnings.includes(b) ? "warning" : "critical"}>{b.message}</Callout>
          ))}
          {reqBlockers.length > 0 && <p className="small muted"><Info size={14} aria-hidden="true" style={{ verticalAlign: -2 }} /> Cost calculation is valid as a simulation, but {reqBlockers.length} critical requirement{reqBlockers.length > 1 ? "s remain" : " remains"} unresolved.</p>}
        </div>
      </Panel>

      {belowFloor && can(user, "package.create") && !locked && (
        <Panel title="Margin exception request" subtitle={`Margin ${pct(r.margin_bp)} is below the ${f.rate_card.margin_floor_pct} floor. The package will be high risk and needs two different approvers.`}>
          <div className="field">
            <label htmlFor="exception">Why should this still be approved? (20+ characters)</label>
            <textarea id="exception" className="textarea" style={{ minHeight: 70 }} value={exceptionReason} onChange={(e) => setExceptionReason(e.target.value)} aria-describedby="exception-hint" />
            <span id="exception-hint" className="hint">Included in the frozen package and shown to both approvers.</span>
          </div>
        </Panel>
      )}
      {conflict ? (
        <Callout tone="critical" title="Someone saved a newer calculation.">
          Reload to see it before saving yours. <button className="btn btn-ghost btn-sm" onClick={() => { save.reset(); q.refetch(); }}>Reload</button>
        </Callout>
      ) : save.error ? <ErrorMessage error={save.error} /> : null}
      {createPkg.error ? <ErrorMessage error={createPkg.error} /> : null}
      <div className="row wrap" style={{ justifyContent: "flex-end" }}>
        {latest && <span className="small muted" style={{ marginRight: "auto" }}>Last saved {relative(latest.created_at)} by {latest.created_by.name} · {f.scenarios[latest.scenario].label} · {dateTime(latest.created_at)}{unsaved && " · unsaved changes"}</span>}
        {can(user, "feasibility.run") && (
          <button className="btn btn-secondary btn-lg" onClick={() => save.mutate()} disabled={save.isPending || !r.valid || locked || !unsaved}>
            {save.isPending ? "Saving…" : unsaved ? "Save calculation" : "Saved"}
          </button>
        )}
        <button className="btn btn-primary btn-lg" onClick={() => createPkg.mutate()} disabled={!canPackage || createPkg.isPending}
          aria-describedby="pkg-why">
          <FileCheck2 size={18} aria-hidden="true" />{createPkg.isPending ? "Freezing…" : "Create decision package"}
        </button>
      </div>
      <p id="pkg-why" className="small muted" style={{ textAlign: "right", marginTop: -8 }}>
        {!can(user, "package.create") ? "Only a Deal Desk Analyst can create packages." :
          locked ? `Locked: ${f.lock_reason}` :
            unsaved ? "Save the calculation first; the package uses the saved version." :
              needsException ? "Write the margin exception request above (20+ characters)." :
              a.blockers.length ? `Blocked: ${a.blockers.map((b) => b.message).join(" ")}` :
                <>Freezes the current requirements and pricing into an immutable, hashed snapshot for review. <ArrowRight size={12} aria-hidden="true" /></>}
      </p>
      <p className="xs faint">Target {int(inputs?.target_units ?? null)} · Fee {idr(inputs?.proposed_fee_idr ?? null)} · demo rate card values are illustrative, not market prices.</p>
    </div>
  );
}
