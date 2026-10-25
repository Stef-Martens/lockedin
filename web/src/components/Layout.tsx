import { NavLink, Outlet } from "react-router-dom";
import { supabase } from "../lib/supabase";

const LINKS = [
  { to: "/activities", label: "Activities" },
  { to: "/import", label: "Import" },
  { to: "/body", label: "Body" },
];

export default function Layout() {
  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand">
          Locked<span>In</span>
        </NavLink>
        <nav className="topnav" aria-label="Main">
          {LINKS.map((l) => (
            <NavLink key={l.to} to={l.to}>
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
          <NavLink key={l.to} to={l.to}>
            {l.label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
