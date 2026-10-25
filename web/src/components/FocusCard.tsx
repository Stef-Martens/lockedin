import { focusLine, type FocusItem } from "../lib/focus";
import SportDot from "./SportDot";

export default function FocusCard({ items }: { items: FocusItem[] }) {
  return (
    <section className="card focus-card">
      <h2>Focus this week</h2>
      {items.length === 0 ? (
        <p className="secondary" style={{ margin: 0 }}>Keep logging for a couple of weeks and suggestions will show up here.</p>
      ) : (
        <ol className="focus-list">
          {items.map((item, i) => {
            const line = focusLine(item);
            return (
              <li key={i}>
                <SportDot sport={item.type === "gym" ? "gym" : item.sport} />
                <div>
                  <div className="list-title">{line.title}</div>
                  <div className="num">{line.detail}</div>
                  <div className="muted" style={{ fontSize: "0.85rem" }}>{item.reason}</div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
