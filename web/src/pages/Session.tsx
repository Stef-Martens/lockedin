import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Card } from "../components/ui";
import { SPORT_NAME } from "../lib/agenda";
import { apiFetch } from "../lib/api";
import { longDay } from "../lib/format";
import type { SessionDetail } from "../lib/session";
import { useApi } from "../lib/useApi";
import ActualSection from "./session/ActualSection";
import Edit from "./session/Edit";
import PlanSection from "./session/PlanSection";

export default function Session() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: d, error: loadError, reload } = useApi<SessionDetail>(`/api/agenda/${id}/detail`);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const error = loadError?.message ?? deleteError;
  if (error) return <><Link to="/agenda" className="back-link">‹ Agenda</Link><p className="error">{error}</p></>;
  if (!d) return <p className="muted">Loading…</p>;
  const { item, plan, actual } = d;
  const remove = () => apiFetch(`/api/agenda/${item.id}`, { method: "DELETE" })
    .then(() => navigate(`/agenda?week=${item.day}`)).catch((e) => setDeleteError(e.message));

  return (
    <>
      <Link to={`/agenda?week=${item.day}`} className="back-link">‹ Agenda</Link>
      <Card i={0} variant={item.done ? "accent" : undefined} className="session-hero">
        <span className={`big-check${item.done ? " done pop" : ""}`} aria-hidden="true">{item.done ? "✓" : "to do"}</span>
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">{longDay(item.day)} · {SPORT_NAME[item.sport]} · {item.source === "coach" ? "planned with the coach" : "added by you"}</div>
          <h1 className="session-title">{item.title}</h1>
          {item.result && <div className="secondary">{item.result}</div>}
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            {item.goal && <span className="goal-tag">for your goal: {item.goal}</span>}
            {item.zwift_status && !item.done && <span className={`pill zwift ${item.zwift_status}`}>
              {item.zwift_status === "synced" ? `In Zwift ✓ as "${item.zwift?.filename.replace(/\.zwo$/, "")}"` : "Goes to Zwift at the next sync"}</span>}
            {item.optional && <span className="pill optional">Optional</span>}
          </div>
          {item.zwift_status === "pending" && !item.done && <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>Restart Zwift after the sync to see it under Custom Workouts.</div>}
        </div>
        <div className="row" style={{ gap: 8 }}>
          {actual && <Link className="btn" to={`/activities/${actual.activity_id}`}>Full activity →</Link>}
          <button className="btn" onClick={() => setEditing((v) => !v)}>Edit</button>
          {!confirm ? <button className="btn danger" onClick={() => setConfirm(true)}>Delete</button>
            : <button className="btn danger" onClick={remove}>Yes, delete it</button>}
        </div>
      </Card>
      {editing && <Edit item={item} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); reload(); }} />}
      {actual && <ActualSection d={d} />}
      {(!actual || plan.kind === "note") && <PlanSection plan={plan} item={item} />}
      {actual && plan.kind !== "note" && (
        <details className="card session-plan-details">
          <summary>What was planned</summary>
          <PlanSection plan={plan} item={item} />
        </details>
      )}
    </>
  );
}
