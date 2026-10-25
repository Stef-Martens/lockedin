import type { Coverage, FocusItem } from "../lib/focus";
import { focusLine } from "../lib/focus";

type GymItem = Extract<FocusItem, { type: "gym" }>;
const REGIONS = ["chest", "shoulders", "arms", "back", "core", "legs"];
const STATUS_LABEL = { low: "low", ok: "ok", high: "a lot" } as const;

/** Sets per week per muscle against its target band; status is always written out, never colour-only. */
export default function MuscleCoverage({ coverage, suggestions }: { coverage: Coverage[]; suggestions: GymItem[] }) {
  const scale = Math.max(16, ...coverage.map((c) => Math.max(c.sets_per_week, c.target_high)));
  const byMuscle = new Map(suggestions.map((s) => [s.muscle_key, s]));
  return (
    <section className="card">
      <h2>Muscles, sets per week (last 4 weeks)</h2>
      {REGIONS.map((region) => {
        const rows = coverage.filter((c) => c.region === region);
        if (!rows.length) return null;
        return (
          <div key={region} className="coverage-group">
            <div className="muted coverage-region">{region}</div>
            {rows.map((c) => {
              const sugg = c.status === "low" ? byMuscle.get(c.key) : undefined;
              return (
                <div key={c.key} className="coverage-row">
                  <div className="coverage-name">{c.name}</div>
                  <div className="coverage-track" title={`target ${c.target_low}–${c.target_high}`}>
                    <div className="coverage-band" style={{ left: `${(c.target_low / scale) * 100}%`,
                      width: `${((c.target_high - c.target_low) / scale) * 100}%` }} />
                    <div className="coverage-bar" style={{ width: `${Math.min(100, (c.sets_per_week / scale) * 100)}%` }} />
                  </div>
                  <div className={`coverage-status num ${c.status}`}>
                    {c.sets_per_week.toFixed(c.sets_per_week % 1 ? 1 : 0)} · {STATUS_LABEL[c.status]}
                  </div>
                  {sugg && (
                    <div className="coverage-sugg secondary">
                      Try <strong>{focusLine(sugg).title}</strong>: {focusLine(sugg).detail}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
      <p className="muted" style={{ fontSize: "0.85rem", marginBottom: 0 }}>
        Shaded band = target range. A main-muscle set counts 1, a helping-muscle set counts ½. Warm-ups don't count.
      </p>
    </section>
  );
}
