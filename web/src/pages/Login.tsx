import { type FormEvent, useState } from "react";
import { supabase } from "../lib/supabase";

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
      <h1>
        Locked<span style={{ color: "var(--accent)" }}>In</span>
      </h1>
      <p className="secondary">Your training, in one place.</p>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          Email
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="field">
          Password
          <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={busy} style={{ width: "100%" }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
