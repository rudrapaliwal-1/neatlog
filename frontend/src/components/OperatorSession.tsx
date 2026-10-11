import { useEffect, useState, type ReactNode } from "react";
import { ShieldCheck, RefreshCw } from "lucide-react";
import { apiBaseUrl, request, setCsrfToken } from "../api/client";

type Session = { user: { id: string; email: string }; csrf_token: string };
export default function OperatorSession({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    request<Session>("/api/auth/me").then(value => { if (active) { setCsrfToken(value.csrf_token); setSession(value); } })
      .catch(() => {}).finally(() => { if (active) setLoading(false); });
    const expired = () => { setCsrfToken(""); setSession(null); setError("Your session expired. Please log in again."); };
    const logout = () => { request("/api/auth/logout", { method: "POST" }).finally(() => { setCsrfToken(""); setSession(null); }); };
    window.addEventListener("sentinel-session-expired", expired);
    window.addEventListener("sentinel-disconnect", logout);
    return () => { active = false; window.removeEventListener("sentinel-session-expired", expired); window.removeEventListener("sentinel-disconnect", logout); };
  }, []);
  async function submit() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const value = await request<Session>(register ? "/api/auth/register" : "/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setCsrfToken(value.csrf_token); setSession(value); setPassword("");
    } catch (e) { setError(e instanceof Error ? e.message : "Authentication failed"); }
    finally { setBusy(false); }
  }
  if (loading) return <main className="operator-connect"><RefreshCw className="spin"/> Restoring session…</main>;
  if (session) return <>{children}</>;
  return <main className="operator-connect"><section className="panel operator-card">
    <div className="eyebrow">TEAM BEYONDSIGHT / LIVE ENGINE</div><h1>SENTINEL<span className="text-cyan">-X</span></h1>
    <h2>{register ? "Create your account" : "Log in"}</h2><p>Upload a repository and review exact patch and verification evidence.</p>
    <form onSubmit={event => { event.preventDefault(); void submit(); }}>
      <label htmlFor="email">Email</label><input id="email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required />
      <label htmlFor="password">Password</label><input id="password" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete={register ? "new-password" : "current-password"} minLength={12} required />
      {error && <div className="error-banner" role="alert">{error}</div>}
      <button className="button button-primary" disabled={busy}>{busy ? <RefreshCw size={16} className="spin"/> : <ShieldCheck size={16}/>} {register ? "Register" : "Log in"}</button>
    </form><button className="text-link" onClick={() => { setRegister(!register); setError(""); }}>{register ? "Already have an account? Log in" : "New here? Register"}</button>
    <a className="text-link" href={`${apiBaseUrl}/docs`} target="_blank" rel="noreferrer">Backend API documentation ↗</a>
  </section></main>;
}
