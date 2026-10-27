import { Card, SectionHead } from "../../components/ui";
import { type Forecast, FTP_FROM } from "../../lib/forecast";
import type { TimeOffWindow } from "../../lib/timeoff";
import ProjectionChart, { ProjectionLegend } from "./ProjectionChart";

/** Today's FTP and who set it, how it has stepped, and where it's heading. */
export default function Ftp({ ftp, timeOff, i }: { ftp: NonNullable<Forecast["ftp"]>; timeOff: TimeOffWindow[]; i: number }) {
  const w = (v: number) => `${Math.round(v)} W`;
  return (
    <Card i={i}>
      <SectionHead title="FTP" right={<ProjectionLegend colorVar="--series-power" projected={ftp.projection.length > 0} />} />
      <div className="eyebrow">Now · {FTP_FROM[ftp.source]}</div>
      <div className="display num big-stat forecast-ftp">{w(ftp.now)}</div>
      {ftp.summary && <p className="forecast-summary">{ftp.summary}</p>}
      {ftp.history.length > 0 && (
        <ProjectionChart history={ftp.history} projection={ftp.projection} colorVar="--series-power" step format={w} timeOff={timeOff}
          tick={(v) => String(Math.round(v))} label={`FTP so far${ftp.projection.length ? " and where it's heading" : ""}`} />
      )}
    </Card>
  );
}
