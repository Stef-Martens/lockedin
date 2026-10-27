import { useEffect, useState } from "react";
import { Card, SectionHead, Segmented } from "../../components/ui";
import { apiDownload, apiFetch } from "../../lib/api";
import type { Profile } from "../../lib/types";

type ReminderFields = Pick<Profile, "reminder_weeks" | "reminder_hevy">;

/** How often the calendar reminds you. Saving hands the updated profile up, so the page header follows. */
export default function ReminderCard({ profile, ready, onSaved }: { profile: Profile; ready: boolean; onSaved: (p: Profile) => void }) {
  const [weeks, setWeeks] = useState(profile.reminder_weeks);
  const [hevy, setHevy] = useState(profile.reminder_hevy);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);
  useEffect(() => { setWeeks(profile.reminder_weeks); setHevy(profile.reminder_hevy); }, [profile.reminder_weeks, profile.reminder_hevy]);
  const every = weeks === 1 ? "week" : `${weeks} weeks`;

  // Only the reminder fields go to the server, so nothing else in the profile can be overwritten.
  async function save(change: Partial<ReminderFields>, undo: () => void) {
    setNote(null);
    try {
      const saved = await apiFetch<Profile | null>("/api/profile", { method: "PATCH", body: JSON.stringify(change) });
      onSaved(saved && typeof saved === "object" ? { ...profile, ...saved } : { ...profile, ...change });
      setNote({ text: "Saved. Add the calendar event again so it uses the new setting (and remove the old one).", ok: true });
    } catch (e) {
      undo();
      setNote({ text: (e as Error).message, ok: false });
    }
  }
  async function download() {
    setNote(null);
    try {
      const how = await apiDownload("/api/reminders/calendar.ics", "lockedin-checkin.ics", "text/calendar");
      setNote({ ok: true, text: how === "shared"
        ? "Choose Calendar in the share sheet to add the reminder."
        : `Downloaded. Open lockedin-checkin.ics to add a reminder every ${every}${hevy ? ", with the Hevy upload" : ""}.` });
    } catch (e) {
      if ((e as Error).name !== "AbortError") setNote({ text: (e as Error).message, ok: false });
    }
  }
  return (
    <Card i={4}>
      <SectionHead title="Reminder" />
      <p className="secondary" style={{ marginTop: -4, fontSize: 14, lineHeight: 1.5 }}>Your calendar reminds you; the event opens this check-in.</p>
      <fieldset disabled={!ready} className="plain">
        <Segmented label="Remind me every" value={weeks} onChange={(w) => { const prev = weeks; setWeeks(w); save({ reminder_weeks: w }, () => setWeeks(prev)); }}
          options={[{ value: 1, label: "Every week" }, { value: 2, label: "Every 2 weeks" }, { value: 4, label: "Every 4 weeks" }]} />
        <label className="row check-row reminder-hevy">
          <input type="checkbox" checked={hevy} onChange={(e) => { const v = e.target.checked; setHevy(v); save({ reminder_hevy: v }, () => setHevy(!v)); }} />
          Also remind me to upload my Hevy export
        </label>
        <div className="row" style={{ marginTop: 16 }}>
          <button type="button" className="btn primary" onClick={download}>Add to calendar</button>
          <span style={{ fontSize: 13, color: note ? (note.ok ? "var(--accent)" : "var(--danger)") : "var(--ink-muted)" }}>
            {note?.text ?? "Adds a repeating event to iPhone or Mac Calendar."}
          </span>
        </div>
      </fieldset>
    </Card>
  );
}
