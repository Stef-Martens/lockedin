import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { supabase } from "../lib/supabase";
import type { Status } from "../lib/types";

const LINKS = [
  { to: "/", label: "Overview", short: "Home", end: true },
  { to: "/agenda", label: "Agenda", short: "Agenda" },
  { to: "/coach", label: "Coach", short: "Coach" },
  { to: "/activities", label: "Activities", short: "Activities" },
  { to: "/trends/bike", label: "Trends", short: "Trends", match: "/trends" },
  { to: "/muscles", label: "Muscles", short: "Muscles" },
  { to: "/body", label: "Body", short: "Body" },
  { to: "/import", label: "Import", short: "Import" },
];

// The phone tab bar keeps the everyday pages; the rest sit under "More".
const TABS = ["/", "/agenda", "/coach", "/activities", "/muscles"];

function MoreMenu({ links, active }: { links: typeof LINKS; active: boolean }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); button.current?.focus(); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="tab-more" ref={wrap}>
      <button ref={button} className={active ? "active" : ""} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>More</button>
      {open && (
        <div className="tab-more-menu pop" role="menu">
          {links.map((l) => <NavLink key={l.to} to={l.to} role="menuitem" onClick={() => setOpen(false)}>{l.label}</NavLink>)}
        </div>
      )}
    </div>
  );
}

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
      <nav className="tabbar" aria-label="Tabs">
        {LINKS.filter((l) => TABS.includes(l.to)).map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={cls("", l)}>{l.short}</NavLink>
        ))}
        <MoreMenu links={LINKS.filter((l) => !TABS.includes(l.to))}
          active={LINKS.some((l) => !TABS.includes(l.to) && pathname.startsWith(l.match ?? l.to))} />
      </nav>
    </div>
  );
}
