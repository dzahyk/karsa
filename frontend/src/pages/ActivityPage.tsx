import { useQuery } from "@tanstack/react-query";
import { CircleDot, ShieldAlert } from "lucide-react";
import { api } from "../api";
import { Empty, ErrorState, LoadingRows, Panel } from "../components/ui";
import { dateTime } from "../format";
import type { AuditEvent } from "../types";
import { useCase } from "./CaseLayout";

export function ActivityPage() {
  const { c } = useCase();
  const q = useQuery({ queryKey: ["audit", c.code], queryFn: () => api.get<AuditEvent[]>(`/cases/${c.code}/audit`) });
  if (q.isLoading) return <LoadingRows label="Loading activity" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  return <Panel title="Activity & audit trail" subtitle="Append-only record of system events and human decisions (newest first). Times in WIB." flush>
    {q.data!.length === 0 ? <Empty title="No activity yet" /> : <AuditTable events={q.data!} />}
  </Panel>;
}

export function AuditTable({ events, showRequestId }: { events: (AuditEvent & { request_id?: string | null })[]; showRequestId?: boolean }) {
  return (
    <div className="table-wrap"><table className="table">
      <thead><tr><th>Time (WIB)</th><th>Actor</th><th>Event</th></tr></thead>
      <tbody>{events.map((e) => {
        const security = e.verb.startsWith("security.");
        return (
          <tr key={e.id}>
            <td className="small mono" style={{ whiteSpace: "nowrap" }}>{dateTime(e.at)}</td>
            <td className="small">{e.actor ? <>{e.actor.name}<div className="xs muted">{e.actor.role_label}</div></> : <span className="muted">Karsa (system)</span>}</td>
            <td>
              <div className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                {security ? <ShieldAlert size={16} color="var(--critical)" aria-label="Security event" /> : <CircleDot size={14} color="var(--ink-faint)" aria-hidden="true" style={{ marginTop: 3 }} />}
                <div><div>{e.summary}</div><div className="xs mono faint">{e.verb}{showRequestId && e.request_id ? ` · ${e.request_id}` : ""}</div></div>
              </div>
            </td>
          </tr>);
      })}</tbody>
    </table></div>
  );
}
