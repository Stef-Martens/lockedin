import { shortDay } from "../lib/format";
import { formNumber, formWords, loadNumber } from "../lib/load";
import { useCssVar } from "../lib/useCssVar";

/** One day on a fitness/fatigue/form chart: the Training load card's days, or the Forecast's (with `planned`). */
export interface LoadRow { day: string; fitness: number; fatigue: number; form: number; load?: number; planned?: boolean }

/** The colours of the fitness, fatigue and form series, plus the chart chrome, resolved for SVG. */
export function useLoadColors() {
  return {
    fitness: useCssVar("--series-power"),
    fatigue: useCssVar("--series-pace"),
    form: useCssVar("--series-cadence"),
    grid: useCssVar("--hairline"),
    muted: useCssVar("--ink-muted"),
    axis: useCssVar("--axis"),
  };
}
export type LoadColors = ReturnType<typeof useLoadColors>;

/** Shared axis props: days along x (category), whole numbers up y. */
export function loadAxes(c: LoadColors, dayFormat: (day: string) => string) {
  return {
    x: { dataKey: "day", tickFormatter: dayFormat, tick: { fill: c.muted, fontSize: 12 }, stroke: c.axis, tickLine: false, minTickGap: 24 },
    y: { tick: { fill: c.muted, fontSize: 12 }, axisLine: false, tickLine: false, width: 40, allowDecimals: false },
  };
}

export function LoadLegend({ c }: { c: LoadColors }) {
  return (
    <span className="legend" aria-label="Legend">
      <span><i className="swatch" style={{ background: c.fitness }} />Fitness</span>
      <span><i className="swatch" style={{ background: c.fatigue }} />Fatigue</span>
      <span><i className="swatch" style={{ background: c.form }} />Form</span>
    </span>
  );
}

export function LoadReadout({ active, payload }: { active?: boolean; payload?: { payload: LoadRow }[] }) {
  const r = payload?.[0]?.payload;
  if (!active || !r) return null;
  return (
    <div className="chart-tooltip num">
      <div className="muted">{shortDay(r.day)}{r.load != null && ` · load ${loadNumber(r.load)}`}{r.planned && " · if you do what's planned"}</div>
      <div>Fitness <strong>{loadNumber(r.fitness)}</strong> · Fatigue <strong>{loadNumber(r.fatigue)}</strong></div>
      <div>Form <strong>{formNumber(r.form)}</strong> · {formWords(r.form).toLowerCase()}</div>
    </div>
  );
}
