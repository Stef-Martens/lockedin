import type { Session } from "@supabase/supabase-js";
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { supabase } from "./lib/supabase";
import Activities from "./pages/Activities";
import ActivityDetail from "./pages/ActivityDetail";
import Body from "./pages/Body";
import Import from "./pages/Import";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Trends from "./pages/Trends";

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

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
        <Route path="body" element={<Body />} />
        <Route path="login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
