import { type FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { stagger } from "../lib/motion";
import { supabase } from "../lib/supabase";

/** Where to go after signing in: `?next=` when it's a page of this app, else home. */
export function nextPath(search: string): string {
  const next = new URLSearchParams(search).get("next");
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/";
}

/** Signed in on /login (e.g. after the session expired): back to the page you were on. */
export function AfterLogin() {
  const { search } = useLocation();
  return <Navigate to={nextPath(search)} replace />;
}

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      // Only a real credentials mismatch gets the friendly message; config problems show Supabase's reason.
      setError(error.code === "invalid_credentials" ? "That email and password don't match. Try again." : error.message);
    }
    setBusy(false);
  }

  return (
    <div className="login">
      <div className="login-inner">
        <div className="rise">
          <div className="wordmark">Locked<span>In</span></div>
          <div className="secondary" style={{ marginTop: 10 }}>Your rides, runs, swims and lifts. One place.</div>
        </div>
        <form className="card rise stack" style={{ ...stagger(1), padding: 28 }} onSubmit={submit}>
          <label className="field">Email
            <input type="email" autoComplete="username" required value={email} placeholder="you@example.com" onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="field">Password
            <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <p className="error" style={{ margin: 0 }}>{error}</p>}
          <button className="btn primary" disabled={busy} style={{ width: "100%", padding: 14, fontSize: 16 }}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <div className="muted rise" style={{ ...stagger(2), textAlign: "center", fontSize: 13 }}>Private app · one account only</div>
      </div>
    </div>
  );
}
