import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { supabase } from "../lib/supabase";
import type { Status } from "../lib/types";

const LINKS = [
  { to: "/", label: "Overview", short: "Home", end: true },
  { to: "/coach", label: "Coach", short: "Coach" },
  { to: "/activities", label: "Activities", short: "Activities" },
  { to: "/trends/bike", label: "Trends", short: "Trends", match: "/trends" },
  { to: "/muscles", label: "Muscles", short: "Muscles" },
  { to: "/body", label: "Body", short: "Body" },
  { to: "/import", label: "Import", short: "Import" },
];

function ago(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 60) return `${Math.max(mins, 1)} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}

export default function Layout() {
  const { pathname } = useLocation();
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    apiFetch<Status>("/api/status").then(setStatus).catch(() => undefined);
  }, [pathname]);

  const cls = (base: string, l: (typeof LINKS)[number]) => ({ isActive }: { isActive: boolean }) =>
    `${base}${isActive || (l.match && pathname.startsWith(l.match)) ? " active" : ""}`;
  const last = status?.zwift.last_import_at ?? null;
  const live = !!last && Date.now() - new Date(last).getTime() < 24 * 3600 * 1000;

  return (
    <div className="shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand">Locked<span>In</span></NavLink>
        <nav className="side-nav" aria-label="Main">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={cls("nav-link", l)}>{l.label}</NavLink>
          ))}
        </nav>
        <div className="side-foot">
          <span className="row" style={{ gap: 8 }}>
            <span className={`sync-dot${live ? " live pulse" : ""}`} aria-hidden="true" />
            Mac sync · {ago(last)}
          </span>
          <button className="link-btn" onClick={() => supabase.auth.signOut()}>Sign out</button>
        </div>
      </aside>
      <header className="topbar">
        <NavLink to="/" className="brand">Locked<span>In</span></NavLink>
        <button className="link-btn" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </header>
      <main className="main">
        <div className="container">
          <Outlet />
        </div>
      </main>
      <nav className="tabbar" aria-label="Main">
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={cls("", l)}>{l.short}</NavLink>
        ))}
      </nav>
    </div>
  );
}
