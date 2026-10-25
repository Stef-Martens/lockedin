import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { activityTitle, keyMetric } from "../lib/activity";
import { apiFetch } from "../lib/api";
import { formatDate, formatDistance, formatDuration, SPORT_LABEL, type Sport } from "../lib/format";
import { stagger } from "../lib/motion";
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

  useEffect(() => { load(); }, [load]);

  const setFilter = (n: { sport?: Sport | "all"; all?: boolean }) => {
    const s = n.sport ?? sport;
    const a = n.all ?? showAll;
    setParams({ ...(s !== "all" ? { sport: s } : {}), ...(a ? { all: "1" } : {}) });
  };

  return (
    <>
      <PageHeader title="Activities" right={
        <div className="chips" role="group" aria-label="Filter by sport">
          {FILTERS.map((f) => (
            <button key={f} className="chip" aria-pressed={sport === f} onClick={() => setFilter({ sport: f })}>
              {f !== "all" && <span className="dot" style={{ background: `var(--sport-${f})` }} />}
              {f === "all" ? "All" : SPORT_LABEL[f]}
            </button>
          ))}
          <button className="chip" aria-pressed={showAll} onClick={() => setFilter({ all: !showAll })}
            title="Show walks and Apple Watch recordings that duplicate a Zwift ride or Hevy workout">Walks &amp; duplicates</button>
        </div>
      } />

      <section className="card rise" style={{ ...stagger(1), padding: 10 }}>
        {error && <p className="error" style={{ padding: 12 }}>{error}</p>}
        {!loading && !error && items.length === 0 && (
          <div style={{ padding: 16 }}>
            <p style={{ marginTop: 0 }}>Nothing here yet.</p>
            <p className="secondary" style={{ marginBottom: 0 }}>Rides and Watch workouts appear after the Mac sync runs, or <Link to="/import">import files yourself</Link>.</p>
          </div>
        )}
        {items.length > 0 && (
          <div className="activity-table">
            <div className="activity-row head" aria-hidden="true">
              <span>Date</span><span>Activity</span><span className="r">Time</span><span className="r hide-sm">Distance</span><span className="r">Key metric</span><span className="r hide-sm">TSS</span>
            </div>
            {items.map((a, n) => (
              <Link key={a.id} to={`/activities/${a.id}`} className="activity-row list-item rise" style={stagger(Math.min(n, 15), 0.05, 0.03)}>
                <span className="secondary num">{formatDate(a.start_at)}</span>
                <span className="row" style={{ gap: 10, flexWrap: "nowrap", minWidth: 0 }}>
                  <span className="dot" style={{ background: `var(--sport-${a.sport})` }} />
                  <span style={{ fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {activityTitle(a)}{a.superseded_by && <span className="muted" style={{ fontWeight: 400 }}> · duplicate</span>}
                  </span>
                </span>
                <span className="r num">{formatDuration(a.duration_s)}</span>
                <span className="r num secondary hide-sm">{a.distance_m ? formatDistance(a.distance_m, a.sport) : "–"}</span>
                <span className="r display num" style={{ fontSize: 20, fontWeight: 600 }}>{keyMetric(a) ?? "–"}</span>
                <span className="r num secondary hide-sm">{a.tss ? Math.round(a.tss) : "–"}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
      {next && (
        <div style={{ textAlign: "center" }}>
          <button className="btn" disabled={loading} onClick={() => load(next)}>{loading ? "Loading…" : "Load more"}</button>
        </div>
      )}
    </>
  );
}
