import { ReferenceArea } from "recharts";
import type { TimeOffWindow } from "../../lib/timeoff";

/**
 * Time off as muted bands behind a chart. `at` turns a day into the chart's x (the day itself on a category
 * axis, epoch ms on a number axis); `span` is the chart's first and last x, so a window sticking out is cut to it
 * and one outside it is left out.
 */
export function timeOffAreas<X extends string | number>(windows: TimeOffWindow[], color: string, at: (day: string) => X, span: [X, X] | null) {
  if (!span) return [];
  return windows.flatMap((w) => {
    const [x1, x2] = [at(w.start) < span[0] ? span[0] : at(w.start), at(w.end) > span[1] ? span[1] : at(w.end)];
    return x1 > x2 ? [] : [<ReferenceArea key={`${w.start}-${w.end}`} x1={x1} x2={x2} fill={color} fillOpacity={0.16} stroke="none" ifOverflow="hidden" />];
  });
}
