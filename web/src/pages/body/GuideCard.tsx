import { type FormEvent, useState } from "react";
import { Card, SectionHead } from "../../components/ui";
import { apiFetch } from "../../lib/api";

export default function GuideCard({ onAdded }: { onAdded: () => void }) {
  const [name, setName] = useState("");
  const [unit, setUnit] = useState("cm");
  const [error, setError] = useState<string | null>(null);
  async function add(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/api/measurement-types", { method: "POST", body: JSON.stringify({ name, unit, kind: unit === "kg" ? "weight" : "tape" }) });
      setName("");
      onAdded();
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <Card i={5}>
      <SectionHead title="Measure the same way every time" />
      <ul className="guide-list">
        <li>Morning, before eating or training; weight after the toilet.</li>
        <li>Tape snug on the skin, not pulling it in; read it in a mirror.</li>
        <li>Relaxed muscles, unless you always measure flexed. Pick one and stick to it.</li>
        <li>Small swings (±0.5 cm, ±1 kg) are normal day-to-day noise.</li>
      </ul>
      <form onSubmit={add} className="row" style={{ marginTop: 16, alignItems: "flex-end" }}>
        <label className="field" style={{ flex: "1 1 160px" }}>Track something else
          <input value={name} placeholder="e.g. Calves" onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="field" style={{ width: 90 }}>Unit
          <select value={unit} onChange={(e) => setUnit(e.target.value)}><option>cm</option><option>kg</option><option>%</option></select>
        </label>
        <button className="btn">Add</button>
      </form>
      {error && <p className="error" style={{ marginBottom: 0 }}>{error}</p>}
    </Card>
  );
}
