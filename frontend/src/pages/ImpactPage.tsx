import { useQuery } from "@tanstack/react-query";
import { Download, Info, Users } from "lucide-react";
import { api } from "../api";
import { Callout, ErrorState, LoadingRows, Panel, SyntheticTag } from "../components/ui";

type Point = { month: string; median_days: number; n: number; insufficient_sample: boolean };
type Cohort = {
  available: boolean; generator: string; data_through: string;
  periods: Record<string, { label: string; start: string; end: string }>;
  cycle_time: { definition: string; series: Record<string, Point[]>; baseline_manual: { median_days: number; n: number };
    assisted_flow: { median_days: number; n: number }; concurrent_manual: { median_days: number; n: number }; min_sample: number };
  funnel: { definition: string; steps: { key: string; label: string; n: number }[] };
  adoption_rate: number; adoption_rate_definition: string;
  user_adoption: { definition: string; eligible_users: number; adopted_users: number; rate: number;
    monthly: { month: string; eligible_users: number; adopted_users: number; rate: number }[] };
  override: { definition: string; n: number; of: number; rate: number; reasons: [string, number][] };
  workflow_status: { definition: string; counts: Record<string, number> };
  caveats: string[];
};
type Live = { cases_by_status: Record<string, number>; runs_by_status: Record<string, number>; analyst_value_overrides: number; cases: number;
  cases_with_human_review: number; cycle_time: { median_days: number | null; n: number; insufficient_sample: boolean };
  user_adoption: { active_analysts: number; analysts: number } };

const SERIES = [
  { key: "baseline_manual", label: "Baseline period — manual", color: "#7b8a86", dash: "6 5" },
  { key: "assisted_manual", label: "Assisted period — still manual", color: "#a36539", dash: "2 4" },
  { key: "assisted_assisted", label: "Assisted period — assisted flow", color: "#086c5a", dash: "" },
];
const MONTH = (m: string) => new Date(`${m}-15T00:00:00Z`).toLocaleString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

