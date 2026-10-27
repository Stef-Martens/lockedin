import { Link } from "react-router-dom";
import SeriesChart from "../../components/SeriesChart";
import { Card, SectionHead, Tile } from "../../components/ui";
import type { Forecast, RacePrediction } from "../../lib/forecast";
import { dayMonth, dayMs, formatDuration, formatPace } from "../../lib/format";

type From = RacePrediction["from"];

/** "your 8.2 km run on 20 Oct", linked to the run. */
function FromRun({ f }: { f: From }) {
  return <Link to={`/activities/${f.activity_id}`}>your {f.km.toFixed(1)} km run on {dayMonth(f.day)}</Link>;
}

/** Predicted 5k / 10k / half marathon from the best recent run, and how the 5k prediction has moved. */
export default function RaceTimes({ race, i }: { race: NonNullable<Forecast["race"]>; i: number }) {
  const { predictions, history, note } = race;
  const runs = new Set(predictions.map((p) => p.from.activity_id));
  const shared = runs.size === 1 ? predictions[0].from : null;
  return (
    <Card i={i}>
      <SectionHead title="Race times" />
      <div className="tiles">
        {predictions.map((p, n) => (
          <Tile key={p.name} label={p.name} value={formatDuration(p.seconds)} i={i + n + 1}
            hint={<>{formatPace(p.seconds / p.km)}{!shared && <span className="forecast-from">from <FromRun f={p.from} /></span>}</>} />
        ))}
      </div>
      {shared && <p className="forecast-from">from <FromRun f={shared} /></p>}
      {history.length > 1 && (
        <div className="forecast-race-chart">
          <SeriesChart bare title="Predicted 5k" summary="faster is higher" points={history.map(([day, s]) => ({ x: dayMs(day), y: s }))}
            colorVar="--series-pace" formatX={dayMonth} formatY={formatDuration} reversed height={160} />
        </div>
      )}
      {note && <p className="muted quiet-note forecast-note">{note}</p>}
    </Card>
  );
}
