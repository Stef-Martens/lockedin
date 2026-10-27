import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { ago, recent } from "../lib/format";
import { supabase } from "../lib/supabase";
import type { Status } from "../lib/types";
import { Icon } from "./icons";

const LINKS = [
  { to: "/", label: "Overview", short: "Home", icon: "home", end: true },
  { to: "/agenda", label: "Agenda", short: "Agenda", icon: "agenda" },
  { to: "/coach", label: "Coach", short: "Coach", icon: "coach" },
  { to: "/activities", label: "Activities", short: "Activities", icon: "activities" },
  { to: "/trends/bike", label: "Trends", short: "Trends", match: "/trends" },
  { to: "/muscles", label: "Muscles", short: "Muscles", icon: "muscles" },
  { to: "/body", label: "Body", short: "Body" },
  { to: "/import", label: "Import", short: "Import" },
];

// The phone tab bar keeps the everyday pages; the rest sit under "More".
const TABS = ["/", "/agenda", "/coach", "/activities", "/muscles"];

/** Sign out, after a confirm: it's one tap from the menu, and signing back in on a phone is a chore. */
function signOut() {
  if (window.confirm("Sign out of LockedIn?")) supabase.auth.signOut();
}

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
      <button ref={button} className={active ? "active" : ""} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Icon name="more" /><span>More</span>
      </button>
      {open && (
        <div className="tab-more-menu pop" role="menu">
          {links.map((l) => <NavLink key={l.to} to={l.to} role="menuitem" onClick={() => setOpen(false)}>{l.label}</NavLink>)}
          <button role="menuitem" className="tab-more-signout" onClick={() => { setOpen(false); signOut(); }}>Sign out</button>
        </div>
      )}
    </div>
  );
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
  const live = recent(last);
  const sync = (
    <span className="row sync" style={{ gap: 8 }}>
      <span className={`sync-dot${live ? " live pulse" : ""}`} aria-hidden="true" />
      Mac sync · {ago(last)}
    </span>
  );

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
          {sync}
          <button className="link-btn" onClick={signOut}>Sign out</button>
        </div>
      </aside>
      {/* Sign out lives under More on phones, away from the logo that's tapped to go home. */}
      <header className="topbar">
        <NavLink to="/" className="brand">Locked<span>In</span></NavLink>
        {sync}
      </header>
      <main className="main">
        <div className="container">
          <Suspense fallback={<p className="muted">Loading…</p>}>
            <Outlet />
          </Suspense>
        </div>
      </main>
      <nav className="tabbar" aria-label="Tabs">
        {LINKS.filter((l) => TABS.includes(l.to)).map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={cls("", l)}>
            {l.icon && <Icon name={l.icon} />}<span>{l.short}</span>
          </NavLink>
        ))}
        <MoreMenu links={LINKS.filter((l) => !TABS.includes(l.to))}
          active={LINKS.some((l) => !TABS.includes(l.to) && pathname.startsWith(l.match ?? l.to))} />
      </nav>
    </div>
  );
}
