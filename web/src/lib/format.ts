export type Sport = "bike" | "run" | "swim" | "gym" | "other";

const TZ = "Europe/Brussels";

const pad = (n: number) => String(n).padStart(2, "0");

/** h:mm:ss above an hour, m:ss below. */
export function formatDuration(s: number): string {
  const total = Math.round(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

function minSec(s: number): string {
  const total = Math.round(s);
  return `${Math.floor(total / 60)}:${pad(total % 60)}`;
}

export const formatPace = (sPerKm: number) => `${minSec(sPerKm)} /km`;
export const formatSwimPace = (sPer100: number) => `${minSec(sPer100)} /100m`;

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

/** YYYY-MM-DD for today in Brussels, for date inputs. */
export function todayLocal(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

export const SPORT_LABEL: Record<Sport, string> = { bike: "Bike", run: "Run", swim: "Swim", gym: "Gym", other: "Other" };
