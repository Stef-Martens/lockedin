import { formatDistance, formatPace, formatSwimPace, SPORT_LABEL } from "./format";
import type { ActivitySummary } from "./types";

export function activityTitle(a: ActivitySummary): string {
  if (a.title) return a.title;
  if (a.sub_type?.startsWith("walking")) return "Walk";
  if (a.sub_type?.includes("strength")) return "Strength (Watch)";
  if (a.source === "zwift") return "Zwift ride";
  if (a.sport === "swim") return a.sub_type?.includes("open_water") ? "Open water swim" : "Pool swim";
  return SPORT_LABEL[a.sport];
}

/** The one number that matters most for this kind of session. */
export function keyMetric(a: ActivitySummary): string | null {
  switch (a.sport) {
    case "bike":
      if (a.np) return `${Math.round(a.np)} W NP`;
      if (a.avg_power) return `${a.avg_power} W`;
      return a.distance_m ? formatDistance(a.distance_m, "bike") : null;
    case "run":
      return a.avg_pace_s_per_km ? formatPace(a.avg_pace_s_per_km) : null;
    case "swim":
      return a.swim_pace_s_per_100m ? formatSwimPace(a.swim_pace_s_per_100m) : null;
    case "gym":
      return a.set_count != null ? `${a.set_count} sets` : null;
    default:
      return a.avg_hr ? `${a.avg_hr} bpm` : null;
  }
}
