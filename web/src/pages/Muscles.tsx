import { useEffect, useRef, useState, type MouseEvent } from "react";
import { useSearchParams } from "react-router-dom";
import BodyFigure from "../components/BodyFigure";
import { Card, PageHeader } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { focusLine } from "../lib/focus";
import { CARDIO_COLOR, CARDIO_PHRASE, shadeLevel, shiftWeek } from "../lib/musclemap";
import type { MapMuscle, MuscleMap } from "../lib/types";

const day = (iso: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", day: "numeric", month: "short" }) =>
  new Date(`${iso}T12:00`).toLocaleDateString("en-GB", opts);
const num = (x: number) => (Number.isInteger(x) ? `${x}` : x.toFixed(1));
const SHADES = ["No gym sets", "A little", "On target", "Lots"];

function Details({ m, map }: { m: MapMuscle; map: MuscleMap }) {
  const max = Math.max(m.target_high, m.sets, 1);
  const peak = Math.max(...m.history.map((h) => h.sets), 1);
  const cardio = map.cardio.filter((c) => m.cardio.some((x) => x.sport === c.sport));
  return (
    <div className="mm-details">
      <h3>{m.name}</h3>
      <div className="row" style={{ gap: 8, alignItems: "baseline" }}>
        <span className="mm-big num">{num(m.sets)}</span>
        <span className="secondary">sets · aim {m.target_low}–{m.target_high}</span>
      </div>
      <div className="mm-bar" aria-hidden="true">
        <span className="band" style={{ left: `${(m.target_low / max) * 100}%`, width: `${((m.target_high - m.target_low) / max) * 100}%` }} />
        <span className="fill" style={{ width: `${(m.sets / max) * 100}%` }} />
      </div>
      {m.days.map((d) => (
        <div key={d.date} className="mm-line">
          <strong>{day(d.date)}</strong>
          <span className="muted"> · {d.exercises.map((e) => `${e.name} ${num(e.sets)}`).join(" · ")}</span>
        </div>
      ))}
      {cardio.map((c) => (
        <div key={c.sport} className="mm-line">
          <span className="dot" style={{ background: CARDIO_COLOR[c.sport], borderRadius: "50%", marginRight: 6 }} />
          {c.minutes}′ {CARDIO_PHRASE[c.sport]} <span className="muted">· {c.days.map((d) => day(d, { weekday: "short" })).join(", ")}</span>
        </div>
      ))}
      {m.sets === 0 && (
        <div className="mm-line secondary">
          {m.last_trained ? `No gym sets this week · last on ${day(m.last_trained)}` : "Not in your logs yet"}
        </div>
      )}
      {m.sets === 0 && m.suggestion && (() => {
        const line = focusLine({ type: "gym", ...m.suggestion });
        return <div className="mm-line">Try <strong>{line.title}</strong> <span className="muted">· {line.detail}</span></div>;
      })()}
      <div className="eyebrow" style={{ marginTop: 12 }}>Last 6 weeks</div>
      <div className="mm-spark" aria-label={m.history.map((h) => `${day(h.week_start, { day: "numeric", month: "short" })}: ${num(h.sets)}`).join(", ")}>
        {m.history.map((h, i) => (
          <span key={h.week_start} className={i === m.history.length - 1 ? "cur" : ""}
            style={{ height: `${Math.max(4, (h.sets / peak) * 100)}%` }} />
        ))}
      </div>
      {m.lift && (
        <div className="mm-lift">
          <span>{m.lift.exercise}</span>
          <span className="num">
            {m.lift.status === "trend" ? `${num(m.lift.first_e1rm)} → ${num(m.lift.latest_e1rm)} kg`
              : `${num(m.lift.latest_e1rm)} kg · ${m.lift.status === "new" ? "new" : "not lately"}`}
          </span>
        </div>
      )}
    </div>
  );
}

export default function Muscles() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("week");
  const week = raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null;  // anything else means this week
  const [map, setMap] = useState<MuscleMap | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [tipAt, setTipAt] = useState<{ x: number; y: number } | null>(null);
  const [asList, setAsList] = useState(false);
  const tipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setError(null);
    apiFetch<MuscleMap>(`/api/muscle-map${week ? `?week=${encodeURIComponent(week)}` : ""}`)
      .then(setMap)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 422) setParams({}, { replace: true });  // bad ?week= → this week
        else setError(e.message);
      });
  }, [week, setParams]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPinned(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!map) return <p className="muted">Loading…</p>;

  const byKey = new Map(map.muscles.map((m) => [m.key, m]));
  // Pinned details stay in the side column; keyboard focus shows there too (the floating panel follows the mouse).
  const sideKey = pinned ?? (tipAt ? null : hover);
  const untrained = map.muscles.filter((m) => m.sets === 0);
  const canBack = !!map.first_week && map.week_start > map.first_week;
  const go = (by: number) => {
    const next = shiftWeek(map.week_start, by);
    setPinned(null);
    setParams(by > 0 && map.is_current ? {} : { week: next });
  };
  const sportsThisWeek = map.cardio.map((c) => c.sport);
  const togglePin = (key: string) => setPinned((p) => (p === key ? null : key));

  const onMove = (e: MouseEvent) => {
    const box = tipRef.current;
    const w = box?.offsetWidth ?? 280, h = box?.offsetHeight ?? 200;
    setTipAt({ x: Math.min(e.clientX + 18, window.innerWidth - w - 12), y: Math.min(e.clientY + 18, window.innerHeight - h - 12) });
  };

  return (
    <>
      <PageHeader eyebrow="What you trained" title="Muscles"
        sub="Every muscle starts grey on Monday and fills in as you log gym sets. Stripes are time on the bike, running or swimming." />

      <Card i={1}>
        <div className="row spread" style={{ marginBottom: 12 }}>
          <div className="row" style={{ gap: 10 }}>
            <button className="btn" onClick={() => go(-1)} disabled={!canBack} aria-label="Previous week">‹</button>
            <h2 style={{ margin: 0 }}>{map.is_current ? "This week" : `Week of ${day(map.week_start, { day: "numeric", month: "short" })}`}</h2>
            <button className="btn" onClick={() => go(1)} disabled={map.is_current} aria-label="Next week">›</button>
          </div>
          <div className="legend">
            {SHADES.map((label, i) => <span key={label}><i className="swatch" style={{ background: `var(--muscle-${i})` }} />{label}</span>)}
            {sportsThisWeek.map((s) => (
              <span key={s}><i className="swatch" style={{ background: `repeating-linear-gradient(45deg, ${CARDIO_COLOR[s]} 0 3px, transparent 3px 6px)` }} />
                {s === "bike" ? "Bike" : s === "run" ? "Run" : "Swim"}</span>
            ))}
          </div>
        </div>

        {!map.first_week && <div className="note" style={{ marginBottom: 12 }}>Log a gym session in Hevy and import it to see your week fill in.</div>}

        <div className="mm-grid">
          <div className="mm-figures" onMouseMove={onMove} onMouseLeave={() => setTipAt(null)}>
            {(["front", "back"] as const).map((side) => (
              <figure key={side} className="mm-figure">
                <BodyFigure side={side} muscles={map.muscles} focused={hover} pinned={pinned} onHover={setHover} onPin={togglePin} />
                <figcaption>{side === "front" ? "Front" : "Back"}</figcaption>
              </figure>
            ))}
          </div>

          <aside className="mm-side">
            <div className="mm-big num">{map.trained_count} / {map.muscles.length}</div>
            <div className="secondary" style={{ marginBottom: 16 }}>muscles trained in the gym</div>
            {sideKey && byKey.get(sideKey) ? (
              <>
                <Details m={byKey.get(sideKey)!} map={map} />
                {pinned && <button className="link-btn" style={{ marginTop: 10 }} onClick={() => setPinned(null)}>Unpin (Esc)</button>}
              </>
            ) : untrained.length > 0 ? (
              <>
                <h2 style={{ fontSize: 16, marginBottom: 8 }}>No gym work yet</h2>
                <div className="chips">
                  {untrained.map((m) => (
                    <button key={m.key} className="chip" onMouseEnter={() => setHover(m.key)} onMouseLeave={() => setHover(null)}
                      onClick={() => togglePin(m.key)}>
                      {m.cardio.map((c) => <span key={c.sport} className="dot" style={{ background: CARDIO_COLOR[c.sport], borderRadius: "50%" }} />)}
                      {m.name}
                    </button>
                  ))}
                </div>
                <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>Hover a muscle for details, click to keep them here.</p>
              </>
            ) : <p className="ok" style={{ margin: 0 }}>Every muscle got gym work this week.</p>}
          </aside>
        </div>

        <div className="row spread" style={{ marginTop: 14 }}>
          <span />
          <button className="link-btn" onClick={() => setAsList((v) => !v)}>{asList ? "Hide list" : "Show as list"}</button>
        </div>
        {asList && (
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="table">
              <thead><tr><th>Muscle</th><th className="num">Sets</th><th>Aim</th><th>Cardio</th><th>Last trained</th></tr></thead>
              <tbody>
                {map.muscles.map((m) => (
                  <tr key={m.key}>
                    <td>{m.name}</td>
                    <td className="num">{num(m.sets)}</td>
                    <td>{m.target_low}–{m.target_high} · {SHADES[shadeLevel(m.sets, m.target_low, m.target_high)].toLowerCase()}</td>
                    <td>{m.cardio.map((c) => `${c.minutes}′ ${CARDIO_PHRASE[c.sport]}`).join(", ") || "–"}</td>
                    <td>{m.sets > 0 ? "this week" : m.last_trained ? day(m.last_trained) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {hover && !pinned && tipAt && byKey.get(hover) && (
        <div ref={tipRef} className="mm-tip" style={{ left: tipAt.x, top: tipAt.y }} role="tooltip">
          <Details m={byKey.get(hover)!} map={map} />
        </div>
      )}
    </>
  );
}
