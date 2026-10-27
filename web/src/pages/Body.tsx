import { PageHeader } from "../components/ui";
import { apiFetch } from "../lib/api";
import type { Checkin } from "../lib/body";
import type { MeasurementType, Profile } from "../lib/types";
import { useLoad } from "../lib/useApi";
import CheckinCard from "./body/CheckinCard";
import GuideCard from "./body/GuideCard";
import History from "./body/History";
import ProfileCard from "./body/ProfileCard";
import ReminderCard from "./body/ReminderCard";

const EMPTY: Profile = { date_of_birth: null, height_cm: null, sex: null, max_hr_override: null, ftp_override: null,
  resting_hr_override: null, dumbbell_weights: "pair", reminder_weeks: 2, reminder_hevy: true };

interface BodyData { types: MeasurementType[]; checkins: Checkin[]; profile: Profile }

export default function Body() {
  const { data, error, reload, setData } = useLoad<BodyData>("body", async (signal) => {
    const [types, checkins, profile] = await Promise.all([
      apiFetch<MeasurementType[]>("/api/measurement-types", { signal }),
      apiFetch<Checkin[]>("/api/checkins", { signal }),
      apiFetch<Profile>("/api/profile", { signal }),
    ]);
    return { types, checkins, profile };
  });
  const types = data?.types ?? [];
  const checkins = data?.checkins ?? [];
  const profile = data?.profile ?? EMPTY;
  const ready = data != null;
  // Both cards that change the profile put the saved version here, so the header and "next on …" follow at once.
  const setProfile = (p: Profile) => setData((d) => (d ? { ...d, profile: p } : d));

  const saveProfile = async (change: Partial<Profile>) =>
    setProfile(await apiFetch<Profile>("/api/profile", { method: "PATCH", body: JSON.stringify(change) }));
  const every = profile.reminder_weeks === 1 ? "week" : `${profile.reminder_weeks} weeks`;

  return (
    <>
      <PageHeader title="Body" sub={`A check-in every ${every}. Same time of day, before training.`} />
      {error && (
        <div className="note row spread"><span className="error">Couldn't load your body data: {error.message}</span><button className="btn" onClick={reload}>Try again</button></div>
      )}
      <CheckinCard types={types} checkins={checkins} weeks={profile.reminder_weeks} onSaved={reload} />
      <History types={types} checkins={checkins} onDeleted={reload} />
      <div className="grid-auto" style={{ ["--min" as string]: "420px" }}>
        <ProfileCard profile={profile} ready={ready} onSave={saveProfile} />
        <div className="column">
          <ReminderCard profile={profile} ready={ready} onSaved={setProfile} />
          <GuideCard onAdded={reload} />
        </div>
      </div>
    </>
  );
}
