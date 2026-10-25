import { Link } from "react-router-dom";
import { focusLine, type FocusItem } from "../lib/focus";
import { Card, SectionHead } from "./ui";

export default function FocusCard({ items, i }: { items: FocusItem[]; i?: number }) {
  return (
    <Card i={i}>
      <SectionHead title="Focus this week" right={<Link to="/trends/gym" style={{ fontSize: 13, textDecoration: "none" }}>Why these</Link>} />
      {items.length === 0 ? (
        <p className="secondary" style={{ margin: 0 }}>Keep logging for a couple of weeks and suggestions will show up here.</p>
      ) : (
        <ol className="focus-list">
          {items.map((item, n) => {
            const line = focusLine(item);
            return (
              <li key={n}>
                <span className="focus-num">{String(n + 1).padStart(2, "0")}</span>
                <div>
                  <div className="list-title">{line.title}</div>
                  <div className="num" style={{ color: "var(--ink-2)", marginTop: 3 }}>{line.detail}</div>
                  <div className="muted" style={{ fontSize: 13, marginTop: 3 }}>{item.reason}</div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
