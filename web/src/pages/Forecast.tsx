import { PageHeader } from "../components/ui";
import type { Forecast as ForecastData } from "../lib/forecast";
import { useApi } from "../lib/useApi";
import FitnessAhead from "./forecast/FitnessAhead";
import Ftp from "./forecast/Ftp";
import Goals from "./forecast/Goals";
import RaceTimes from "./forecast/RaceTimes";

/** Where am I heading, and when do I get there: goals, fitness, race times and FTP, each projected forward. */
export default function Forecast() {
  const { data, error } = useApi<ForecastData>("/api/forecast");
  const n = data?.goals.length ?? 0;
  return (
    <>
      <PageHeader title="Forecast" sub="Where you're heading, and when you get there." />
      {error ? <p className="muted quiet-note">The forecast isn't available right now.</p>
        : !data ? <p className="muted">Loading…</p>
        : (
          <>
            {data.time_off.length > 0 && <p className="muted quiet-note">Shaded stretches are time off.</p>}
            <Goals goals={data.goals} timeOff={data.time_off} />
            {data.fitness && data.fitness.days.length > 0 && <FitnessAhead days={data.fitness.days} timeOff={data.time_off} i={n + 1} />}
            {data.race && data.race.predictions.length > 0 && <RaceTimes race={data.race} i={n + 2} />}
            {data.ftp && <Ftp ftp={data.ftp} timeOff={data.time_off} i={n + 6} />}
          </>
        )}
    </>
  );
}
