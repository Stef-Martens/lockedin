import { Link } from "react-router-dom";
import { type Win, winParts } from "../lib/focus";
import { Card, SectionHead } from "./ui";

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

export default function WinsStrip({ wins, i }: { wins: Win[]; i?: number }) {
  if (!wins.length) return null;
  return (
    <Card i={i}>
      <SectionHead title="New bests" />
      {wins.map((w, n) => {
        const { value, note } = winParts(w.detail);
        const body = (
          <>
            <div>
              <div style={{ fontSize: 15 }}>{w.title.replace(/^New best: /, "")}</div>
              <div className="muted" style={{ fontSize: 13 }}>{shortDate(w.date)} · {note}</div>
            </div>
            {value && <div className="win-value num">{value}</div>}
          </>
        );
        return w.activity_id ? (
          <Link key={n} to={`/activities/${w.activity_id}`} className="win-row lift">{body}</Link>
        ) : (
          <div key={n} className="win-row">{body}</div>
        );
      })}
    </Card>
  );
}
