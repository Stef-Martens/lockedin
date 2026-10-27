export type Sport = "bike" | "run" | "swim" | "gym" | "other";

const TZ = "Europe/Brussels";

const pad = (n: number) => String(n).padStart(2, "0");

/** h:mm:ss above an hour, m:ss below: durations, clock positions in a session, paces. */
export function formatDuration(s: number): string {
  const total = Math.round(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

/** Whole minutes with a prime, "45′"; "–" when there's nothing. */
export function formatMin(s: number | null | undefined): string {
  return s == null ? "–" : `${Math.round(s / 60)}′`;
}

export const formatPace = (sPerKm: number) => `${formatDuration(sPerKm)} /km`;
export const formatSwimPace = (sPer100: number) => `${formatDuration(sPer100)} /100m`;

/** Pace for a run (per km) or a swim (per 100 m); "–" when there's none. */
export function formatSportPace(s: number | null | undefined, sport: "run" | "swim"): string {
  if (s == null) return "–";
  return sport === "run" ? formatPace(s) : formatSwimPace(s);
}

export function formatDistance(m: number, sport: Sport): string {
  return sport === "swim" ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
});

/** "Sun 25 Oct, 23:30" in Brussels time. */
export function formatDate(iso: string): string {
  const p = Object.fromEntries(dateFmt.formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
  return `${p.weekday} ${p.day} ${p.month}, ${p.hour}:${p.minute}`;
}

/** "Sunday 25 October, 23:30" in Brussels time. */
export function formatDateLong(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: TZ });
}

/**
 * A calendar day ("2026-10-25", or a chart's epoch-ms at noon UTC) in words, e.g. { day: "numeric", month: "short" }
 * → "25 Oct". The day is never shifted by the device's time zone.
 */
export function formatDay(day: string | number, opts: Intl.DateTimeFormatOptions): string {
  const d = typeof day === "number" ? new Date(day) : new Date(`${day}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", { ...opts, timeZone: "UTC" });
}

/** "25 Oct" */
export const dayMonth = (day: string | number) => formatDay(day, { day: "numeric", month: "short" });
/** "Sun 25 Oct" */
export const shortDay = (day: string) => formatDay(day, { weekday: "short", day: "numeric", month: "short" });
/** "25 Oct 2026" */
export const dayMonthYear = (day: string) => formatDay(day, { day: "numeric", month: "short", year: "numeric" });
/** "Sunday 25 October" */
export const longDay = (day: string) => formatDay(day, { weekday: "long", day: "numeric", month: "long" });

/** Noon UTC of a calendar day as epoch ms: the x value of a per-day chart point. */
export const dayMs = (day: string) => new Date(`${day}T12:00:00Z`).getTime();

/** The calendar day `n` days after `day` (calendar maths, so DST can't shift it). */
export function addDays(day: string, n: number): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

/** YYYY-MM-DD for today in Brussels, for date inputs and "is it today" checks. */
export function todayLocal(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(now);
}

/** ISO week number of a calendar day. */
export function isoWeek(day: string): number {
  const [y, m, d] = day.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  return Math.ceil(((t.getTime() - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
}

/** "just now", "5 min ago", "3 h ago", "yesterday", "4 days ago"; "never" without a time. */
export function ago(iso: string | null, now = Date.now()): string {
  if (!iso) return "never";
  const mins = Math.round((now - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

/** Within the last 24 hours. */
export const recent = (iso: string | null, now = Date.now()) => !!iso && now - new Date(iso).getTime() < 24 * 3600 * 1000;

export const SPORT_LABEL: Record<Sport, string> = { bike: "Bike", run: "Run", swim: "Swim", gym: "Gym", other: "Other" };
