import { describe, expect, it } from "vitest";
import {
  addDays, ago, dayMonth, dayMonthYear, dayMs, formatDate, formatDateLong, formatDay, formatDistance, formatDuration, formatMin, formatPace,
  formatSportPace, formatSwimPace, isoWeek, longDay, recent, shortDay, todayLocal,
} from "./format";

describe("format", () => {
  it("durations and clock times", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatDuration(605)).toBe("10:05");
    expect(formatDuration(59)).toBe("0:59");
    expect(formatDuration(0)).toBe("0:00");
  });
  it("minutes", () => {
    expect(formatMin(2700)).toBe("45′");
    expect(formatMin(null)).toBe("–");
    expect(formatMin(undefined)).toBe("–");
  });
  it("paces, one format everywhere", () => {
    expect(formatPace(300)).toBe("5:00 /km");
    expect(formatPace(337.5)).toBe("5:38 /km");
    expect(formatSwimPace(125)).toBe("2:05 /100m");
    expect(formatSportPace(342, "run")).toBe("5:42 /km");
    expect(formatSportPace(126.7, "swim")).toBe("2:07 /100m");
    expect(formatSportPace(null, "run")).toBe("–");
  });
  it("distances", () => {
    expect(formatDistance(12345, "bike")).toBe("12.3 km");
    expect(formatDistance(1500, "swim")).toBe("1500 m");
    expect(formatDistance(800, "run")).toBe("0.8 km");
  });
  it("dates in Brussels time", () => {
    // 22:30 UTC on Sun 25 Oct 2026 is 23:30 in Brussels
    expect(formatDate("2026-10-25T22:30:00Z")).toBe("Sun 25 Oct, 23:30");
    expect(formatDateLong("2026-10-25T22:30:00Z")).toBe("Sunday 25 October at 23:30");
  });
  it("calendar days, never shifted by the device's time zone", () => {
    expect(dayMonth("2026-10-25")).toBe("25 Oct");
    expect(dayMonth(dayMs("2026-10-25"))).toBe("25 Oct");
    expect(shortDay("2026-10-25")).toBe("Sun 25 Oct");
    expect(longDay("2026-10-25")).toBe("Sunday 25 October");
    expect(dayMonthYear("2026-10-25")).toBe("25 Oct 2026");
    expect(formatDay("2026-10-25", { weekday: "long" })).toBe("Sunday");
    expect(addDays("2026-10-24", 14)).toBe("2026-11-07");
    expect(addDays("2026-03-28", 1)).toBe("2026-03-29");  // across the switch to summer time
  });
  it("today is Brussels' today, also between midnight and 2 am", () => {
    expect(todayLocal(new Date("2026-10-26T23:30:00Z"))).toBe("2026-10-27");  // 00:30 in Brussels
    expect(todayLocal(new Date("2026-07-01T22:30:00Z"))).toBe("2026-07-02");  // 00:30 summer time
  });
  it("ISO weeks", () => {
    expect(isoWeek("2026-10-27")).toBe(44);
    expect(isoWeek("2026-01-01")).toBe(1);
    expect(isoWeek("2027-01-03")).toBe(53);
  });
  it("how long ago", () => {
    const now = Date.parse("2026-10-27T12:00:00Z");
    expect(ago(null, now)).toBe("never");
    expect(ago("2026-10-27T11:59:50Z", now)).toBe("just now");
    expect(ago("2026-10-27T11:55:00Z", now)).toBe("5 min ago");
    expect(ago("2026-10-27T09:00:00Z", now)).toBe("3 h ago");
    expect(ago("2026-10-26T10:00:00Z", now)).toBe("yesterday");
    expect(ago("2026-10-23T12:00:00Z", now)).toBe("4 days ago");
    expect(recent("2026-10-27T09:00:00Z", now)).toBe(true);
    expect(recent("2026-10-25T09:00:00Z", now)).toBe(false);
    expect(recent(null, now)).toBe(false);
  });
});
