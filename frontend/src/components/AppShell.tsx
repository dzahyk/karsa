import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, Bell, ClipboardCheck, FlaskConical, FolderKanban, Inbox, LogOut, MoreHorizontal, Settings, ScrollText, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, hasModule } from "../api";
import { relative } from "../format";
import { useSession } from "../session";
import type { Notification } from "../types";
import { LoginPage } from "../pages/LoginPage";
import { Avatar, LoadingRows } from "./ui";

const NAV = [
  { to: "/cases", label: "Cases", module: "cases" },
  { to: "/approvals", label: "Approvals", module: "approvals" },
  { to: "/workflows", label: "Workflows", module: "workflows" },
  { to: "/evaluation", label: "Evaluation", module: "evaluation" },
  { to: "/impact", label: "Impact", module: "impact" },
  { to: "/audit", label: "Audit", module: "audit" },
  { to: "/manage", label: "Manage", module: "manage" },
];

export function Logo() {
  return (
    <svg width="18" height="18" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M9 9h8a7 7 0 0 1 0 14H9z" fill="none" stroke="#fff" strokeWidth="2.8" />
      <path d="M13 16h11" stroke="#E4B18A" strokeWidth="2.8" strokeLinecap="round" />
    </svg>
  );
}

export function homeFor(modules: string[]) {
  return NAV.find((n) => modules.includes(n.module))?.to ?? "/more";
}

type DemoAccount = { username: string; name: string; role_label: string; organization_id: string };

function AccountMenu() {
  const { user, demoLogin, logout } = useSession();
  const nav = useNavigate();
  const accounts = useQuery({ queryKey: ["demoAccounts"], queryFn: () => api.get<DemoAccount[]>("/auth/demo-accounts"), retry: false, staleTime: 600_000 });
  if (!user) return null;
  return (
    <div className="role-switch">
      {accounts.data && (
        <>
          <label htmlFor="role-switch">Demo account</label>
          <select id="role-switch" value={user.username} aria-describedby="role-switch-note"
            onChange={async (e) => { await demoLogin(e.target.value); nav("/"); }}>
            {accounts.data.map((a) => <option key={a.username} value={a.username}>{a.name} — {a.role_label}{a.organization_id !== user.organization_id ? " (other tenant)" : ""}</option>)}
          </select>
          <span id="role-switch-note" className="sr-only">Switching signs you in as another synthetic demo account.</span>
        </>
      )}
      <Avatar initials={user.initials} />
      <button className="icon-btn on-dark" onClick={async () => { await logout(); nav("/"); }} aria-label="Sign out" title="Sign out"><LogOut size={18} /></button>
    </div>
  );
}

function NotificationBell() {
  const { unread } = useSession();
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const nav = useNavigate();
  const ref = useRef<HTMLDivElement>(null);
  const list = useQuery({ queryKey: ["notifications"], queryFn: () => api.get<{ items: Notification[]; unread: number }>("/notifications"), enabled: open });
  const readAll = useMutation({ mutationFn: () => api.post("/notifications/read"), onSuccess: () => { qc.invalidateQueries({ queryKey: ["notifications"] }); qc.invalidateQueries({ queryKey: ["me"] }); } });
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  return (
    <div className="bell" ref={ref}>
      <button className="icon-btn on-dark" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen(!open)}
        aria-label={`Notifications, ${unread} unread`}>
        <Bell size={19} aria-hidden="true" />{unread > 0 && <span className="bell-count" aria-hidden="true">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Notifications" onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
          <div className="row between" style={{ padding: "12px 14px", borderBottom: "1px solid var(--hairline)" }}>
            <strong>Notifications</strong>
            <button className="btn btn-ghost btn-sm" onClick={() => readAll.mutate()} disabled={!unread}>Mark all read</button>
          </div>
          {list.isLoading ? <LoadingRows rows={3} /> : (list.data?.items.length ?? 0) === 0 ? <p className="small muted" style={{ padding: 14 }}>Nothing yet.</p> : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, maxHeight: 380, overflow: "auto" }}>
              {list.data!.items.map((n) => (
                <li key={n.id}>
                  <button className="notif" onClick={() => { setOpen(false); api.post(`/notifications/read?notification_id=${n.id}`).then(() => qc.invalidateQueries({ queryKey: ["me"] })); nav(n.link); }}>
                    {!n.read && <span className="dot-unread" aria-label="unread" />}
                    <span style={{ fontWeight: n.read ? 500 : 650 }}>{n.title}</span>
                    <span className="small muted">{n.body}</span>
                    <span className="xs faint">{relative(n.created_at)}</span>
                  </button>
                </li>))}
            </ul>)}
          <p className="xs muted" style={{ padding: "8px 14px", borderTop: "1px solid var(--hairline)" }}>In-app only — email/Slack would need a permissioned connector.</p>
        </div>
      )}
    </div>
  );
}

