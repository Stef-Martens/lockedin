import type { Point } from "../components/SeriesChart";

/** Centred moving average for display (1 Hz power is too spiky to read); gaps stay gaps. */
export function smooth(points: Point[], window: number): Point[] {
  if (window <= 1) return points;
  const half = Math.floor(window / 2);
  return points.map((p, i) => {
    if (p.y == null) return p;
    let sum = 0;
    let n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(points.length - 1, i + half); j++) {
      const y = points[j].y;
      if (y != null) { sum += y; n++; }
    }
    return { x: p.x, y: Math.round((sum / n) * 10) / 10 };
  });
}
