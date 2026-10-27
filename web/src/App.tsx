import type { Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Layout from "./components/Layout";
import { handleSessionExpired, loginPath } from "./lib/api";
import { supabase } from "./lib/supabase";
import Activities from "./pages/Activities";
import Agenda from "./pages/Agenda";
import ActivityDetail from "./pages/ActivityDetail";
import Body from "./pages/Body";
import Coach from "./pages/Coach";
import Import from "./pages/Import";
import Login, { AfterLogin } from "./pages/Login";
import Muscles from "./pages/Muscles";
import Overview from "./pages/Overview";
import Plan from "./pages/Plan";
import SessionPage from "./pages/Session";
import Trends from "./pages/Trends";

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const navigate = useNavigate();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);
  // A session that can't be refreshed: the sign-out flips `session` above to the login screen; this only
  // puts /login?next=… in the address bar, without reloading the app.
  useEffect(() => handleSessionExpired((next) => navigate(loginPath(next), { replace: true })), [navigate]);

  if (session === undefined) return null;
  if (!session) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="activities" element={<Activities />} />
        <Route path="activities/:id" element={<ActivityDetail />} />
        <Route path="import" element={<Import />} />
        <Route path="trends" element={<Navigate to="/trends/bike" replace />} />
        <Route path="trends/:sport" element={<Trends />} />
        <Route path="agenda" element={<Agenda />} />
        <Route path="agenda/:id" element={<SessionPage />} />
        <Route path="muscles" element={<Muscles />} />
        <Route path="plan" element={<Plan />} />
        <Route path="body" element={<Body />} />
        <Route path="coach" element={<Coach />} />
        <Route path="coach/:id" element={<Coach />} />
        <Route path="login" element={<AfterLogin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
