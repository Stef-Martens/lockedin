import { Link } from "react-router-dom";
import type { Point } from "../../components/SeriesChart";
import { Card } from "../../components/ui";
import type { EffortMix, FocusItem } from "../../lib/focus";
import { dayMs } from "../../lib/format";
import { stagger } from "../../lib/motion";
import { useApi } from "../../lib/useApi";

export type SessionItem = Extract<FocusItem, { type: "session" }>;

/** One chart point per row that has a value, x at noon UTC of its day. */
export function pts<T>(rows: T[], date: (r: T) => string, y: (r: T) => number | null | undefined): Point[] {
  return rows.filter((r) => y(r) != null).map((r) => ({ x: dayMs(date(r)), y: y(r) as number }));
}

export function Failed({ retry }: { retry: () => void }) {
  return (
    <Card>
      <p style={{ marginTop: 0 }}>Couldn't load this right now. Check your connection.</p>
      <button className="btn" onClick={retry}>Try again</button>
    </Card>
  );
}

export function useFocusSessions(): SessionItem[] {
  const { data } = useApi<{ session_suggestions: Omit<SessionItem, "type">[] }>("/api/focus");
  return (data?.session_suggestions ?? []).map((s) => ({ type: "session" as const, ...s }));
}

/** Empty state with a soft preview of the charts that will appear. */
export function Empty({ what, charts }: { what: string; charts: string[] }) {
  return (
    <>
      <Card i={1} className="row spread">
        <div style={{ maxWidth: 560 }}>
          <h2 style={{ fontSize: 30, margin: 0 }}>No {what} yet</h2>
          <p style={{ margin: "8px 0 0", lineHeight: 1.5, color: "var(--ink-2)" }}>
            {what === "gym workouts"
              ? "Upload your Hevy export on the Import page and your sets, muscle coverage and progress show up here."
              : `${what[0].toUpperCase()}${what.slice(1)} come from your Apple Watch through HealthFit. Once its iCloud folder is in your sync settings, past and new ones land here automatically.`}
          </p>
        </div>
        <Link to="/import" className="btn primary">Check sync status</Link>
      </Card>
      <div className="grid-auto" aria-hidden="true" style={{ ["--min" as string]: "300px" }}>
        {charts.map((c, n) => (
          <Card key={c} i={n + 2}>
            <h2 className="muted" style={{ fontSize: 18 }}>{c}</h2>
            <svg className="shimmer" viewBox="0 0 400 140" style={{ width: "100%", height: "auto", animationDelay: `${n * 0.3}s` }}>
              <polyline points={n % 2 ? "10,110 80,96 150,100 220,80 290,84 390,64" : "10,100 70,90 130,104 190,76 260,82 330,62 390,58"}
                fill="none" stroke="#3a3e42" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" />
            </svg>
          </Card>
        ))}
      </div>
    </>
  );
}

export function MixBar({ mix, i }: { mix: EffortMix; i?: number }) {
  const order = ["easy", "steady", "long", "hard"] as const;
  const colors = { easy: "#3ccf9a", steady: "#4d97ec", long: "#a68cff", hard: "#ff7a45" };
  const total = order.reduce((t, k) => t + mix.counts[k], 0);
  return (
    <div className="card rise" style={stagger(i ?? 0)}>
      <div className="eyebrow">Last 4 weeks by effort</div>
      {total ? (
        <>
          <div className="mix-bar">
            {order.filter((k) => mix.counts[k]).map((k) => (
              <div key={k} className="grow-x" style={{ width: `${(mix.counts[k] / total) * 100}%`, background: colors[k], animationDelay: ".4s" }} />
            ))}
          </div>
          <div className="row spread mix-legend">
            {order.map((k) => (
              <span key={k} className="row" style={{ gap: 6, color: mix.counts[k] ? "var(--ink)" : undefined }}>
                <span className="dot" style={{ background: colors[k], width: 8, height: 8 }} />{k[0].toUpperCase() + k.slice(1)} {mix.counts[k]}
              </span>
            ))}
          </div>
        </>
      ) : (
        <p className="secondary" style={{ margin: "12px 0 0", fontSize: 14 }}>No heart-rate or power data to classify yet.</p>
      )}
    </div>
  );
}

export function TryThis({ items, sport, i }: { items: SessionItem[]; sport: string; i?: number }) {
  const mine = items.filter((s) => s.sport === sport);
  if (!mine.length) return null;
  return (
    <Card variant="accent" i={i}>
      <div className="eyebrow" style={{ color: "var(--accent)", fontWeight: 600 }}>Try this</div>
      {mine.map((s, n) => (
        <div key={n} style={{ marginTop: 6, fontSize: 16 }}><strong>{s.title}</strong>: {s.detail} <span className="secondary">· {s.reason.toLowerCase()}</span></div>
      ))}
    </Card>
  );
}
