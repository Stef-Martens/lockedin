import { Link } from "react-router-dom";
import type { Win } from "../lib/focus";

export default function WinsStrip({ wins }: { wins: Win[] }) {
  if (!wins.length) return null;
  return (
    <section style={{ marginBottom: 16 }}>
      <h2>Recent wins</h2>
      <div className="wins">
        {wins.map((w, i) => {
          const body = (
            <>
              <div className="list-title">{w.title}</div>
              <div className="secondary num" style={{ fontSize: "0.9rem" }}>{w.detail}</div>
            </>
          );
          return w.activity_id ? (
            <Link key={i} to={`/activities/${w.activity_id}`} className="win">{body}</Link>
          ) : (
            <div key={i} className="win">{body}</div>
          );
        })}
      </div>
    </section>
  );
}
