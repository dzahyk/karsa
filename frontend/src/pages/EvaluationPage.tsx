import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ExternalLink, Play, Search, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, can } from "../api";
import { Badge, Callout, Dialog, Empty, ErrorMessage, ErrorState, Field, LoadingRows, Panel, StatusBadge, SyntheticTag, useToast } from "../components/ui";
import { dateTime } from "../format";
import { useSession } from "../session";

type Summary = {
  cases: number; passed: number; failed: number; pass_rate: number; pass_rate_ci95: [number, number] | null;
  field_precision: number; field_recall: number; field_f1: number; grounded_spans: number; total_spans: number;
  grounding_rate: number | null; calculation_exact: number; task_completion: number; task_completion_rate: number;
  task_completion_ci95: [number, number] | null; claim_cases: number; claims_caught: number;
  failures_by_category: Record<string, number>; note?: string; injection_cases: number; injections_caught: number;
};
type FullSummary = Summary & {
  splits: Record<string, Summary>; gate: { pass: boolean; applied_to: string; checks: { name: string; threshold: number; value: number | null; pass: boolean }[] };
  regressions: string[]; fixes: string[]; compared_to_run: number | null;
};
type Dataset = { id: number; name: string; version: string; description: string; manifest_hash: string; cases: number; synthetic: boolean; splits: Record<string, number> };
type RunRow = { id: number; dataset_id: number; extractor_version: string; provider: string; status: string; summary: FullSummary; started_by: { name: string }; started_at: string; duration_ms: number };
type Check = { check: string; expected: unknown; actual: unknown; pass: boolean };
type Result = { id: number; code: string; split: string; category: string; outcome: "PASS" | "FAIL"; failure_categories: string[]; checks: Check[]; brief: string;
  actual: { flags: { kind: string; quote: string }[] }; adjudication: string | null; adjudication_note: string | null; adjudicated_by: { name: string } | null };
type RunDetail = { id: number; summary: FullSummary; extractor_version: string; provider: string; started_at: string; duration_ms: number; started_by: { name: string };
  previous: { id: number; summary: FullSummary } | null; dataset: { name: string; version: string; manifest_hash: string }; categories: Record<string, string>;
  adjudications: Record<string, string>; results: Result[] };

