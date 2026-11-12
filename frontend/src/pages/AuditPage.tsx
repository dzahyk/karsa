import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { ErrorState, LoadingRows, Panel } from "../components/ui";
import type { AuditEvent } from "../types";
import { AuditTable } from "./ActivityPage";

const PAGE = 50;
const FILTERS = [["", "All events"], ["security.", "Security"], ["package.", "Packages & approvals"], ["execution.", "Authorization"],
  ["workflow.", "Workflow runs"], ["incident.", "Incidents"], ["requirement.", "Requirements"], ["auth.", "Sign-ins"],
  ["rate_card.", "Rate cards"], ["connector.", "Connectors"], ["eval.", "Evaluation"]];

export function AuditPage() {
  const [verb, setVerb] = useState("");
  const [page, setPage] = useState(0);
  const q = useQuery({
    queryKey: ["audit", verb, page],
    queryFn: () => api.get<{ items: (AuditEvent & { request_id: string | null })[]; total: number }>(
      `/audit?limit=${PAGE}&offset=${page * PAGE}${verb ? `&verb=${encodeURIComponent(verb)}` : ""}`),
  });
  return (
    <div className="page">
      <div className="page-head"><div>
        <h1 className="page-title">Audit log</h1>
        <p className="page-sub">Append-only record for the whole workspace. The database rejects updates and deletes on this table.</p>
      </div></div>
      <div className="row wrap" style={{ marginBottom: 12 }}>
        <label className="label" htmlFor="verb">Event type</label>
        <select id="verb" className="select" style={{ width: "auto" }} value={verb} onChange={(e) => { setVerb(e.target.value); setPage(0); }}>
          {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <Panel title={`Events${q.data ? ` (${q.data.total})` : ""}`} flush>
        {q.isLoading ? <LoadingRows /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : (
          <>
            <AuditTable events={q.data!.items} showRequestId />
            <div className="row between" style={{ padding: "12px 16px", borderTop: "1px solid var(--hairline)" }}>
              <span className="small muted">{q.data!.total ? page * PAGE + 1 : 0}–{Math.min(q.data!.total, page * PAGE + PAGE)} of {q.data!.total}</span>
              <div className="row">
                <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
                <button className="btn btn-secondary btn-sm" disabled={(page + 1) * PAGE >= q.data!.total} onClick={() => setPage(page + 1)}>Next</button>
              </div>
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