function FreshnessBanner() {
  const h = useQuery({ queryKey: ["health"], queryFn: () => api.get<{ demo_data_age_days: number | null; rate_card_valid: boolean }>("/health"), staleTime: 300_000 });
  if (!h.data) return null;
  const old = (h.data.demo_data_age_days ?? 0) > 30;
  if (h.data.rate_card_valid && !old) return null;
  return (
    <div className="freshness" role="status">
      <AlertTriangle size={16} aria-hidden="true" />
      {!h.data.rate_card_valid ? "The demo rate card has expired, so pricing is blocked." : `Demo data is ${h.data.demo_data_age_days} days old; due dates look overdue.`}
      {" "}Reset it with <code>uv run python -m app.seed --reset</code>.
    </div>
  );
}

export function AppShell() {
  const { user, loading } = useSession();
  const loc = useLocation();
  if (loading) return <div className="page"><LoadingRows label="Loading session" /></div>;
  if (!user) return <LoginPage />;
  const nav = NAV.filter((n) => hasModule(user, n.module));
  const mobile = [
    { to: "/approvals", label: "Inbox", icon: Inbox, module: "approvals" },
    { to: "/cases", label: "Cases", icon: FolderKanban, module: "cases" },
    { to: "/workflows", label: "Runs", icon: Workflow, module: "workflows" },
    { to: "/evaluation", label: "Eval", icon: FlaskConical, module: "evaluation" },
    { to: "/impact", label: "Impact", icon: BarChart3, module: "impact" },
  ].filter((n) => hasModule(user, n.module)).slice(0, 3);
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to={homeFor(user.modules)} className="brand-link" aria-label="Karsa home">
            <span className="brand-mark"><Logo /></span>karsa.
          </NavLink>
          <nav className="nav" aria-label="Primary">
            {nav.map((n) => <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "active" : "")}>{n.label}</NavLink>)}
          </nav>
          <div className="topbar-right">
            <span className="demo-pill" title="All tenants, cases and numbers are fictional">Synthetic demo</span>
            <NotificationBell />
            <AccountMenu />
          </div>
        </div>
      </header>
      <FreshnessBanner />
      <main id="main" tabIndex={-1}>
        <Outlet key={loc.pathname.split("/")[1]} />
      </main>
      <nav className="bottom-bar" aria-label="Primary (mobile)">
        {mobile.map((m) => <NavLink key={m.to} to={m.to} className={({ isActive }) => (isActive ? "active" : "")}><m.icon size={20} aria-hidden="true" />{m.label}</NavLink>)}
        <NavLink to="/more" className={({ isActive }) => (isActive ? "active" : "")}><MoreHorizontal size={20} aria-hidden="true" />More</NavLink>
      </nav>
    </>
  );
}

export function RequireModule({ module, children }: { module: string; children: React.ReactNode }) {
  const { user } = useSession();
  if (!hasModule(user, module)) {
    return (
      <div className="page">
        <div className="empty" role="alert">
          <h1 style={{ fontSize: 20 }}>Not available for your role</h1>
          <p>{user?.name} ({user?.role_label}) does not have access to this module. The server enforces the same rule.</p>
          <Link className="btn btn-primary" to={homeFor(user?.modules ?? [])}>Go to your home page</Link>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

export function MorePage() {
  const { user, logout } = useSession();
  const links = [
    { to: "/evaluation", label: "Evaluation Lab", icon: FlaskConical, module: "evaluation" },
    { to: "/impact", label: "Transformation impact", icon: BarChart3, module: "impact" },
    { to: "/approvals", label: "Approval inbox", icon: ClipboardCheck, module: "approvals" },
    { to: "/audit", label: "Audit log", icon: ScrollText, module: "audit" },
    { to: "/manage", label: "Manage workspace", icon: Settings, module: "manage" },
  ].filter((l) => hasModule(user, l.module));
  return (
    <div className="page">
      <h1 className="page-title">More</h1>
      <p className="page-sub">Signed in as {user?.name} ({user?.role_label}). Analysis-heavy views work best on a larger screen.</p>
      <div className="stack" style={{ marginTop: 20 }}>
        {links.map((l) => <NavLink key={l.to} to={l.to} className="btn btn-secondary btn-lg"><l.icon size={18} aria-hidden="true" />{l.label}</NavLink>)}
        <button className="btn btn-secondary btn-lg" onClick={() => logout()}><LogOut size={18} aria-hidden="true" />Sign out</button>
      </div>
    </div>
  );
}