const pc = (x: number | null | undefined, d = 0) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(d)}%`);
const PAGE = 8;

export function EvaluationPage() {
  const { user } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const datasetsQ = useQuery({ queryKey: ["datasets"], queryFn: () => api.get<{ datasets: Dataset[]; providers: Record<string, boolean> }>("/evaluations/datasets") });
  const datasets = { ...datasetsQ, data: datasetsQ.data?.datasets };
  const [provider, setProvider] = useState("demo");
  const [split, setSplit] = useState("heldout");
  const runs = useQuery({ queryKey: ["evalRuns"], queryFn: () => api.get<RunRow[]>("/evaluations/runs") });
  const [runId, setRunId] = useState<number | null>(null);
  const activeId = runId ?? runs.data?.[0]?.id ?? null;
  const detail = useQuery({ queryKey: ["evalRun", activeId], queryFn: () => api.get<RunDetail>(`/evaluations/runs/${activeId}`), enabled: activeId !== null });
  const ds = datasets.data?.[0];
  const start = useMutation({
    mutationFn: () => api.post<{ id: number; summary: Summary }>("/evaluations/runs", { dataset_id: ds!.id, provider }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["evalRuns"] }); setRunId(r.id); toast(`Evaluation run #${r.id} completed: ${r.summary.passed}/${r.summary.cases} cases passed.`); },
  });
  const [qText, setQText] = useState("");
  const [outcome, setOutcome] = useState("all");
  const [cat, setCat] = useState("all");
  const [page, setPage] = useState(0);
  const [trace, setTrace] = useState<Result | null>(null);
  useEffect(() => setPage(0), [qText, outcome, cat, activeId, split]);
  const filtered = useMemo(() => (detail.data?.results ?? []).filter((r) =>
    (split === "all" || r.split === split) &&
    (outcome === "all" || r.outcome === outcome) && (cat === "all" || r.failure_categories.includes(cat)) &&
    (!qText || `${r.code} ${r.category}`.toLowerCase().includes(qText.toLowerCase()))), [detail.data, outcome, cat, qText, split]);
  const full = detail.data?.summary;
  const s = full ? (split === "all" ? full : full.splits?.[split] ?? full) : undefined;
  const prevFull = detail.data?.previous?.summary;
  const prev = prevFull ? (split === "all" ? prevFull : prevFull.splits?.[split]) : undefined;
  const maxCat = Math.max(1, ...Object.values(s?.failures_by_category ?? { x: 1 }));
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Evaluation lab</h1>
          <p className="page-sub">Measure extraction, grounding, calculation and task completion on a frozen synthetic benchmark, with failures you can inspect.</p>
        </div>
        <SyntheticTag text="Synthetic benchmark" />
      </div>
      {datasets.isLoading || runs.isLoading ? <LoadingRows /> : datasets.error ? <ErrorState error={datasets.error} /> : !ds ? (
        <Empty title="No dataset loaded">Run the seed script to load the campaign brief benchmark.</Empty>
      ) : (
        <div className="stack">
          <section className="panel" style={{ padding: "16px 20px" }} aria-label="Dataset and run">
            <div className="row wrap" style={{ gap: 20 }}>
              <div style={{ flex: "1 1 300px" }}>
                <div className="label">Dataset</div>
                <div style={{ fontWeight: 650 }}>{ds.name} · {ds.version} · {ds.cases} cases</div>
                <div className="xs muted mono">manifest {ds.manifest_hash.slice(7, 19)}…</div>
              </div>
              <div className="row wrap" style={{ gap: 24 }}>
                <div><div className="label">Run</div>
                  <select className="select" style={{ width: "auto" }} aria-label="Evaluation run" value={activeId ?? ""} onChange={(e) => setRunId(Number(e.target.value))}>
                    {runs.data!.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.provider} · {dateTime(r.started_at)}</option>)}
                  </select></div>
                <div><div className="label">System under test</div><div className="mono small">{detail.data?.extractor_version ?? "—"}</div></div>
                {can(user, "eval.run") && <div><label className="label" htmlFor="provider">Provider</label>
                  <select id="provider" className="select" style={{ width: "auto" }} value={provider} onChange={(e) => setProvider(e.target.value)}>
                    <option value="demo">Demo rules (offline)</option>
                    <option value="anthropic" disabled={!datasetsQ.data?.providers.anthropic}>Claude{datasetsQ.data?.providers.anthropic ? "" : " — not configured"}</option>
                  </select></div>}
                {can(user, "eval.run") ? (
                  <button className="btn btn-primary" onClick={() => start.mutate()} disabled={start.isPending}><Play size={16} aria-hidden="true" />{start.isPending ? "Running…" : "Run evaluation"}</button>
                ) : <span className="small muted" style={{ maxWidth: 220 }}>Starting a run needs the AI Evaluation Analyst role.</span>}
              </div>
            </div>
            <p className="small muted" style={{ marginTop: 10 }}>{ds.description} Each run scores the selected extraction provider, the pricing engine and the action planner live on the server. The demo provider is rule-based, so repeated runs give the same result; a Claude run calls the API once per case and costs money.</p>
            {start.error ? <ErrorMessage error={start.error} /> : null}
          </section>

          {detail.isLoading || !s || !full ? <LoadingRows /> : (
            <>
              <div className="row wrap" role="group" aria-label="Split">
                {[["heldout", `Held-out (${ds.splits?.heldout ?? 0}) — honest score`], ["dev", `Dev (${ds.splits?.dev ?? 0}) — used for tuning`], ["all", "All"]].map(([k, l]) => (
                  <button key={k} className="chip" aria-pressed={split === k} onClick={() => setSplit(k)}>{l}</button>))}
              </div>
              <GatePanel full={full} />
              <div className="grid-2">
                <Panel title="Evaluation results" subtitle={`Run #${detail.data!.id} · ${dateTime(detail.data!.started_at)} · ${detail.data!.duration_ms} ms · by ${detail.data!.started_by.name}`} flush>
                  <div className="metric-row" style={{ gridAutoColumns: "minmax(0,1fr)" }}>
                    <div className="metric"><div className="label">Cases passed</div><div className="value">{s.passed}/{s.cases}</div>
                      <div className="sub">{pc(s.pass_rate)} · 95% CI {s.pass_rate_ci95 ? `${pc(s.pass_rate_ci95[0])}–${pc(s.pass_rate_ci95[1])}` : "—"}{prev && <> · prev {pc(prev.pass_rate)}</>}</div></div>
                    <div className="metric"><div className="label">Field F1</div><div className="value">{s.field_f1.toFixed(2)}</div><div className="sub">P {s.field_precision.toFixed(2)} · R {s.field_recall.toFixed(2)}</div></div>
                    <div className="metric"><div className="label">Task completion</div><div className="value">{s.task_completion}/{s.cases}</div><div className="sub">all required actions planned</div></div>
                  </div>
                  <div className="metric-row">
                    <div className="metric"><div className="label">Grounded spans</div><div className="value">{pc(s.grounding_rate)}</div><div className="sub">{s.grounded_spans}/{s.total_spans}; quotes are slices of the source by design</div></div>
                    <div className="metric"><div className="label">Unsupported claims caught</div><div className="value">{s.claims_caught}/{s.claim_cases}</div><div className="sub">claim cases flagged</div></div>
                    <div className="metric"><div className="label">Calculation exact</div><div className="value">{s.calculation_exact}/{s.cases}</div><div className="sub">vs hand-computed oracle</div></div>
                  </div>
                  <p className="xs muted" style={{ padding: "10px 20px 14px" }}>
                    {split === "dev" ? "Dev cases were used while writing the rules, so this score is optimistic. " : ""}
                    Small samples: intervals are wide and results hold only for this dataset version.
                    {full.compared_to_run && <> Compared with run #{full.compared_to_run}: {full.regressions.length} regression(s){full.regressions.length ? ` (${full.regressions.join(", ")})` : ""}, {full.fixes.length} fix(es).</>}
                  </p>
                </Panel>
                <Panel title="Failures by category" subtitle={`Cases with at least one failure of that type (of ${s.cases}).`}>
                  <div className="bars">
                    {Object.entries(s.failures_by_category).map(([k, n]) => (
                      <button key={k} className="bar-row" onClick={() => { setCat(cat === k ? "all" : k); setOutcome("all"); }}
                        style={{ background: cat === k ? "var(--brand-tint)" : "none", border: 0, padding: "4px 6px", borderRadius: 6, cursor: "pointer", textAlign: "left" }}
                        aria-pressed={cat === k} aria-label={`${detail.data!.categories[k]}: ${n} cases. Filter results.`}>
                        <span>{detail.data!.categories[k]}</span>
                        <span className="bar-track"><span className="bar-fill" style={{ width: `${(n / maxCat) * 100}%`, display: "block", background: n ? undefined : "transparent" }} /></span>
                        <span className="mono right">{n}</span>
                      </button>
                    ))}
                  </div>
                </Panel>
              </div>

              <Panel title={`Results (${filtered.length} of ${s.cases})`} flush
                actions={<div className="row wrap">
                  <select className="select" style={{ width: "auto" }} aria-label="Outcome" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                    <option value="all">All outcomes</option><option value="PASS">Pass</option><option value="FAIL">Fail</option>
                  </select>
                  <div className="search"><Search size={16} aria-hidden="true" /><input className="input" type="search" aria-label="Search results" placeholder="Search by case ID or category" value={qText} onChange={(e) => setQText(e.target.value)} /></div>
                </div>}>
                {filtered.length === 0 ? <Empty title="No results match these filters" /> : (
                  <div className="table-wrap"><table className="table">
                    <thead><tr><th>Case ID</th><th>Split</th><th>Test category</th><th>Outcome</th><th>Trace</th></tr></thead>
                    <tbody>{filtered.slice(page * PAGE, page * PAGE + PAGE).map((r) => (
                      <tr key={r.id}>
                        <td className="mono" style={{ color: "var(--brand)", fontWeight: 600 }}>{r.code}</td>
                        <td className="small">{r.split}</td>
                        <td>{r.category}{r.adjudication && <div><Badge tone="info">{detail.data!.adjudications[r.adjudication]}</Badge></div>}</td>
                        <td><StatusBadge status={r.outcome} label={r.outcome === "PASS" ? "Pass" : `Fail – ${r.failure_categories.map((c) => detail.data!.categories[c].toLowerCase()).join(", ")}`} /></td>
                        <td><button className="btn btn-ghost btn-sm" onClick={() => setTrace(r)}>Inspect trace <ExternalLink size={14} aria-hidden="true" /></button></td>
                      </tr>))}</tbody>
                  </table></div>
                )}
                <div className="row between" style={{ padding: "12px 16px", borderTop: "1px solid var(--hairline)" }}>
                  <span className="small muted">Showing {filtered.length ? page * PAGE + 1 : 0}–{Math.min(filtered.length, page * PAGE + PAGE)} of {filtered.length}</span>
                  <div className="row">
                    <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
                    <button className="btn btn-secondary btn-sm" disabled={(page + 1) * PAGE >= filtered.length} onClick={() => setPage(page + 1)}>Next</button>
                  </div>
                </div>
              </Panel>
              <Callout tone="info" title="What these numbers mean.">They measure a deterministic demo extractor on hand-written synthetic briefs. They are not a benchmark of any language model and do not predict performance on real client documents.</Callout>
            </>
          )}
        </div>
      )}
      {trace && detail.data && <TraceDialog r={trace} runId={detail.data.id} categories={detail.data.categories} adjudications={detail.data.adjudications} onClose={() => setTrace(null)} />}
    </div>
  );
}

