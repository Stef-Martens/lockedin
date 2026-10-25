import { NavLink, Outlet, useLocation } from "react-router-dom";
import { supabase } from "../lib/supabase";

const LINKS = [
  { to: "/", label: "Overview", short: "Home", end: true },
  { to: "/activities", label: "Activities", short: "Activities" },
  { to: "/trends/bike", label: "Trends", short: "Trends", match: "/trends" },
  { to: "/body", label: "Body", short: "Body" },
  { to: "/import", label: "Import", short: "Import" },
];

export default function Layout() {
  const { pathname } = useLocation();
  const cls = (l: (typeof LINKS)[number]) => ({ isActive }: { isActive: boolean }) =>
    isActive || (l.match && pathname.startsWith(l.match)) ? "active" : "";
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          Locked<span>In</span>
        </NavLink>
        <nav className="topnav" aria-label="Main">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={cls(l)}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <button className="btn ghost" onClick={() => supabase.auth.signOut()}>
          Sign out
        </button>
      </header>
      <main className="main">
        <Outlet />
      </main>
      <nav className="tabbar" aria-label="Main">
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end} className={cls(l)}>
            {l.short}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
