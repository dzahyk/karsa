import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, Ban, Calendar, CalendarDays, Download, FileText, Gauge, Globe2, History, ListChecks, MessageSquarePlus, Package,
  RefreshCw, ShieldCheck, Target, UserPen, Users, Wallet,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, can, fieldErrors } from "../api";
import { Badge, Callout, Dialog, Empty, ErrorMessage, Field, Panel, StatusBadge, useToast } from "../components/ui";
import { dateTime, pageOf, valueDisplay } from "../format";
import { useSession } from "../session";
import type { CaseDetail, Change, Clarification, Requirement, SourceDocument } from "../types";
import { caseKey, useCase } from "./CaseLayout";

const ICONS: Record<string, typeof Target> = {
  target_leads: Target, budget: Wallet, timeline: Calendar, lead_definition: Users, geography: Globe2,
  target_segment: Gauge, reporting: ListChecks, deliverables: Package, start_date: CalendarDays, constraints: Ban,
};

export function VerificationBadge({ doc }: { doc: Pick<SourceDocument, "verification" | "channel" | "reference" | "kind"> }) {
  if (doc.kind === "brief") return <Badge tone="success" icon={<ShieldCheck size={13} aria-hidden="true" />}>Client document</Badge>;
  return doc.verification === "client_text"
    ? <Badge tone="success" icon={<ShieldCheck size={13} aria-hidden="true" />}>Client's own words · {doc.channel}</Badge>
    : <Badge tone="warning" icon={<UserPen size={13} aria-hidden="true" />}>Analyst-recorded {doc.channel} — not the client's words</Badge>;
}

function sourceLabel(c: CaseDetail, r: Requirement) {
  if (!r.source) return r.state === "CONFLICTING" ? `${r.candidates.length} values in brief` : "Not in source";
  const doc = c.documents.find((d) => d.id === r.source!.document_id);
  if (!doc) return "Source";
  if (doc.kind !== "brief") return `${doc.title.split(" — ")[0]}${doc.verification === "analyst_recorded" ? " (analyst-recorded)" : ""}`;
  const page = doc.page_breaks.length ? `p.${pageOf(doc.page_breaks, r.source.start)} · ` : "";
  return `Brief · ${page}chars ${r.source.start}–${r.source.end}`;
}

function useInvalidate(code: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: caseKey(code) });
    qc.invalidateQueries({ queryKey: ["clarifications", code] });
    qc.invalidateQueries({ queryKey: ["history", code] });
    qc.invalidateQueries({ queryKey: ["cases"] });
    qc.invalidateQueries({ queryKey: ["feasibility", code] });
  };
}

