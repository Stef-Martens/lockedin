import type { Coverage, FocusItem } from "../lib/focus";
import { focusLine } from "../lib/focus";
import { Card, SectionHead } from "./ui";

type GymItem = Extract<FocusItem, { type: "gym" }>;
const REGIONS = ["chest", "shoulders", "arms", "back", "core", "legs"];
const STATUS_LABEL = { low: "low", ok: "ok", high: "a lot" } as const;

/** Sets per week per muscle against its target band; status is always written out, never colour-only. */
export default function MuscleCoverage({ coverage, suggestions, i }: { coverage: Coverage[]; suggestions: GymItem[]; i?: number }) {
  const scale = Math.max(16, ...coverage.map((c) => Math.max(c.sets_per_week, c.target_high)));
  const byMuscle = new Map(suggestions.map((s) => [s.muscle_key, s]));
  let n = 0;
  return (
    <Card i={i}>
      <SectionHead title="Muscle coverage" right={<span className="muted" style={{ fontSize: 13 }}>sets / week · last 4 weeks</span>} />
      {REGIONS.map((region) => {
        const rows = coverage.filter((c) => c.region === region);
        if (!rows.length) return null;
        return (
          <div key={region}>
            <div className="coverage-region">{region}</div>
            {rows.map((c) => {
              const sugg = c.status === "low" ? byMuscle.get(c.key) : undefined;
              const line = sugg ? focusLine(sugg) : null;
              return (
                <div key={c.key} className="coverage-row">
                  <span className="coverage-name">{c.name}</span>
                  <div className="coverage-track" title={`target ${c.target_low}–${c.target_high} sets/week`}>
                    <div className="coverage-band" style={{ left: `${(c.target_low / scale) * 100}%`, width: `${((c.target_high - c.target_low) / scale) * 100}%` }} />
                    <div className="coverage-bar grow-x" style={{ width: `${Math.min(100, (c.sets_per_week / scale) * 100)}%`, animationDelay: `${(0.2 + 0.03 * n++).toFixed(2)}s` }} />
                  </div>
                  <span className="coverage-sets num">{c.sets_per_week.toFixed(c.sets_per_week % 1 ? 1 : 0)}</span>
                  <span className={`coverage-status ${c.status}`}>{STATUS_LABEL[c.status]}</span>
                  {line && <div className="coverage-sugg"><strong>Add</strong> {line.title}, {line.detail}</div>}
                </div>
              );
            })}
          </div>
        );
      })}
      <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>Shaded band = target range. A main-muscle set counts 1, a helping-muscle set ½, warm-ups 0.</p>
    </Card>
  );
}