function show(v: unknown): string {
  if (v === null || v === undefined) return "— (missing)";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${x}`).join(" · ");
  return String(v);
}

function GatePanel({ full }: { full: FullSummary }) {
  const g = full.gate;
  return (
    <section className={`callout ${g.pass ? "success" : "critical"}`} aria-label="Release gate">
      {g.pass ? <CheckCircle2 size={20} aria-hidden="true" /> : <XCircle size={20} aria-hidden="true" />}
      <div style={{ flex: 1 }}>
        <strong>Release gate {g.pass ? "passed" : "failed"}</strong> <span className="small">(applied to the {g.applied_to === "heldout" ? "held-out" : g.applied_to} split)</span>
        <ul className="small" style={{ margin: "6px 0 0" }}>
          {g.checks.map((c) => <li key={c.name}>{c.pass ? "✓" : "✗"} {c.name}: {c.value === null ? "—" : `${(c.value * 100).toFixed(1)}%`} (needs ≥ {(c.threshold * 100).toFixed(0)}%)</li>)}
        </ul>
        {!g.pass && <p className="small" style={{ marginTop: 6 }}>The demo rule set should not be promoted. Fixing it means changing rules and re-measuring on a <em>new</em> held-out set, not tuning to this one.</p>}
      </div>
    </section>
  );
}

function TraceDialog({ r, runId, categories, adjudications, onClose }: { r: Result; runId: number; categories: Record<string, string>; adjudications: Record<string, string>; onClose: () => void }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [status, setStatus] = useState(r.adjudication ?? "confirmed_failure");
  const [note, setNote] = useState(r.adjudication_note ?? "");
  const adj = useMutation({
    mutationFn: () => api.post(`/evaluations/results/${r.id}/adjudicate`, { status, note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["evalRun", runId] }); toast("Adjudication saved."); onClose(); },
  });
  return (
    <Dialog open onClose={onClose} title={`${r.code} — ${r.category}`} wide footer={<button className="btn btn-secondary" onClick={onClose}>Close</button>}>
      <div className="row wrap"><StatusBadge status={r.outcome} />{r.failure_categories.map((c) => <span key={c} className="badge critical">{categories[c]}</span>)}</div>
      <div><div className="section-title">Input brief (synthetic)</div><div className="doc" style={{ maxHeight: 180 }}>{r.brief}</div></div>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Check</th><th>Expected</th><th>Actual</th><th>Result</th></tr></thead>
        <tbody>{r.checks.map((c) => (
          <tr key={c.check}><td className="mono xs">{c.check}</td><td className="small">{show(c.expected)}</td><td className="small">{show(c.actual)}</td>
            <td><StatusBadge status={c.pass ? "PASS" : "FAIL"} /></td></tr>))}</tbody>
      </table></div>
      {r.actual.flags.length > 0 && <p className="small">Flags raised: {r.actual.flags.map((f) => `${f.kind} (“${f.quote}”)`).join("; ")}</p>}
      <p className="xs muted">The trace shows inputs, outputs and checks only. No model reasoning is stored.</p>
      {r.adjudication && <Callout tone="info" title={`Adjudicated: ${adjudications[r.adjudication]}`}>{r.adjudication_note} — {r.adjudicated_by?.name}</Callout>}
      {r.outcome === "FAIL" && can(user, "eval.adjudicate") && (
        <form className="stack tight" onSubmit={(e) => { e.preventDefault(); adj.mutate(); }}>
          <div className="section-title">Human adjudication</div>
          <Field label="Verdict">{({ id }) => <select id={id} className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(adjudications).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</Field>
          <Field label="Note (5+ characters)">{({ id }) => <textarea id={id} className="textarea" style={{ minHeight: 60 }} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
          <div><button className="btn btn-primary btn-sm" disabled={adj.isPending || note.trim().length < 5}>Save adjudication</button></div>
          {adj.error ? <ErrorMessage error={adj.error} /> : null}
        </form>
      )}
    </Dialog>
  );
}
