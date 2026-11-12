import {
  AlertCircle, AlertTriangle, Ban, CheckCircle2, Circle, CircleDashed, Clock, FileEdit, HelpCircle, Hourglass,
  Info, Loader2, MinusCircle, RefreshCw, ShieldAlert, ShieldCheck, X, XCircle,
} from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../api";

type Tone = "success" | "warning" | "critical" | "info" | "neutral" | "brand" | "copper" | "outline";
type StatusDef = [Tone, typeof Circle, string];

const S: Record<string, StatusDef> = {
  // case
  NEEDS_CLARIFICATION: ["warning", HelpCircle, "Needs clarification"],
  IN_ANALYSIS: ["info", RefreshCw, "In analysis"],
  AWAITING_APPROVAL: ["brand", Hourglass, "Awaiting approval"],
  CHANGES_REQUESTED: ["warning", FileEdit, "Changes requested"],
  REJECTED: ["critical", XCircle, "Rejected"],
  APPROVED: ["success", CheckCircle2, "Approved"],
  AUTHORIZED: ["success", ShieldCheck, "Authorized"],
  EXECUTING: ["info", Loader2, "Executing"],
  EXECUTION_ATTENTION: ["critical", AlertTriangle, "Needs attention"],
  COMPLETED: ["success", CheckCircle2, "Completed"],
  // package
  IN_REVIEW: ["brand", Hourglass, "In review"],
  SUPERSEDED: ["neutral", MinusCircle, "Superseded"],
  // requirement
  DRAFT: ["info", CircleDashed, "AI draft — review"],
  CONFIRMED: ["success", CheckCircle2, "Confirmed"],
  MISSING: ["warning", AlertCircle, "Missing"],
  CONFLICTING: ["critical", AlertTriangle, "Conflicting"],
  NOT_APPLICABLE: ["neutral", MinusCircle, "Not applicable"],
  // runs / steps
  PENDING: ["neutral", Circle, "Pending"],
  RUNNING: ["info", Loader2, "Running"],
  SUCCEEDED: ["success", CheckCircle2, "Succeeded"],
  FAILED: ["critical", XCircle, "Failed"],
  PARTIAL: ["critical", AlertTriangle, "Partial"],
  UNKNOWN_OUTCOME: ["warning", HelpCircle, "Unknown outcome"],
  BLOCKED: ["neutral", Ban, "Blocked"],
  // clarifications / eval
  OPEN: ["warning", Clock, "Open"],
  ANSWERED: ["success", CheckCircle2, "Answered"],
  PASS: ["success", CheckCircle2, "Pass"],
  FAIL: ["critical", XCircle, "Fail"],
  // risk
  LOW: ["success", ShieldCheck, "Low risk"],
  MODERATE: ["warning", ShieldAlert, "Moderate risk"],
  HIGH: ["critical", ShieldAlert, "High risk"],
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const [tone, Icon, text] = S[status] ?? (["neutral", Circle, status] as StatusDef);
  return (
    <span className={`badge ${tone}`}>
      <Icon size={14} aria-hidden="true" />
      {label ?? text}
    </span>
  );
}

export function Badge({ tone = "neutral", children, icon }: { tone?: Tone; children: ReactNode; icon?: ReactNode }) {
  return <span className={`badge ${tone}`}>{icon}{children}</span>;
}

export function SyntheticTag({ text = "Synthetic data" }: { text?: string }) {
  return <Badge tone="copper" icon={<Info size={13} aria-hidden="true" />}>{text}</Badge>;
}

export function Avatar({ initials, size }: { initials: string; size?: "sm" }) {
  return <span className={`avatar ${size ?? ""}`} aria-hidden="true">{initials}</span>;
}

