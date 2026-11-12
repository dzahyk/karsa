import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Empty, ErrorState, LoadingRows, Panel, StatusBadge, SyntheticTag } from "../components/ui";
import { idr, relative } from "../format";
import { useSession } from "../session";
import type { PackageSummary } from "../types";

function PackageList({ items, empty }: { items: PackageSummary[]; empty: string }) {
  if (!items.length) return <p className="small muted" style={{ padding: "4px 20px 20px" }}>{empty}</p>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {items.map((p) => (
        <li key={p.id} style={{ borderTop: "1px solid var(--hairline)" }}>
          <Link to={`/approvals/${p.id}`} className="row wrap" style={{ padding: "14px 20px", color: "inherit", textDecoration: "none", gap: 16 }}>
            <div style={{ flex: "1 1 260px" }}>
              <div style={{ fontWeight: 650 }}>{p.case.client_name} — {p.case.title}</div>
              <div className="small muted"><span className="mono">{p.case.code}</span> · Package v{p.version} · prepared by {p.created_by.name} {relative(p.created_at)}</div>
            </div>
            <div className="row wrap" style={{ gap: 10 }}>
              <span className="mono small">{idr(p.fee_idr)}</span><span className="mono small">{p.margin_pct}</span>
              <StatusBadge status={p.risk_level} /><StatusBadge status={p.state} />
              {p.required_approvals > 1 && p.approvals_count !== undefined && <span className="badge outline">{p.approvals_count} of {p.required_approvals} approvals{p.approved_by_me ? " · you approved" : ""}</span>}
              <ArrowRight size={16} aria-hidden="true" color="var(--ink-faint)" />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function ApprovalsPage() {
  const { user } = useSession();
  const q = useQuery({ queryKey: ["approvals"], queryFn: () => api.get<{ pending: PackageSummary[]; awaiting_authorization: PackageSummary[]; recent: PackageSummary[] }>("/approvals"), refetchInterval: 30_000 });
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Approvals</h1>
          <p className="page-sub">Decision packages waiting for a human decision, and approved decisions waiting for execution authorization.</p>
        </div>
        <SyntheticTag />
      </div>
      {user && user.role !== "APPROVER" && (
        <div className="callout info" style={{ marginBottom: 16 }}>You are acting as {user.name} ({user.role_label}). You can read packages; only a Commercial Manager can decide. Switch role in the header to try approval.</div>
      )}
      {q.isLoading ? <LoadingRows /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
        <div className="stack">
          <Panel title={`Pending review (${q.data!.pending.length})`} flush>
            {q.data!.pending.length ? <PackageList items={q.data!.pending} empty="" /> : <Empty title="Inbox clear">No packages are waiting for review.</Empty>}
          </Panel>
          <Panel title={`Approved — waiting for execution authorization (${q.data!.awaiting_authorization.length})`} subtitle="Approval confirms the decision. Authorizing execution is a separate, explicit step." flush>
            <PackageList items={q.data!.awaiting_authorization} empty="Nothing waiting for authorization." />
          </Panel>
          <Panel title="Recent decisions" flush><PackageList items={q.data!.recent} empty="No decisions yet." /></Panel>
        </div>
      )}
    </div>
  );
}
