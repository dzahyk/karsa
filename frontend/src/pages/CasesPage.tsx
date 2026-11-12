import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, CloudOff, Plus, Search, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, can, fieldErrors } from "../api";
import { Avatar, Dialog, Empty, ErrorMessage, ErrorState, Field, LoadingRows, StatusBadge, SyntheticTag, useToast } from "../components/ui";
import { dateTime, relative } from "../format";
import { useSession } from "../session";
import type { CaseSummary, User } from "../types";

const PAGE = 25;

const GROUPS = [
  { key: "all", label: "All" },
  { key: "needs_clarification", label: "Needs clarification" },
  { key: "awaiting_approval", label: "Awaiting approval" },
  { key: "in_progress", label: "In progress" },
  { key: "closed", label: "Closed" },
];

export const EXAMPLE_BRIEF = `Subject: Lead campaign request (synthetic)

Target: 1,200 qualified leads
Budget: Rp66.000.000
Timeline: 6 weeks
Lead definition: HR or finance managers who handle company travel
Geography: to be confirmed
Target segment: Companies with 200+ employees
Reporting: weekly report and CRM sync of accepted leads`;

function Due({ iso, closed }: { iso: string | null; closed: boolean }) {
  if (!iso) return <span className="muted">—</span>;
  const overdue = !closed && new Date(iso).getTime() < Date.now();
  return (
    <span style={{ color: overdue ? "var(--critical)" : undefined, fontWeight: overdue ? 600 : undefined }}>
      {overdue && <><AlertCircle size={13} aria-hidden="true" style={{ verticalAlign: -2, marginRight: 4 }} />Overdue · </>}
      {dateTime(iso)}
    </span>
  );
}

