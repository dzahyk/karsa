import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorState, LoadingRows, Panel, StatusBadge, SyntheticTag } from "../components/ui";
import { dateTime, idr, relative } from "../format";
import type { Incident, PackageSummary, RunSummary } from "../types";

type Row = RunSummary & { case: { code: string; title: string; client_name: string }; package_version: number };

export function WorkflowsPage() {
  const q = useQuery({ queryKey: ["runs"], queryFn: () => api.get<{ items: Row[]; ready: PackageSummary[]; incidents: Incident[] }>("/runs"), refetchInterval: 15_000 });
  const nav = useNavigate();
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Workflows</h1>
          <p className="page-sub">Controlled execution of approved, authorized decision packages against sandbox connectors.</p>
        </div>
        <SyntheticTag text="Sandbox connectors only" />
      </div>
      {q.isLoading ? <LoadingRows /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="stack">
          <Panel title={`Exception queue (${q.data!.incidents.filter((i) => i.status === "OPEN").length} open)`} subtitle="Runs that need a human: escalations, exhausted retries and cancellations with compensation." flush>
            {q.data!.incidents.length === 0 ? <p className="small muted" style={{ padding: "0 20px 20px" }}>No incidents.</p> : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>{q.data!.incidents.map((i) => (
                <li key={i.id} className="row wrap between" style={{ borderTop: "1px solid var(--hairline)", padding: "12px 20px" }}>
                  <span><StatusBadge status={i.status === "OPEN" ? "FAILED" : "SUCCEEDED"} label={i.status === "OPEN" ? "Open" : "Resolved"} />{" "}
                    <strong>#{i.id} {i.title}</strong> <span className="small muted mono">{i.case_code} · {i.run_code}</span>
                    <div className="small muted">{i.detail} · {relative(i.created_at)}</div></span>
                  {i.run_code && <Link className="btn btn-secondary btn-sm" to={`/workflows/${i.run_code}`}>Open run</Link>}
                </li>))}</ul>
            )}
          </Panel>
          <Panel title={`Ready to run (${q.data!.ready.length})`} subtitle="Approved and authorized; no run started yet." flush>
            {q.data!.ready.length === 0 ? <p className="small muted" style={{ padding: "0 20px 20px" }}>Nothing is waiting. Packages appear here after an approver authorizes execution.</p> : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>{q.data!.ready.map((p) => (
                <li key={p.id} className="row wrap between" style={{ borderTop: "1px solid var(--hairline)", padding: "12px 20px" }}>
                  <span><strong>{p.case.client_name} — {p.case.title}</strong> <span className="small muted mono">{p.case.code} · v{p.version} · {idr(p.fee_idr)}</span></span>
                  <Link className="btn btn-primary btn-sm" to={`/approvals/${p.id}`}>Open & run</Link>
                </li>))}</ul>
            )}
          </Panel>
          <Panel title="Execution runs" flush>
            {q.data!.items.length === 0 ? <Empty title="No runs yet" /> : (
              <div className="table-wrap"><table className="table">
                <thead><tr><th>Run</th><th>Case</th><th>Status</th><th>Steps</th><th>Started (WIB)</th><th className="hide-mobile">Started by</th></tr></thead>
                <tbody>{q.data!.items.map((r) => (
                  <tr key={r.code} className="clickable" onClick={() => nav(`/workflows/${r.code}`)}>
                    <td><Link className="case-link" to={`/workflows/${r.code}`} onClick={(e) => e.stopPropagation()}>{r.code}</Link></td>
                    <td>{r.case.client_name} — {r.case.title}<div className="xs muted mono">{r.case.code} · package v{r.package_version}</div></td>
                    <td><StatusBadge status={r.status} label={r.status === "SUCCEEDED" ? "Verified" : undefined} /></td>
                    <td className="mono">{r.steps_done}/{r.steps_total}</td>
                    <td className="small">{dateTime(r.started_at)}</td>
                    <td className="small hide-mobile">{r.started_by.name}</td>
                  </tr>))}</tbody>
              </table></div>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