export function RequirementsPage() {
  const { c } = useCase();
  const { user } = useSession();
  const [selected, setSelected] = useState<string>(() => c.requirements.find((r) => r.state !== "CONFIRMED")?.key ?? c.requirements[0]?.key);
  const sel = c.requirements.find((r) => r.key === selected) ?? c.requirements[0];
  const [dialog, setDialog] = useState<null | { kind: "edit" | "mark_missing" | "not_applicable" | "ask"; value?: string }>(null);
  const invalidate = useInvalidate(c.code);
  const toast = useToast();
  const editable = can(user, "requirement.edit") && !c.lock_reason;
  const confirm = useMutation({
    mutationFn: (r: Requirement) => api.patch(`/cases/${c.code}/requirements/${r.key}`, { action: "confirm", version: r.version }),
    onSuccess: () => { invalidate(); toast("Requirement confirmed."); },
    onError: (e) => { toast((e as Error).message, "error"); if (e instanceof ApiError && e.code === "VERSION_CONFLICT") invalidate(); },
  });
  const reextract = useMutation({
    mutationFn: () => api.post<{ changed: number; extractor: string }>(`/cases/${c.code}/extract`),
    onSuccess: (r) => { invalidate(); toast(`Extraction re-run with ${r.extractor}: ${r.changed} untouched field(s) updated. Reviewed fields were kept.`); },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const drafts = c.requirements.filter((r) => r.state === "DRAFT").length;
  const blocking = c.requirements.filter((r) => r.critical && r.state !== "CONFIRMED");
  const injection = c.flags.filter((f) => f.kind === "prompt_injection");
  const claims = c.flags.filter((f) => f.kind === "unsupported_claim");
  return (
    <div className="stack">
      <div className="row wrap" style={{ gap: 10 }}>
        {drafts > 0 && <Badge tone="info">AI draft — analyst review required ({drafts})</Badge>}
        <span className="small muted">Drafted by: <span className="mono">{c.extractor}</span>{c.extractor.startsWith("demo-rules") && " — demo extractor (rule-based, not an LLM)"}</span>
        {editable && <button className="btn btn-ghost btn-sm" onClick={() => reextract.mutate()} disabled={reextract.isPending}
          title="Re-run extraction on the stored brief; fields a person has touched are kept"><RefreshCw size={14} aria-hidden="true" />Re-run extraction</button>}
      </div>
      {injection.length > 0 && (
        <Callout tone="critical" title="Instruction-like text found in the brief.">
          “{injection[0].span.quote}” was treated as data. It cannot approve, execute or change permissions. Security review is recorded in the audit log.
        </Callout>
      )}
      {claims.length > 0 && (
        <Callout tone="warning" title="Unsupported client claim.">“{claims[0].span.quote}” has no supporting data and will be listed as a risk, never as a fact.</Callout>
      )}


      <div className="grid-2">
        <div className="stack">
          <Panel title="Requirements" id="req-title" subtitle="Extracted from the submitted brief. Verify each value against its source and complete what is missing."
            actions={<span className="small muted">{c.requirements.length} requirements · {blocking.length} critical open</span>} flush>
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th scope="col">Requirement</th><th scope="col">Value</th><th scope="col">Status</th><th scope="col" className="hide-mobile">Source (evidence)</th></tr></thead>
                <tbody>
                  {c.requirements.map((r) => {
                    const Icon = ICONS[r.key] ?? FileText;
                    return (
                      <tr key={r.key} className={`clickable ${sel?.key === r.key ? "selected" : ""}`} onClick={() => setSelected(r.key)}>
                        <td>
                          <button className="row" style={{ background: "none", border: 0, padding: 0, cursor: "pointer", textAlign: "left", gap: 10 }}
                            onClick={(e) => { e.stopPropagation(); setSelected(r.key); }} aria-pressed={sel?.key === r.key}
                            aria-label={`${r.label}: show evidence`}>
                            <span className="req-icon"><Icon size={17} aria-hidden="true" /></span>
                            <span><span style={{ fontWeight: 600 }}>{r.label}</span>{r.critical && <span className="xs muted" style={{ display: "block" }}>Critical</span>}</span>
                          </button>
                        </td>
                        <td style={{ maxWidth: 260 }}>
                          <span className={r.value_type === "text" ? "" : "mono"}>{valueDisplay(r.value_type, r.value)}</span>
                          {r.overridden && <div className="xs" style={{ color: "var(--warning)", marginTop: 3 }}>Overridden — source says {valueDisplay(r.value_type, r.source_value)}</div>}
                        </td>
                        <td><StatusBadge status={r.state} /></td>
                        <td className="small muted hide-mobile">{sourceLabel(c, r)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          <Clarifications c={c} />
          <ChangeHistory code={c.code} />
        </div>

        <div className="stack" style={{ position: "sticky", top: 76 }}>
          {sel && <Evidence c={c} r={sel} />}
          {sel && (
            <Panel title="Review this requirement" headingLevel={3} subtitle={sel.note ?? undefined}>
              {!can(user, "requirement.edit") ? (
                <p className="small muted">Your role can view requirements but not change them. Switch to a Deal Desk Analyst to edit.</p>
              ) : (
                <div className="row wrap">
                  {sel.state === "DRAFT" && sel.value && (
                    <button className="btn btn-primary" disabled={!editable || confirm.isPending} onClick={() => confirm.mutate(sel)}>
                      Confirm value
                    </button>
                  )}
                  <button className="btn btn-secondary" disabled={!editable} onClick={() => setDialog({ kind: "edit", value: sel.value ?? "" })}>
                    {sel.value ? "Edit value" : "Enter value"}
                  </button>
                  <button className="btn btn-secondary" disabled={!editable} onClick={() => setDialog({ kind: "ask" })}>
                    <MessageSquarePlus size={16} aria-hidden="true" />Ask client
                  </button>
                  {sel.state !== "MISSING" && <button className="btn btn-ghost" disabled={!editable} onClick={() => setDialog({ kind: "mark_missing" })}>Mark missing</button>}
                  {!sel.critical && sel.state !== "NOT_APPLICABLE" && <button className="btn btn-ghost" disabled={!editable} onClick={() => setDialog({ kind: "not_applicable" })}>Not applicable</button>}
                </div>
              )}
              {sel.state === "CONFLICTING" && editable && (
                <div className="stack tight" style={{ marginTop: 14 }}>
                  <span className="label">Choose the value that applies (a reason is required):</span>
                  {sel.candidates.map((cd) => (
                    <button key={cd.value} className="btn btn-outline" onClick={() => setDialog({ kind: "edit", value: cd.value })}
                      style={{ justifyContent: "space-between" }}>
                      <span>“{cd.span.quote}”</span><span className="mono">{valueDisplay(sel.value_type, cd.value)}</span>
                    </button>
                  ))}
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>

      <div className="row" style={{ justifyContent: "flex-end" }}>
        <Link className="btn btn-primary btn-lg" to="../feasibility">Continue to feasibility <ArrowRight size={18} aria-hidden="true" /></Link>
      </div>

      {dialog && sel && (dialog.kind === "ask"
        ? <AskDialog code={c.code} r={sel} onClose={() => setDialog(null)} />
        : <ChangeDialog code={c.code} r={sel} kind={dialog.kind} initial={dialog.value ?? ""} onClose={() => setDialog(null)} />)}
    </div>
  );
}

function highlight(text: string, spans: { start: number; end: number; cls: string; label: string }[]): ReactNode[] {
  const sorted = [...spans].filter((s) => s.end > s.start).sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let pos = 0;
  sorted.forEach((s, i) => {
    if (s.start < pos) return;
    out.push(text.slice(pos, s.start));
    out.push(<mark key={i} className={s.cls} aria-label={s.label} id={s.cls.includes("active") ? "active-span" : undefined}>{text.slice(s.start, s.end)}</mark>);
    pos = s.end;
  });
  out.push(text.slice(pos));
  return out;
}

function Evidence({ c, r }: { c: CaseDetail; r: Requirement }) {
  const docId = r.source?.document_id ?? r.candidates[0]?.source_document_id ?? c.documents.find((d) => d.kind === "brief")?.id;
  const [override, setOverride] = useState<number | null>(null);
  const doc = c.documents.find((d) => d.id === (override ?? docId)) ?? c.documents[0];
  const spans = useMemo(() => {
    const s: { start: number; end: number; cls: string; label: string }[] = [];
    if (r.source && r.source.document_id === doc.id) s.push({ start: r.source.start, end: r.source.end, cls: "active", label: `Evidence for ${r.label}` });
    for (const cd of r.candidates) if (cd.source_document_id === doc.id) s.push({ start: cd.span.start, end: cd.span.end, cls: "active", label: `Conflicting value for ${r.label}` });
    if (doc.kind === "brief") for (const f of c.flags) s.push({ start: f.span.start, end: f.span.end, cls: "flag", label: f.kind === "prompt_injection" ? "Flagged instruction-like text" : "Unsupported claim" });
    return s;
  }, [r, doc, c.flags]);
  const page = r.source && r.source.document_id === doc.id && doc.page_breaks.length ? pageOf(doc.page_breaks, r.source.start) : null;
  const docRef = useRef<HTMLDivElement>(null);
  useEffect(() => { // bring the highlighted evidence into view inside the source panel
    const box = docRef.current;
    const mark = box?.querySelector("mark.active") as HTMLElement | null;
    if (!box) return;
    box.scrollTop = 0;
    if (mark) box.scrollTop = Math.max(0, mark.getBoundingClientRect().top - box.getBoundingClientRect().top - 60);
  }, [r.key, doc.id]);
  return (
    <Panel title={`Evidence: ${r.label}`} headingLevel={2} subtitle={doc.page_breaks.length ? "Exact text extracted from the uploaded file; page numbers come from the PDF's own pages." : "Exact text from the stored source. Highlights use character positions."}>
      <div className="doc-head">
        <span className="doc-icon"><FileText size={18} aria-hidden="true" /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600 }}>{doc.title}{page && <span className="muted"> · page {page} of {doc.page_breaks.length + 1}</span>}</div>
          <div className="xs muted mono" title={doc.sha256}>sha256 {doc.sha256.slice(7, 19)}… · {doc.content.length.toLocaleString()} chars</div>
          <div className="row wrap" style={{ gap: 6, marginTop: 4 }}>
            <VerificationBadge doc={doc} />
            {doc.reference && <span className="xs muted">Ref: {doc.reference}</span>}
            {doc.artifact && <a className="xs" href={`/api/v1/artifacts/${doc.artifact.id}`} download><Download size={12} aria-hidden="true" /> Original file ({doc.artifact.filename})</a>}
          </div>
        </div>
        {c.documents.length > 1 && (
          <select className="select" style={{ width: "auto", minHeight: 34 }} aria-label="Source document" value={doc.id} onChange={(e) => setOverride(Number(e.target.value))}>
            {c.documents.map((d) => <option key={d.id} value={d.id}>{d.kind === "brief" ? "Client brief" : d.title.split(" — ")[0]}</option>)}
          </select>
        )}
      </div>
      {r.overridden && <Callout tone="warning" title="Value overridden by an analyst.">The source below says {valueDisplay(r.value_type, r.source_value)}; the confirmed value is {valueDisplay(r.value_type, r.value)}. {r.note}</Callout>}
      {r.source || r.candidates.length ? (
        r.source && <div className="quote" style={{ marginBottom: 10 }}>“{r.source.quote}”</div>
      ) : (
        <Callout tone="warning" title="No source for this value.">
          {r.state === "MISSING" ? "The brief does not state it. Ask the client; do not guess." : "Entered manually; the reason is in the change history."}
        </Callout>
      )}
      <div className="doc" ref={docRef} tabIndex={0} aria-label={`Source text: ${doc.title}`}>{highlight(doc.content, spans)}</div>
    </Panel>
  );
}

function ChangeDialog({ code, r, kind, initial, onClose }: { code: string; r: Requirement; kind: "edit" | "mark_missing" | "not_applicable"; initial: string; onClose: () => void }) {
  const [value, setValue] = useState(initial);
  const [reason, setReason] = useState("");
  const invalidate = useInvalidate(code);
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.patch(`/cases/${code}/requirements/${r.key}`, { action: kind, value: kind === "edit" ? value : null, reason, version: r.version }),
    onSuccess: () => { invalidate(); toast(`${r.label} updated.`); onClose(); },
  });
  const errs = fieldErrors(m.error);
  const title = { edit: `${r.value ? "Edit" : "Enter"} ${r.label.toLowerCase()}`, mark_missing: `Mark ${r.label.toLowerCase()} as missing`, not_applicable: `Mark ${r.label.toLowerCase()} not applicable` }[kind];
  const hint = { integer: "Whole number, e.g. 3000", idr: "Whole rupiah, e.g. 150000000", weeks: "Number of weeks, e.g. 8", text: "Use the client's wording where possible.", date: "Pick the agreed start date." }[r.value_type];
  return (
    <Dialog open onClose={onClose} title={title}
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" form="req-change" disabled={m.isPending}>{m.isPending ? "Saving…" : "Save change"}</button></>}>
      <form id="req-change" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        {kind === "edit" && (
          <Field label="Value" hint={hint} error={errs.value}>{({ id, describedBy, invalid }) =>
            r.value_type === "date"
              ? <input id={id} type="date" className="input" value={value} onChange={(e) => setValue(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} />
              : r.value_type === "text"
              ? <textarea id={id} className="textarea" style={{ minHeight: 80 }} value={value} onChange={(e) => setValue(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} />
              : <input id={id} className="input num" inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} />}
          </Field>
        )}
        <Field label="Reason for this change" hint="Recorded in the audit trail with your name and the time." error={errs.reason}>{({ id, describedBy, invalid }) =>
          <textarea id={id} className="textarea" style={{ minHeight: 80 }} value={reason} onChange={(e) => setReason(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} />}
        </Field>
        {r.source && kind === "edit" && <p className="small muted">The original source quote stays attached as provenance: “{r.source.quote}”.</p>}
        {m.error && !Object.keys(errs).length ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function AskDialog({ code, r, onClose }: { code: string; r: Requirement; onClose: () => void }) {
  const [question, setQuestion] = useState("");
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post(`/cases/${code}/clarifications`, { requirement_key: r.key, question }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["clarifications", code] }); toast("Question added."); onClose(); },
  });
  return (
    <Dialog open onClose={onClose} title={`Ask about ${r.label.toLowerCase()}`}
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="ask" disabled={m.isPending}>Add question</button></>}>
      <form id="ask" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Question for the client" error={fieldErrors(m.error).question}>{({ id, describedBy, invalid }) =>
          <textarea id={id} className="textarea" style={{ minHeight: 90 }} value={question} onChange={(e) => setQuestion(e.target.value)} aria-describedby={describedBy} aria-invalid={invalid} />}
        </Field>
        {m.error && !fieldErrors(m.error).question ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function Clarifications({ c }: { c: CaseDetail }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["clarifications", c.code], queryFn: () => api.get<Clarification[]>(`/cases/${c.code}/clarifications`) });
  const suggest = useMutation({
    mutationFn: () => api.post<Clarification[]>(`/cases/${c.code}/clarifications/suggest`),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["clarifications", c.code] }); toast(r.length ? `${r.length} question(s) added from the required-field list.` : "Every unresolved item already has an open question."); },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const [answering, setAnswering] = useState<Clarification | null>(null);
  const editable = can(user, "clarification.manage") && !c.lock_reason;
  const open = (q.data ?? []).filter((x) => x.status === "OPEN").length;
  return (
    <Panel title={`Clarification questions${q.data ? ` (${q.data.length})` : ""}`} id="clar-title"
      subtitle={open ? `${open} open — critical gaps block the decision package until answered.` : "Questions sent to the client and their recorded answers."}
      actions={editable && <button className="btn btn-secondary btn-sm" onClick={() => suggest.mutate()} disabled={suggest.isPending}>Generate for open items</button>}>
      {q.isLoading ? <div className="skeleton" /> : (q.data ?? []).length === 0 ? (
        <p className="small muted">No questions yet. Generate them from the list of required fields, or ask one from a requirement.</p>
      ) : (
        <ul className="stack tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {q.data!.map((x) => (
            <li key={x.id} style={{ border: "1px solid var(--hairline)", borderRadius: 8, padding: "12px 14px" }}>
              <div className="row between" style={{ alignItems: "flex-start" }}>
                <div>
                  <div className="xs muted">#{x.id} · {x.requirement_key ? c.requirements.find((r) => r.key === x.requirement_key)?.label : "General"}</div>
                  <div style={{ fontWeight: 600, marginTop: 2 }}>{x.question}</div>
                </div>
                <StatusBadge status={x.status} />
              </div>
              {x.answer ? (
                <div className="quote" style={{ marginTop: 8 }}>
                  {x.answer}
                  <div className="xs muted" style={{ marginTop: 4 }}>— {x.answered_source} via {x.channel} ({x.reference}), recorded by {x.answered_by?.name} · {dateTime(x.answered_at)}{x.applied && " · applied to requirement"}</div>
                </div>
              ) : editable && (
                <button className="btn btn-outline btn-sm" style={{ marginTop: 10 }} onClick={() => setAnswering(x)}>Record answer</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {answering && <AnswerDialog c={c} q={answering} onClose={() => setAnswering(null)} />}
    </Panel>
  );
}

function AnswerDialog({ c, q, onClose }: { c: CaseDetail; q: Clarification; onClose: () => void }) {
  const r = c.requirements.find((x) => x.key === q.requirement_key);
  const [form, setForm] = useState({ answer: "", answered_source: "", apply: !!r, apply_value: "", channel: "email", reference: "", client_excerpt: "" });
  const invalidate = useInvalidate(c.code);
  const toast = useToast();
  const m = useMutation({
    mutationFn: () => api.post(`/cases/${c.code}/clarifications/${q.id}/answer`, { ...form, client_excerpt: form.client_excerpt || null, version: r?.version }),
    onSuccess: () => { invalidate(); toast(form.apply && r ? `Answer recorded and ${r.label} confirmed.` : "Answer recorded."); onClose(); },
  });
  const errs = fieldErrors(m.error);
  return (
    <Dialog open onClose={onClose} title="Record client answer"
      footer={<><button className="btn btn-secondary" onClick={onClose}>Cancel</button><button className="btn btn-primary" form="answer" disabled={m.isPending}>{m.isPending ? "Saving…" : "Save answer"}</button></>}>
      <form id="answer" className="stack" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <p className="small"><strong>Question:</strong> {q.question}</p>
        <Field label="Answer (as given)" hint="Stored as a new source document; it becomes the evidence for the requirement." error={errs.answer}>{({ id, describedBy, invalid }) =>
          <textarea id={id} className="textarea" style={{ minHeight: 90 }} value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} aria-describedby={describedBy} aria-invalid={invalid} />}</Field>
        <div className="grid-2 even" style={{ gap: 12 }}>
          <Field label="Answered by" hint="e.g. Maya Santoso (client)" error={errs.answered_source}>{({ id, describedBy, invalid }) =>
            <input id={id} className="input" value={form.answered_source} onChange={(e) => setForm({ ...form, answered_source: e.target.value })} aria-describedby={describedBy} aria-invalid={invalid} />}</Field>
          <Field label="Received via" error={errs.channel}>{({ id }) =>
            <select id={id} className="select" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
              {["email", "call", "meeting", "chat", "document"].map((x) => <option key={x} value={x}>{x}</option>)}
            </select>}</Field>
        </div>
        <Field label="Reference someone else can check" hint="e.g. email subject + date, call date and time, meeting notes link" error={errs.reference}>{({ id, describedBy, invalid }) =>
          <input id={id} className="input" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} aria-describedby={describedBy} aria-invalid={invalid} />}</Field>
        <Field label="Client's own words (paste, optional but recommended)" hint="If pasted, this verbatim text becomes the evidence. Without it the evidence is labelled 'analyst-recorded'." error={errs.client_excerpt}>{({ id, describedBy }) =>
          <textarea id={id} className="textarea" style={{ minHeight: 70 }} value={form.client_excerpt} onChange={(e) => setForm({ ...form, client_excerpt: e.target.value })} aria-describedby={describedBy} />}</Field>
        {r && (
          <label className="check"><input type="checkbox" checked={form.apply} onChange={(e) => setForm({ ...form, apply: e.target.checked })} />
            <span>Apply to <strong>{r.label}</strong> and mark it confirmed</span></label>
        )}
        {r && form.apply && r.value_type !== "text" && (
          <Field label={`Value for ${r.label.toLowerCase()}`} hint="Digits only — e.g. 3000 or 150000000." error={errs.apply_value}>{({ id, describedBy, invalid }) =>
            <input id={id} className="input num" inputMode="numeric" value={form.apply_value} onChange={(e) => setForm({ ...form, apply_value: e.target.value })} aria-describedby={describedBy} aria-invalid={invalid} />}</Field>
        )}
        {m.error && !Object.keys(errs).length ? <ErrorMessage error={m.error} /> : null}
      </form>
    </Dialog>
  );
}

function ChangeHistory({ code }: { code: string }) {
  const q = useQuery({ queryKey: ["history", code], queryFn: () => api.get<Change[]>(`/cases/${code}/requirements/history`) });
  const n = q.data?.length ?? 0;
  return (
    <details className="panel" style={{ padding: "14px 20px" }}>
      <summary style={{ cursor: "pointer", fontWeight: 600 }}><History size={16} aria-hidden="true" style={{ verticalAlign: -3, marginRight: 6 }} />Change history ({n})</summary>
      {n === 0 ? <Empty title="No changes yet" /> : (
        <ul style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }} className="stack tight">
          {q.data!.map((ch) => (
            <li key={ch.id} className="small" style={{ borderTop: "1px solid var(--hairline)", paddingTop: 8 }}>
              <strong>{ch.actor.name}</strong> · {ch.action.replace("_", " ")} · {ch.from_state} → {ch.to_state}
              {ch.from_value !== ch.to_value && <> · <span className="mono">{ch.from_value ?? "—"} → {ch.to_value ?? "—"}</span></>}
              {ch.reason && <div className="muted">Reason: {ch.reason}</div>}
              <div className="xs faint">{dateTime(ch.at)}</div>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