export function CasesPage() {
  const [params, setParams] = useSearchParams();
  const group = params.get("group") ?? "all";
  const [q, setQ] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState(q);
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const { user } = useSession();
  const nav = useNavigate();
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  useEffect(() => setPage(0), [group, debounced]);
  const query = useQuery({
    queryKey: ["cases", group, debounced, page],
    queryFn: () => api.get<{ items: CaseSummary[]; counts: Record<string, number>; total: number }>(
      `/cases?${new URLSearchParams({ ...(group !== "all" ? { group } : {}), ...(debounced ? { q: debounced } : {}), limit: String(PAGE), offset: String(page * PAGE) })}`),
    refetchInterval: 60_000, placeholderData: (prev) => prev,
  });
  const counts = query.data?.counts;
  const attention = (counts?.needs_clarification ?? 0) + (counts?.awaiting_approval ?? 0);
  const setGroup = (g: string) => { const p = new URLSearchParams(params); if (g === "all") p.delete("group"); else p.set("group", g); setParams(p, { replace: true }); };
  const closedStatuses = ["COMPLETED", "REJECTED"];
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Cases</h1>
          <p className="page-sub">Turn business requests into decisions you can trace, review and act on.</p>
        </div>
        <div className="row">
          <SyntheticTag />
          <button className="btn btn-primary" onClick={() => setOpen(true)} disabled={!can(user, "case.create")}
            title={can(user, "case.create") ? undefined : "Only a Deal Desk Analyst can create requests"}>
            <Plus size={18} aria-hidden="true" />New request
          </button>
        </div>
      </div>

      {attention > 0 && (
        <div className="callout brand" style={{ marginBottom: 18, alignItems: "center" }}>
          <AlertCircle size={20} aria-hidden="true" color="var(--brand)" />
          <div style={{ flex: 1 }}>
            <strong>{attention} cases need a decision</strong>
            <span className="muted"> — {counts?.needs_clarification ?? 0} need clarification before pricing can be finalized; {counts?.awaiting_approval ?? 0} await approval.</span>
          </div>
          <button className="btn btn-ghost" onClick={() => setGroup("needs_clarification")}>Review missing details <ArrowRight size={16} aria-hidden="true" /></button>
        </div>
      )}

      <div className="row wrap between" style={{ marginBottom: 14 }}>
        <div className="row wrap" role="group" aria-label="Filter by status">
          {GROUPS.map((g) => (
            <button key={g.key} className="chip" aria-pressed={group === g.key} onClick={() => setGroup(g.key)}>
              {g.label} <span className="count">({counts?.[g.key] ?? "…"})</span>
            </button>
          ))}
        </div>
        <div className="search" style={{ width: "min(340px, 100%)" }}>
          <Search size={16} aria-hidden="true" />
          <input className="input" type="search" placeholder="Search case ID, client or title" aria-label="Search cases"
            value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <section className="panel" aria-label="Case list">
        {query.error && query.data && (
          <div className="callout warning" role="status" style={{ margin: 12 }}>
            <CloudOff size={18} aria-hidden="true" />
            <div><strong>API unavailable — showing data from {new Date(query.dataUpdatedAt).toLocaleTimeString("en-GB", { timeZone: "Asia/Jakarta" })} WIB.</strong> It may be stale. <button className="btn btn-ghost btn-sm" onClick={() => query.refetch()}>Retry</button></div>
          </div>
        )}
        {query.isLoading ? <LoadingRows rows={8} label="Loading cases" /> : query.error && !query.data ? <ErrorState error={query.error} onRetry={() => query.refetch()} /> : (
          query.data!.items.length === 0 ? (
            <Empty title={counts?.all === 0 && !debounced ? "No cases yet" : "No cases match these filters"}
              action={<div className="row">
                {(group !== "all" || debounced) && <button className="btn btn-secondary" onClick={() => { setQ(""); setGroup("all"); }}>Clear filters</button>}
                {can(user, "case.create") && <button className="btn btn-primary" onClick={() => setOpen(true)}>Create a request</button>}
              </div>}>
              Clear the filters or create a new request from a client brief.
            </Empty>
          ) : (
            <>
              <div className="table-wrap hide-mobile">
                <table className="table">
                  <caption className="sr-only">Cases, most urgent open work first. Times in WIB.</caption>
                  <thead><tr><th scope="col">Case</th><th scope="col">Client — request</th><th scope="col">Stage</th><th scope="col">Next action</th><th scope="col">Owner</th><th scope="col">Due (WIB)</th><th scope="col">Updated</th></tr></thead>
                  <tbody>
                    {query.data!.items.map((c) => (
                      <tr key={c.code} className="clickable" onClick={() => nav(`/cases/${c.code}`)}>
                        <td><Link className="case-link" to={`/cases/${c.code}`} onClick={(e) => e.stopPropagation()}>{c.code}</Link></td>
                        <td>{c.client_name} — {c.title}</td>
                        <td><StatusBadge status={c.status} /></td>
                        <td style={{ fontWeight: 600 }}>{c.next_action}</td>
                        <td className="nowrap"><span className="row" style={{ gap: 8 }}><Avatar initials={c.owner.initials} size="sm" />{c.owner.name}</span></td>
                        <td className="small"><Due iso={c.due_at} closed={closedStatuses.includes(c.status)} /></td>
                        <td className="small muted" title={dateTime(c.updated_at)}>{relative(c.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="show-mobile" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {query.data!.items.map((c) => (
                  <li key={c.code} style={{ borderBottom: "1px solid var(--hairline)" }}>
                    <Link to={`/cases/${c.code}`} style={{ display: "block", padding: "14px 16px", color: "inherit", textDecoration: "none" }}>
                      <div className="row between"><span className="mono" style={{ color: "var(--brand)", fontWeight: 600 }}>{c.code}</span><StatusBadge status={c.status} /></div>
                      <div style={{ fontWeight: 600, marginTop: 6 }}>{c.client_name} — {c.title}</div>
                      <div className="small muted" style={{ marginTop: 2 }}>Next: {c.next_action}</div>
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="row between small muted" style={{ padding: "12px 16px", borderTop: "1px solid var(--hairline)" }}>
                <span>{page * PAGE + 1}–{page * PAGE + query.data!.items.length} of {query.data!.total} · times in WIB (UTC+7)</span>
                <span className="row">
                  <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button>
                  <button className="btn btn-secondary btn-sm" disabled={(page + 1) * PAGE >= query.data!.total} onClick={() => setPage(page + 1)}>Next</button>
                </span>
              </div>
            </>
          )
        )}
      </section>
      <NewCaseDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

function NewCaseDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user } = useSession();
  const usersQ = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users"), enabled: open });
  const analysts = (usersQ.data ?? []).filter((u) => u.role === "ANALYST");
  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [form, setForm] = useState({ title: "", client_name: "", brief: "", owner_id: "" });
  const [file, setFile] = useState<File | null>(null);
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => {
      if (mode === "upload") {
        const fd = new FormData();
        fd.set("title", form.title); fd.set("client_name", form.client_name); fd.set("owner_id", form.owner_id || user!.id);
        if (file) fd.set("file", file);
        return api.upload<CaseSummary>("/cases/upload", fd);
      }
      return api.post<CaseSummary>("/cases", { ...form, owner_id: form.owner_id || user?.id });
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["cases"] });
      toast(`Case ${c.code} created. Requirements were drafted and need your review.`);
      onClose();
      setForm({ title: "", client_name: "", brief: "", owner_id: "" });
      setFile(null);
      nav(`/cases/${c.code}/requirements`);
    },
  });
  const errs = fieldErrors(m.error);
  return (
    <Dialog open={open} onClose={onClose} title="New request" wide
      footer={<>
        <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="new-case" type="submit" disabled={m.isPending || (mode === "upload" && !file)}>{m.isPending ? "Creating…" : "Create case"}</button>
      </>}>
      <form id="new-case" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }} noValidate>
        <div className="grid-2 even" style={{ gap: 14 }}>
          <Field label="Request title" error={errs.title}>{({ id, describedBy, invalid }) =>
            <input id={id} className="input" value={form.title} aria-describedby={describedBy} aria-invalid={invalid} required
              placeholder="B2B Lead Campaign" onChange={(e) => setForm({ ...form, title: e.target.value })} />}</Field>
          <Field label="Client (pseudonym)" error={errs.client_name}>{({ id, describedBy, invalid }) =>
            <input id={id} className="input" value={form.client_name} aria-describedby={describedBy} aria-invalid={invalid} required
              placeholder="Aster Labs" onChange={(e) => setForm({ ...form, client_name: e.target.value })} />}</Field>
        </div>
        <Field label="Owner" hint="The analyst accountable for this case." error={errs.owner_id}>{({ id, describedBy }) =>
          <select id={id} className="select" aria-describedby={describedBy} value={form.owner_id || user?.id || ""} onChange={(e) => setForm({ ...form, owner_id: e.target.value })}>
            {analysts.map((a) => <option key={a.id} value={a.id}>{a.name} — {a.title}</option>)}
          </select>}</Field>
        <div className="tabs" role="tablist" aria-label="Brief source">
          <button type="button" role="tab" aria-selected={mode === "paste"} onClick={() => setMode("paste")}>Paste text</button>
          <button type="button" role="tab" aria-selected={mode === "upload"} onClick={() => setMode("upload")}><Upload size={14} aria-hidden="true" /> Upload file</button>
        </div>
        {mode === "paste" ? (
          <>
            <Field label="Client brief" error={errs.brief}
              hint="Paste the email or brief text. It is stored as the original source and treated as untrusted data: instructions inside it are never followed.">
              {({ id, describedBy, invalid }) =>
                <textarea id={id} className="textarea" rows={10} value={form.brief} aria-describedby={describedBy} aria-invalid={invalid} required
                  onChange={(e) => setForm({ ...form, brief: e.target.value })} />}
            </Field>
            <div><button type="button" className="btn btn-ghost" onClick={() => setForm({ ...form, brief: EXAMPLE_BRIEF })}>Insert example brief</button></div>
          </>
        ) : (
          <Field label="Brief file" error={errs.file}
            hint="PDF (text-based, up to 30 pages), .eml, .txt or .md — max 5 MB. The original file is kept; scanned PDFs are refused rather than guessed.">
            {({ id, describedBy, invalid }) =>
              <input id={id} type="file" className="input" accept=".pdf,.eml,.txt,.md" aria-describedby={describedBy} aria-invalid={invalid}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)} />}
          </Field>
        )}
        {m.error && !Object.keys(errs).filter((k) => k !== "file").length ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}
