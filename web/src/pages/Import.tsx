import { type DragEvent, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Card, PageHeader, SectionHead } from "../components/ui";
import { apiFetch, uploadFile } from "../lib/api";
import { ago, recent } from "../lib/format";
import { stagger } from "../lib/motion";
import type { FitResult, HevyResult, Status } from "../lib/types";

interface FileRow {
  name: string;
  state: "waiting" | "uploading" | "done";
  result?: FitResult;
  error?: string;
}

function StatusTile({ label, when, sub, dot, i }: { label: string; when: string; sub: string; dot: "live" | "idle" | "gym"; i: number }) {
  return (
    <div className="card rise" style={stagger(i)}>
      <div className="row spread"><span className="eyebrow">{label}</span>
        <span className={`sync-dot${dot === "live" ? " live pulse" : ""}`} style={dot === "gym" ? { background: "var(--sport-gym)" } : undefined} aria-hidden="true" />
      </div>
      <div className="display" style={{ fontSize: 34, marginTop: 10 }}>{when}</div>
      <div className="secondary" style={{ fontSize: 14 }}>{sub}</div>
    </div>
  );
}

function FitUpload({ onDone }: { onDone: () => void }) {
  const [rows, setRows] = useState<FileRow[]>([]);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  async function handle(files: File[]) {
    const list = files.filter((f) => f.name.toLowerCase().endsWith(".fit"));
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

  const label = (r: FileRow): [string, string] => {
    if (r.error) return [r.error, "var(--danger)"];
    if (r.state === "waiting") return ["waiting", "var(--ink-muted)"];
    if (r.state === "uploading") return ["uploading…", "var(--ink-muted)"];
    switch (r.result?.status) {
      case "imported": return ["imported", "var(--accent)"];
      case "duplicate": return ["already imported", "var(--ink-3)"];
      case "empty": return ["empty, skipped", "var(--ink-3)"];
      default: return ["couldn't read this file", "var(--danger)"];
    }
  };

  return (
    <Card i={4}>
      <SectionHead title="Ride and workout files" />
      <p className="secondary" style={{ marginTop: -6, fontSize: 14 }}>.fit files from Zwift or HealthFit. These normally sync from your Mac by themselves.</p>
      <div className={`drop${over ? " over" : ""}`} onClick={() => input.current?.click()} role="button" tabIndex={0}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.current?.click(); } }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e: DragEvent) => { e.preventDefault(); setOver(false); handle(Array.from(e.dataTransfer.files)); }}>
        Drop .fit files here or <span style={{ color: "var(--accent)", fontWeight: 600 }}>choose files</span>
      </div>
      {/* Outside the drop zone, so its click doesn't bubble back into it. Cleared after each pick, so picking the
          same file again (e.g. after a failed upload) still uploads it. */}
      <input ref={input} type="file" accept=".fit,.FIT" multiple hidden data-testid="fit-input"
        onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; handle(files); }} />
      {rows.map((r, i) => {
        const [text, color] = label(r);
        const pct = r.state === "waiting" ? 0 : r.state === "uploading" ? 60 : 100;
        return (
          <div key={i} className="pop" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 12, alignItems: "center", padding: "10px 0", borderTop: "1px solid var(--hairline)", marginTop: i ? 0 : 10 }}>
            <div style={{ minWidth: 0 }}>
              {r.result?.status === "imported" ? (
                <Link to={`/activities/${r.result.activity_id}`} style={{ fontSize: 14 }}>{r.name}</Link>
              ) : <div style={{ fontSize: 14, overflow: "hidden", textOverflow: "ellipsis" }}>{r.name}</div>}
              <div style={{ height: 4, background: "var(--hairline)", borderRadius: 2, marginTop: 6, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${pct}%`, background: color, transition: "width .35s ease" }} />
              </div>
            </div>
            <span style={{ fontSize: 13, color, textAlign: "right" }}>{text}</span>
          </div>
        );
      })}
    </Card>
  );
}

function HevyUpload({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
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

  const chip = (text: string, on = false) => (
    <span style={{ border: `1px solid ${on ? "var(--accent-line)" : "var(--hairline)"}`, background: on ? "var(--accent-wash)" : "var(--sunken)",
      color: on ? "var(--accent)" : "var(--ink)", borderRadius: 999, padding: "6px 12px", fontSize: 14 }}>{text}</span>
  );
  return (
    <Card i={5}>
      <SectionHead title="Hevy workouts" />
      <p className="secondary" style={{ marginTop: -6, fontSize: 14, lineHeight: 1.5 }}>
        In Hevy: Profile → Settings → Export &amp; Import Data → Export Workouts. Upload the whole file every time; nothing gets duplicated.
      </p>
      <button type="button" className="btn primary" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Importing…" : "Choose CSV"}
      </button>
      <input ref={input} type="file" accept=".csv,text/csv" hidden data-testid="hevy-input"
        onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; handle(file); }} />
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="row pop" style={{ marginTop: 16, gap: 8 }}>
          {chip(`${result.new} new`, result.new > 0)}
          {chip(`${result.updated} updated`)}
          {chip(`${result.unchanged} unchanged`)}
          {result.skipped.length > 0 && <span className="muted" style={{ fontSize: 13 }}>{result.skipped.length} rows skipped (e.g. row {result.skipped[0][0]}: {result.skipped[0][1]})</span>}
        </div>
      )}
    </Card>
  );
}

export default function Import() {
  const [status, setStatus] = useState<Status | null>(null);
  const load = () => apiFetch<Status>("/api/status").then(setStatus).catch(() => undefined);
  useEffect(() => { load(); }, []);

  return (
    <>
      <PageHeader title="Import" sub="Most of this happens by itself. Use the uploads for anything the sync missed." />
      {status && (
        <div className="grid-auto" style={{ ["--min" as string]: "240px" }}>
          <StatusTile i={1} label="Zwift" when={ago(status.zwift.last_import_at)} sub={`${status.zwift.count} rides · syncing from your Mac`}
            dot={recent(status.zwift.last_import_at) ? "live" : "idle"} />
          <StatusTile i={2} label="Apple Watch" when={status.healthfit.count ? ago(status.healthfit.last_import_at) : "Not set up"}
            sub={status.healthfit.count ? `${status.healthfit.count} workouts via HealthFit` : "Add your HealthFit folder to the sync"}
            dot={recent(status.healthfit.last_import_at) ? "live" : "idle"} />
          <StatusTile i={3} label="Hevy" when={ago(status.hevy.last_import_at)} sub={`${status.hevy.count} workouts · manual upload`} dot="gym" />
        </div>
      )}
      <div className="grid-auto" style={{ ["--min" as string]: "420px" }}>
        <FitUpload onDone={load} />
        <HevyUpload onDone={load} />
      </div>
    </>
  );
}
