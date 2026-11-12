import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Callout, Empty, ErrorState, LoadingRows, Panel, StatusBadge } from "../components/ui";
import { dateTime, idr, shortHash } from "../format";
import type { PackageSummary } from "../types";
import { useCase } from "./CaseLayout";

export function PackagePage() {
  const { c } = useCase();
  const q = useQuery({ queryKey: ["packages", c.code], queryFn: () => api.get<PackageSummary[]>(`/cases/${c.code}/packages`) });
  if (q.isLoading) return <LoadingRows label="Loading packages" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const list = q.data ?? [];
  const latest = list[0];
  return (
    <div className="stack">
      {latest?.state === "SUPERSEDED" && (
        <Callout tone="warning" title={`Package v${latest.version} was invalidated.`}>
          {latest.superseded_reason} Recalculate and create a new version from <Link to="../feasibility">Feasibility & pricing</Link>.
        </Callout>
      )}
      {latest && latest.state !== "SUPERSEDED" && (
        <Panel title={`Current package — v${latest.version}`} subtitle="Frozen snapshot. Any later change to requirements or pricing creates a new version and needs a new review."
          actions={<Link className="btn btn-primary" to={`/approvals/${latest.id}`}>Open review <ArrowRight size={16} aria-hidden="true" /></Link>}>
          <div className="row wrap" style={{ gap: 24 }}>
            <StatusBadge status={latest.state} /><StatusBadge status={latest.risk_level} />
            <span>Fee <strong className="mono">{idr(latest.fee_idr)}</strong></span>
            <span>Margin <strong className="mono">{latest.margin_pct}</strong></span>
            <span>Delivery <strong>{latest.duration_weeks} weeks</strong></span>
            <span className="hash">{latest.content_hash}</span>
          </div>
        </Panel>
      )}
      <Panel title="Version history" flush>
        {list.length === 0 ? (
          <Empty title="No decision package yet" action={<Link className="btn btn-primary" to="../feasibility">Go to feasibility & pricing</Link>}>
            A package is created from confirmed requirements and a saved pricing calculation.
          </Empty>
        ) : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Version</th><th>State</th><th>Fee</th><th>Margin</th><th>Snapshot hash</th><th>Prepared</th><th /></tr></thead>
            <tbody>{list.map((p) => (
              <tr key={p.id}>
                <td className="mono">v{p.version}</td><td><StatusBadge status={p.state} /></td>
                <td className="mono">{idr(p.fee_idr)}</td><td className="mono">{p.margin_pct}</td>
                <td className="hash" title={p.content_hash}>{shortHash(p.content_hash)}…</td>
                <td className="small">{p.created_by.name}<div className="xs muted">{dateTime(p.created_at)}</div></td>
                <td><Link to={`/approvals/${p.id}`}>View</Link></td>
              </tr>))}
            </tbody>
          </table></div>
        )}
      </Panel>
    </div>
  );
}
