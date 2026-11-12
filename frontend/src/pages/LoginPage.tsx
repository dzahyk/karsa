import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError } from "../api";
import { Logo } from "../components/AppShell";
import { Field } from "../components/ui";
import { useSession } from "../session";

type DemoAccount = { username: string; name: string; role: string; role_label: string; title: string; organization_id: string };

export function LoginPage() {
  const { login, demoLogin } = useSession();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const accounts = useQuery({ queryKey: ["demoAccounts"], queryFn: () => api.get<DemoAccount[]>("/auth/demo-accounts"), retry: false });
  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { setError(e instanceof ApiError ? e.message : "Sign-in failed."); } finally { setBusy(false); }
  };
  return (
    <main id="main" className="login-wrap">
      <div className="login-card panel">
        <div className="row" style={{ gap: 10, marginBottom: 6 }}>
          <span className="brand-mark" style={{ background: "var(--header)" }}><Logo /></span>
          <strong style={{ fontSize: 18 }}>karsa.</strong>
        </div>
        <h1 style={{ fontSize: 24, margin: "8px 0 4px" }}>Sign in</h1>
        <p className="small muted">Portfolio demo with synthetic data. Sessions use an HttpOnly cookie and a CSRF token.</p>
        <form className="stack" style={{ marginTop: 18 }} onSubmit={(e) => { e.preventDefault(); run(() => login(form.username, form.password)); }}>
          <Field label="Username">{({ id }) => <input id={id} className="input" autoComplete="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />}</Field>
          <Field label="Password">{({ id }) => <input id={id} type="password" className="input" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}</Field>
          {error && <div className="callout critical" role="alert">{error}</div>}
          <button className="btn btn-primary btn-lg" disabled={busy || !form.username || !form.password}>Sign in</button>
        </form>
        {accounts.data && (
          <section style={{ marginTop: 24 }} aria-labelledby="demo-accounts">
            <h2 id="demo-accounts" className="section-title">Demo accounts (synthetic)</h2>
            <p className="xs muted" style={{ marginBottom: 8 }}>One-click sign-in is available because the server runs with DEMO_MODE=true. The shared password is in the README.</p>
            <ul className="stack tight" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {accounts.data.map((a) => (
                <li key={a.username}>
                  <button className="demo-account" disabled={busy} onClick={() => run(() => demoLogin(a.username))}>
                    <span style={{ fontWeight: 600 }}>{a.name}</span>
                    <span className="small muted">{a.role_label}{a.organization_id !== "org_northstar" ? " · other tenant" : ""}</span>
                  </button>
                </li>))}
            </ul>
          </section>
        )}
      </div>
    </main>
  );
}
