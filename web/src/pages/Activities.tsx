import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import SportDot from "../components/SportDot";
import { activityTitle, keyMetric } from "../lib/activity";
import { apiFetch } from "../lib/api";
import { formatDate, formatDistance, formatDuration, SPORT_LABEL, type Sport } from "../lib/format";
import type { ActivityPage, ActivitySummary } from "../lib/types";

const FILTERS: (Sport | "all")[] = ["all", "bike", "run", "swim", "gym", "other"];

export default function Activities() {
  const [params, setParams] = useSearchParams();
  const sport = (params.get("sport") as Sport | null) ?? "all";
  const showAll = params.get("all") === "1";
  const [items, setItems] = useState<ActivitySummary[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (before?: string) => {
    setLoading(true);
    setError(null);
    const q = new URLSearchParams({ limit: "30" });
    if (sport !== "all") q.set("sport", sport);
    if (showAll) {
      q.set("include_walks", "true");
      q.set("include_superseded", "true");
    }
    if (before) q.set("before", before);
    try {
      const page = await apiFetch<ActivityPage>(`/api/activities?${q}`);
      setItems((prev) => (before ? [...prev, ...page.items] : page.items));
      setNext(page.next_before);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [sport, showAll]);

  const setFilter = (next: { sport?: Sport | "all"; all?: boolean }) => {
    const s = next.sport ?? sport;
    const a = next.all ?? showAll;
    setParams({ ...(s !== "all" ? { sport: s } : {}), ...(a ? { all: "1" } : {}) });
  };

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <h1>Activities</h1>
      <div className="chips" role="group" aria-label="Filter by sport">
        {FILTERS.map((f) => (
          <button key={f} className="chip" aria-pressed={sport === f}
            onClick={() => setFilter({ sport: f })}>
            {f !== "all" && <SportDot sport={f} />}
            {f === "all" ? "All" : SPORT_LABEL[f]}
          </button>
        ))}
        <button className="chip" aria-pressed={showAll} onClick={() => setFilter({ all: !showAll })}
          title="Show walks and Apple Watch recordings that duplicate a Zwift ride or Hevy workout">
          Walks &amp; duplicates
        </button>
      </div>
      <section className="card" style={{ padding: 4 }}>
        {error && <p className="error" style={{ padding: 12 }}>{error}</p>}
        {!loading && !error && items.length === 0 && (
          <div style={{ padding: 16 }}>
            <p style={{ marginTop: 0 }}>Nothing here yet.</p>
            <p className="secondary" style={{ marginBottom: 0 }}>
              Your Zwift rides and Watch workouts show up after the Mac sync runs, or{" "}
              <Link to="/import">import files yourself</Link>.
            </p>
          </div>
        )}
        <ul className="list">
          {items.map((a) => (
            <li key={a.id}>
              <Link to={`/activities/${a.id}`} className="list-item">
                <SportDot sport={a.sport} />
                <div>
                  <div className="list-title">
                    {activityTitle(a)}
                    {a.superseded_by && <span className="muted" style={{ fontWeight: 400 }}> · duplicate</span>}
                  </div>
                  <div className="list-meta num">
                    {formatDate(a.start_at)} · {formatDuration(a.duration_s)}
                    {a.distance_m ? ` · ${formatDistance(a.distance_m, a.sport)}` : ""}
                  </div>
                </div>
                <div className="list-metric num">{keyMetric(a)}</div>
              </Link>
            </li>
          ))}
        </ul>
        {next && (
          <div style={{ padding: 12, textAlign: "center" }}>
            <button className="btn" disabled={loading} onClick={() => load(next)}>
              {loading ? "Loading…" : "Load more"}
            </button>
          </div>
        )}
      </section>
    </>
  );
}
