import { useState } from "react";
import { Card, SectionHead } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { type Checkin, historyRows } from "../../lib/body";
import { dayMonthYear } from "../../lib/format";
import type { MeasurementType } from "../../lib/types";

export default function History({ types, checkins, onDeleted }: { types: MeasurementType[]; checkins: Checkin[]; onDeleted: () => void }) {
  const [error, setError] = useState<string | null>(null);
  async function remove(d: string) {
    if (!window.confirm(`Delete the check-in of ${dayMonthYear(d)}?`)) return;
    setError(null);
    try {
      await apiFetch(`/api/checkins/${d}`, { method: "DELETE" });
      onDeleted();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const rows = historyRows(checkins, types.map((t) => t.id));
  if (!rows.length) return null;
  return (
    <Card i={2} className="pop">
      <SectionHead title="History" right={<span className="muted" style={{ fontSize: 13 }}>Change vs the previous check-in</span>} />
      <div className="table-wrap">
        <table className="table num" style={{ minWidth: 200 + types.length * 92 }}>
          <thead>
            <tr><th>Date</th>{types.map((t) => <th key={t.id} className="num">{t.name}</th>)}<th><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.measured_on}>
                <td className="secondary">{dayMonthYear(r.measured_on)}</td>
                {r.cells.map((c, n) => (
                  <td key={n} className="num">
                    <span className="display" style={{ fontSize: 20, fontWeight: 700 }}>{c.value ?? "–"}</span>
                    {c.delta != null && <span className="history-delta">{c.delta === 0 ? "±0" : `${c.delta > 0 ? "+" : "−"}${Math.abs(c.delta).toFixed(1)}`}</span>}
                  </td>
                ))}
                <td className="num"><button className="btn ghost" onClick={() => remove(r.measured_on)} aria-label={`Delete check-in of ${dayMonthYear(r.measured_on)}`}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}
    </Card>
  );
}
