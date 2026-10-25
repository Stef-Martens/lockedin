import { type DragEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, uploadFile } from "../lib/api";
import type { FitResult, HevyResult, Status } from "../lib/types";

interface FileRow {
  name: string;
  state: "waiting" | "uploading" | "done";
  result?: FitResult;
  error?: string;
}

function ago(iso: string | null): string {
  if (!iso) return "never";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} days ago`;
}

function FitUpload({ onDone }: { onDone: () => void }) {
  const [rows, setRows] = useState<FileRow[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function handle(files: FileList | null) {
    const list = Array.from(files ?? []).filter((f) => f.name.toLowerCase().endsWith(".fit"));
    if (!list.length) return;
    setRows(list.map((f) => ({ name: f.name, state: "waiting" })));
    for (let i = 0; i < list.length; i++) {
      setRows((r) => r.map((row, j) => (j === i ? { ...row, state: "uploading" } : row)));
      try {
        const result = await uploadFile<FitResult>("/api/fit/upload", list[i]);
        setRows((r) => r.map((row, j) => (j === i ? { ...row, state: "done", result } : row)));
      } catch (e) {
        setRows((r) => r.map((row, j) => (j === i ? { ...row, state: "done", error: (e as Error).message } : row)));
      }
    }
    onDone();
  }

  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    handle(e.dataTransfer.files);
  };

  return (
    <section className="card">
      <h2>Ride and workout files (.fit)</h2>
      <p className="secondary" style={{ marginTop: 0 }}>
        Zwift rides and HealthFit workouts sync from your Mac automatically. Use this for anything the sync missed.
      </p>
      <div className={`drop${over ? " over" : ""}`} onClick={() => input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}
        role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && input.current?.click()}>
        Drop .fit files here or tap to choose
        <input ref={input} type="file" accept=".fit,.FIT" multiple onChange={(e) => handle(e.target.files)} />
      </div>
      {rows.length > 0 && (
        <ul className="list" style={{ marginTop: 12 }}>
          {rows.map((r, i) => (
            <li key={i} className="row spread" style={{ padding: "6px 0" }}>
              <span>{r.name}</span>
              <span className="num">
                {r.state === "waiting" && <span className="muted">waiting</span>}
                {r.state === "uploading" && <span className="muted">uploading…</span>}
                {r.error && <span className="error">{r.error}</span>}
                {r.result?.status === "imported" && (
                  <Link className="ok" to={`/activities/${r.result.activity_id}`}>imported</Link>
                )}
                {r.result?.status === "duplicate" && <span className="muted">already imported</span>}
                {r.result?.status === "error" && <span className="error">couldn't read this file</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function HevyUpload({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<HevyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handle(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await uploadFile<HevyResult>("/api/hevy/upload", file));
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Hevy workouts (.csv)</h2>
      <p className="secondary" style={{ marginTop: 0 }}>
        In Hevy: Profile → Settings → Export &amp; Import Data → Export Workouts. Upload the whole file every time;
        nothing gets duplicated.
      </p>
      <label className="btn primary">
        {busy ? "Importing…" : "Choose CSV"}
        <input type="file" accept=".csv,text/csv" hidden disabled={busy} onChange={(e) => handle(e.target.files?.[0])} />
      </label>
      {error && <p className="error">{error}</p>}
      {result && (
        <p className="num">
          <span className="ok">{result.new} new</span> · {result.updated} updated · {result.unchanged} unchanged
          {result.skipped.length > 0 && (
            <span className="muted"> · {result.skipped.length} rows skipped (e.g. row {result.skipped[0][0]}: {result.skipped[0][1]})</span>
          )}
        </p>
      )}
    </section>
  );
}

export default function Import() {
  const [status, setStatus] = useState<Status | null>(null);
  const load = () => apiFetch<Status>("/api/status").then(setStatus).catch(() => undefined);
  useEffect(() => { load(); }, []);

  return (
    <>
      <h1>Import</h1>
      <p className="secondary">Get your training data in.</p>
      {status && (
        <section className="card">
          <h2>Last synced</h2>
          <div className="tiles" style={{ marginBottom: 0 }}>
            {(["zwift", "healthfit", "hevy"] as const).map((s) => (
              <div className="tile" key={s}>
                <div className="label">{{ zwift: "Zwift", healthfit: "Apple Watch", hevy: "Hevy" }[s]}</div>
                <div className="value" style={{ fontSize: "1rem" }}>{ago(status[s].last_import_at)}</div>
                <div className="muted num" style={{ fontSize: "0.85rem" }}>{status[s].count} imported</div>
              </div>
            ))}
          </div>
        </section>
      )}
      <FitUpload onDone={load} />
      <HevyUpload onDone={load} />
    </>
  );
}