export function Panel({ title, subtitle, actions, children, className = "", flush, headingLevel = 2, id }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
  flush?: boolean; headingLevel?: 2 | 3; id?: string;
}) {
  const H = headingLevel === 2 ? "h2" : "h3";
  return (
    <section className={`panel ${className}`} aria-labelledby={title && id ? id : undefined}>
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <H id={id}>{title}</H>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions && <div className="row wrap">{actions}</div>}
        </div>
      )}
      <div className={`panel-body ${flush ? "flush" : ""}`}>{children}</div>
    </section>
  );
}

export function Callout({ tone, title, children, icon }: { tone: "info" | "warning" | "critical" | "success" | "brand"; title?: ReactNode; children?: ReactNode; icon?: ReactNode }) {
  const I = { info: Info, warning: AlertTriangle, critical: AlertCircle, success: CheckCircle2, brand: Info }[tone];
  return (
    <div className={`callout ${tone}`} role={tone === "critical" ? "alert" : undefined}>
      {icon ?? <I size={18} aria-hidden="true" />}
      <div>{title && <strong>{title} </strong>}{children}</div>
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = error instanceof ApiError ? error.message : "Something went wrong while loading this view.";
  return (
    <div className="empty" role="alert">
      <h3>Could not load this view</h3>
      <p>{msg}</p>
      {onRetry && <button className="btn btn-secondary" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function LoadingRows({ rows = 5, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="stack tight" style={{ padding: 20 }} aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton" style={{ height: 18, width: `${90 - (i % 3) * 12}%` }} />)}
    </div>
  );
}

export function Field({ label, hint, error, children, htmlFor }: {
  label: ReactNode; hint?: ReactNode; error?: string; children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode; htmlFor?: string;
}) {
  const auto = useId();
  const id = htmlFor ?? auto;
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children({ id, describedBy, invalid: !!error })}
      {hint && <span className="hint" id={hintId}>{hint}</span>}
      {error && <span className="error" id={errId}><AlertCircle size={14} aria-hidden="true" />{error}</span>}
    </div>
  );
}

/** Native <dialog>: focus is trapped by the browser, Esc closes, focus returns to the opener. */
export function Dialog({ open, onClose, title, children, footer, wide, labelledBy }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode; wide?: boolean; labelledBy?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<Element | null>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      opener.current = document.activeElement;
      d.showModal();
    } else if (!open && d.open) {
      d.close();
      (opener.current as HTMLElement | null)?.focus?.();
    }
  }, [open]);
  useEffect(() => () => {
    // the parent often unmounts the dialog instead of setting open=false: still return focus to the opener
    const el = opener.current as HTMLElement | null;
    if (el && document.contains(el)) requestAnimationFrame(() => el.focus());
  }, []);
  return (
    <dialog ref={ref} className={`dialog ${wide ? "wide" : ""}`} aria-labelledby={labelledBy ?? titleId}
      onCancel={(e) => { e.preventDefault(); onClose(); }}>
      {open && (
        <>
          <div className="dialog-head">
            <h2 id={titleId}>{title}</h2>
            <button className="icon-btn" onClick={onClose} aria-label="Close dialog"><X size={18} /></button>
          </div>
          <div className="dialog-body">{children}</div>
          {footer && <div className="dialog-foot">{footer}</div>}
        </>
      )}
    </dialog>
  );
}

type Toast = { id: number; text: string; tone: "ok" | "error" };
const ToastCtx = createContext<(text: string, tone?: "ok" | "error") => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: "ok" | "error" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 8000 : 4500);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone === "error" ? "error" : ""}`}>
            {t.tone === "error" ? <AlertCircle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error instanceof ApiError ? error : null;
  const blockers = (e?.details.blockers as { message: string }[] | undefined) ?? [];
  return (
    <Callout tone="critical" title={e ? e.message : "Something went wrong."}>
      {blockers.length > 0 && <ul>{blockers.map((b, i) => <li key={i}>{b.message}</li>)}</ul>}
      {e?.code && <div className="xs mono" style={{ marginTop: 4, opacity: 0.8 }}>{e.code}</div>}
    </Callout>
  );
}
