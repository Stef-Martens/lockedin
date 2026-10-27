import { dayMonth, todayLocal } from "./format";

export type TimeOffReason = "vacation" | "injury";
export type TimeOffCategory = "run" | "bike" | "swim" | "upper" | "core" | "lower" | "all";
export interface Restriction { category: TimeOffCategory; until: string }

/** GET /api/time-off: `end` is the latest restriction end. */
export interface TimeOffEntry {
  id: number;
  reason: TimeOffReason;
  label: string | null;
  start: string;
  end: string;
  restrictions: Restriction[];
}
/** A day of an agenda week inside a time-off window; `text` is "no running, no upper body" or "everything off". */
export interface TimeOffDay { day: string; reason: TimeOffReason; label: string | null; text: string }
/** A window to shade on the forecast charts. */
export interface TimeOffWindow { start: string; end: string; reason: TimeOffReason; label: string | null }

export type PartCategory = Exclude<TimeOffCategory, "all">;
export const PARTS: { category: PartCategory; name: string; off: string }[] = [
  { category: "run", name: "Running", off: "running" }, { category: "bike", name: "Cycling", off: "cycling" },
  { category: "swim", name: "Swimming", off: "swimming" }, { category: "upper", name: "Upper body", off: "upper body" },
  { category: "core", name: "Core", off: "core" }, { category: "lower", name: "Lower body", off: "lower body" },
];

export const reasonName = (reason: TimeOffReason, label: string | null) => label || (reason === "vacation" ? "Vacation" : "Injury");

/** "Operation · from 3 Dec · no running until 17 Dec, no upper body until 2 Jan". */
export function entryLine(e: TimeOffEntry): string {
  const what = e.restrictions.map((r) => r.category === "all" ? `everything off until ${dayMonth(r.until)}`
    : `no ${PARTS.find((p) => p.category === r.category)?.off ?? r.category} until ${dayMonth(r.until)}`);
  return [reasonName(e.reason, e.label), `from ${dayMonth(e.start)}`, what.join(", ")].join(" · ");
}

/** The thin band on a week-view day: "Operation · no running, no upper body", or just "Vacation". */
export function bandText(d: TimeOffDay): string {
  const name = reasonName(d.reason, d.label);
  return d.reason === "vacation" && d.text === "everything off" ? name : `${name} · ${d.text}`;
}

export interface TimeOffForm {
  reason: TimeOffReason;
  label: string;
  start: string;
  /** "Everything off" until this day; empty: not used. */
  all: string;
  /** Per activity: the day it is off until; empty: fine. */
  until: Record<PartCategory, string>;
}

export const emptyForm = (): TimeOffForm => ({
  reason: "vacation", label: "", start: todayLocal(), all: "",
  until: { run: "", bike: "", swim: "", upper: "", core: "", lower: "" },
});

export function formFromEntry(e: TimeOffEntry): TimeOffForm {
  const form: TimeOffForm = { ...emptyForm(), reason: e.reason, label: e.label ?? "", start: e.start };
  for (const r of e.restrictions) {
    if (r.category === "all") form.all = r.until;
    else form.until[r.category] = r.until;
  }
  return form;
}

/** The request body, or null when nothing is off. */
export function formBody(f: TimeOffForm) {
  const restrictions: Restriction[] = [
    ...(f.all ? [{ category: "all" as const, until: f.all }] : []),
    ...PARTS.filter((p) => f.until[p.category]).map((p) => ({ category: p.category, until: f.until[p.category] })),
  ];
  return restrictions.length ? { reason: f.reason, label: f.label.trim() || null, start: f.start, restrictions } : null;
}
