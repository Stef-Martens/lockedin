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
        <Route index element={<Navigate to="/activities" replace />} />
        <Route path="activities" element={<Activities />} />
        <Route path="activities/:id" element={<ActivityDetail />} />
        <Route path="import" element={<Import />} />
        <Route path="body" element={<Body />} />
        <Route path="login" element={<Navigate to="/activities" replace />} />
        <Route path="*" element={<Navigate to="/activities" replace />} />
      </Route>
    </Routes>
  );
}