function CycleChart({ series }: { series: Record<string, Point[]> }) {
  const months = Array.from(new Set(Object.values(series).flat().map((p) => p.month))).sort();
  const W = 640, H = 270, L = 44, R = 36, T = 28, B = 34;
  const ymax = Math.ceil(Math.max(...Object.values(series).flat().map((p) => p.median_days), 10) / 2) * 2;
  const x = (m: string) => L + (months.indexOf(m) / Math.max(1, months.length - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v / ymax) * (H - T - B);
  const ticks = Array.from({ length: ymax / 2 + 1 }, (_, i) => i * 2);
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Median decision cycle time per month. The data table below has the same values.">
        {ticks.map((t) => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#e3e8e4" /><text x={L - 8} y={y(t) + 4} fontSize="11" textAnchor="end" fill="#52625f">{t}</text></g>)}
        {months.map((m) => <text key={m} x={x(m)} y={H - 10} fontSize="11" textAnchor="middle" fill="#52625f">{MONTH(m)}</text>)}
        <text x={L - 8} y={12} fontSize="11" textAnchor="end" fill="#52625f">days</text>
        {SERIES.map((s) => {
          const pts = series[s.key] ?? [];
          if (!pts.length) return null;
          return (
            <g key={s.key}>
              <polyline fill="none" stroke={s.color} strokeWidth={2.5} strokeDasharray={s.dash} points={pts.map((p) => `${x(p.month)},${y(p.median_days)}`).join(" ")} />
              {pts.map((p) => (
                <g key={p.month}>
                  <circle cx={x(p.month)} cy={y(p.median_days)} r={4.5} fill={p.insufficient_sample ? "#fff" : s.color} stroke={s.color} strokeWidth={2} />
                  <title>{`${s.label}, ${MONTH(p.month)}: median ${p.median_days} days (n=${p.n}${p.insufficient_sample ? ", insufficient sample" : ""})`}</title>
                </g>))}
            </g>);
        })}
      </svg>
      <figcaption className="legend">
        {SERIES.map((s) => <span key={s.key}><svg width="22" height="6" aria-hidden="true"><line x1="0" x2="22" y1="3" y2="3" stroke={s.color} strokeWidth="2.5" strokeDasharray={s.dash} /></svg>{s.label}</span>)}
        <span><svg width="10" height="10" aria-hidden="true"><circle cx="5" cy="5" r="4" fill="#fff" stroke="#52625f" strokeWidth="1.5" /></svg>Hollow = insufficient sample</span>
      </figcaption>
    </figure>
  );
}

export function ImpactPage() {
  const q = useQuery({ queryKey: ["impact"], queryFn: () => api.get<{ cohort: Cohort; live: Live }>("/impact/summary") });
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Transformation impact</h1>
          <p className="page-sub">Process outcomes against a manual baseline — with definitions, sample sizes and limits shown next to every number.</p>
        </div>
        <div className="row"><SyntheticTag text="Synthetic demonstration" />
          <a className="btn btn-secondary btn-sm" href="/api/v1/impact/export.csv" download><Download size={14} aria-hidden="true" />Export cohort CSV</a></div>
      </div>
      {q.isLoading ? <LoadingRows rows={8} /> : q.error || !q.data ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !q.data.cohort.available ? (
        <Callout tone="info" title="No baseline loaded.">Run the seed script to generate the synthetic cohort.</Callout>
      ) : (() => {
        const c = q.data.cohort;
        const ct = c.cycle_time;
        return (
          <div className="stack">
            <div className="row wrap small muted" style={{ gap: 20 }}>
              <span><strong>Baseline:</strong> {c.periods.baseline.label}, {c.periods.baseline.start} – {c.periods.baseline.end}</span>
              <span><strong>Comparison:</strong> {c.periods.assisted.label}, {c.periods.assisted.start} – {c.periods.assisted.end}</span>
              <span>Data through {c.data_through}</span>
            </div>
            <div className="panel">
              <div className="metric-row" style={{ borderTop: 0 }}>
                <div className="metric"><div className="label">Median cycle time — baseline</div><div className="value">{ct.baseline_manual.median_days} days</div><div className="sub">n = {ct.baseline_manual.n} decided cases</div></div>
                <div className="metric"><div className="label">Median — assisted flow</div><div className="value" style={{ color: "var(--brand-strong)" }}>{ct.assisted_flow.median_days} days</div><div className="sub">n = {ct.assisted_flow.n}</div></div>
                <div className="metric"><div className="label">Median — concurrent manual</div><div className="value">{ct.concurrent_manual.median_days} days</div><div className="sub">n = {ct.concurrent_manual.n} · partial control group</div></div>
                <div className="metric"><div className="label">Adoption — people</div><div className="value">{(c.user_adoption.rate * 100).toFixed(0)}%</div><div className="sub">{c.user_adoption.adopted_users} of {c.user_adoption.eligible_users} eligible analysts</div></div>
                <div className="metric"><div className="label">Adoption — cases</div><div className="value">{(c.adoption_rate * 100).toFixed(1)}%</div><div className="sub">eligible cases handled in assisted flow</div></div>
                <div className="metric"><div className="label">Human override rate</div><div className="value">{(c.override.rate * 100).toFixed(1)}%</div><div className="sub">{c.override.n} of {c.override.of} reviewed cases</div></div>
              </div>
            </div>

            <div className="grid-2">
              <Panel title="Decision cycle time" subtitle={ct.definition}>
                <CycleChart series={ct.series} />
                <details style={{ marginTop: 10 }}>
                  <summary className="small" style={{ cursor: "pointer", fontWeight: 600 }}>Show data table</summary>
                  <div className="table-wrap"><table className="table">
                    <thead><tr><th>Series</th><th>Month</th><th className="right">Median days</th><th className="right">n</th></tr></thead>
                    <tbody>{SERIES.flatMap((s) => (ct.series[s.key] ?? []).map((p) => (
                      <tr key={s.key + p.month}><td className="small">{s.label}</td><td className="small">{MONTH(p.month)}</td><td className="right mono">{p.median_days}</td><td className="right mono">{p.n}{p.insufficient_sample && " ⚠"}</td></tr>)))}</tbody>
                  </table></div>
                </details>
              </Panel>
              <Panel title="Metrics, definitions & sample sizes">
                <dl className="kv small">
                  <dt>Decision cycle time</dt><dd>{ct.definition}</dd>
                  <dt>Adoption (people)</dt><dd>{c.user_adoption.definition}</dd>
                  <dt>Adoption (cases)</dt><dd>{c.adoption_rate_definition}</dd>
                  <dt>Human override</dt><dd>{c.override.definition}</dd>
                  <dt>Workflow status</dt><dd>{c.workflow_status.definition}</dd>
                  <dt>Minimum sample</dt><dd>{ct.min_sample} decided cases per month; smaller months are marked.</dd>
                  <dt>Source</dt><dd>Synthetic cohort — {c.generator}</dd>
                </dl>
              </Panel>
            </div>

            <Panel title="Adoption by people, per month" subtitle="Analysts who used the assisted flow at least once ÷ analysts who handled any case that month." flush>
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Month</th><th className="right">Eligible analysts</th><th className="right">Used assisted flow</th><th className="right">Rate</th></tr></thead>
                <tbody>{c.user_adoption.monthly.map((m) => <tr key={m.month}><td>{MONTH(m.month)}</td><td className="right mono">{m.eligible_users}</td><td className="right mono">{m.adopted_users}</td><td className="right mono">{(m.rate * 100).toFixed(0)}%</td></tr>)}</tbody>
              </table></div>
            </Panel>
            <div className="grid-2">
              <Panel title="Adoption funnel" subtitle={c.funnel.definition}>
                <div className="funnel">
                  {c.funnel.steps.map((s, i) => (
                    <div key={s.key} className="funnel-step">
                      <div className="small" style={{ fontWeight: 600 }}>{s.label}</div>
                      <div className="n">{s.n.toLocaleString()}</div>
                      {i > 0 && <div className="xs">{((s.n / c.funnel.steps[0].n) * 100).toFixed(1)}% of eligible</div>}
                    </div>))}
                </div>
              </Panel>
              <Panel title="Human override reasons" actions={<Users size={18} aria-hidden="true" color="var(--brand)" />} subtitle="Overrides are tracked to learn from, not counted as failures.">
                <div className="bars">
                  {c.override.reasons.map(([reason, n]) => (
                    <div key={reason} className="bar-row"><span>{reason}</span><span className="bar-track"><span className="bar-fill" style={{ width: `${(n / Math.max(...c.override.reasons.map((r) => r[1]))) * 100}%`, display: "block", background: "var(--copper)" }} /></span><span className="mono right">{n}</span></div>))}
                </div>
                <div className="divider" />
                <div className="section-title">Workflow status (approved assisted cases)</div>
                <div className="row wrap small">{Object.entries(c.workflow_status.counts).map(([k, n]) => <span key={k} className="badge neutral">{k.replace("_", " ").toLowerCase()}: {n}</span>)}</div>
              </Panel>
            </div>

            <Callout tone="info" icon={<Info size={18} aria-hidden="true" />} title="Association does not prove causation.">
              <ul>{c.caveats.map((x) => <li key={x}>{x}</li>)}</ul>
            </Callout>
            <Panel title="Live counts from this demo database" subtitle="Real counts of the demo cases you can open in this app — separate from the synthetic cohort above.">
              <div className="metric-row" style={{ border: "1px solid var(--hairline)", borderRadius: 8, marginBottom: 12 }}>
                <div className="metric"><div className="label">Median cycle time (live)</div><div className="value">{q.data.live.cycle_time.median_days ?? "—"}{q.data.live.cycle_time.median_days !== null && " days"}</div>
                  <div className="sub">n = {q.data.live.cycle_time.n}{q.data.live.cycle_time.insufficient_sample && " · insufficient sample — do not compare"}</div></div>
                <div className="metric"><div className="label">Analysts active</div><div className="value">{q.data.live.user_adoption.active_analysts}/{q.data.live.user_adoption.analysts}</div><div className="sub">changed at least one requirement</div></div>
                <div className="metric"><div className="label">Cases with human review</div><div className="value">{q.data.live.cases_with_human_review}</div><div className="sub">of {q.data.live.cases} demo cases</div></div>
              </div>
              <div className="row wrap small" style={{ gap: 10 }}>
                <span className="badge outline">{q.data.live.cases} cases</span>
                {Object.entries(q.data.live.cases_by_status).map(([k, n]) => <span key={k} className="badge neutral">{k.replace(/_/g, " ").toLowerCase()}: {n}</span>)}
                {Object.entries(q.data.live.runs_by_status).map(([k, n]) => <span key={k} className="badge info">run {k.replace(/_/g, " ").toLowerCase()}: {n}</span>)}
                <span className="badge copper">analyst value overrides: {q.data.live.analyst_value_overrides}</span>
              </div>
            </Panel>
          </div>
        );
      })()}
    </div>
  );
}
