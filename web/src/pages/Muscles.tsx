import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
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
const GAP = 12;

type Point = { x: number; y: number };
/** Below-right of the cursor, kept inside the viewport (a panel taller than the screen starts at the top). */
export function placeTip(cursor: Point, size: { w: number; h: number }, viewport: { w: number; h: number }): Point {
  return {
    x: Math.max(GAP, Math.min(cursor.x + 18, viewport.w - size.w - GAP)),
    y: Math.max(GAP, Math.min(cursor.y + 18, viewport.h - size.h - GAP)),
  };
}

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
      {m.left_out && <div className="mm-line secondary">Left out in your preferences.</div>}
      {cardio.map((c) => (
        <div key={c.sport} className="mm-line">
          <span className="dot" style={{ background: CARDIO_COLOR[c.sport], borderRadius: "50%", marginRight: 6 }} />
          {c.minutes}′ {CARDIO_PHRASE[c.sport]} <span className="muted">· {c.days.map((d) => day(d, { weekday: "short" })).join(", ")}</span>
        </div>
      ))}
      {m.sets === 0 && !m.left_out && (
        <div className="mm-line secondary">
          {m.last_trained ? `No gym sets this week · last on ${day(m.last_trained)}` : "Not in your logs yet"}
        </div>
      )}
      {m.sets === 0 && !m.left_out && m.suggestion && (() => {
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
  const [hover, setHover] = useState<string | null>(null);         // mouse over a muscle on the body
  const [chipHover, setChipHover] = useState<string | null>(null);  // mouse or focus on a "no gym work" chip
  const [focusKey, setFocusKey] = useState<string | null>(null);    // keyboard focus on the body
  const [pinned, setPinned] = useState<string | null>(null);
  const [cursor, setCursor] = useState<Point | null>(null);
  const [tipPos, setTipPos] = useState<Point | null>(null);
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

  const tipKey = hover && cursor && hover !== pinned ? hover : null;
  // Place the panel after it has rendered, so it's measured with the muscle it's actually showing.
  useLayoutEffect(() => {
    if (!tipKey || !cursor || !tipRef.current) { setTipPos(null); return; }
    const box = tipRef.current;
    setTipPos(placeTip(cursor, { w: box.offsetWidth, h: box.offsetHeight }, { w: window.innerWidth, h: window.innerHeight }));
  }, [tipKey, cursor]);

  if (error) return <p className="error">{error}</p>;
  if (!map) return <p className="muted">Loading…</p>;

  const byKey = new Map(map.muscles.map((m) => [m.key, m]));
  // The side column shows the keyboard-focused muscle, else the pinned one; the floating panel follows the mouse.
  const sideKey = focusKey ?? pinned;
  const untrained = map.muscles.filter((m) => m.sets === 0 && !m.left_out);
  const anyLeftOut = map.muscles.some((m) => m.left_out);
  const canBack = !!map.first_week && map.week_start > map.first_week;
  const go = (by: number) => {
    const next = shiftWeek(map.week_start, by);
    setPinned(null);
    setParams(by > 0 && map.is_current ? {} : { week: next });
  };
  const sportsThisWeek = map.cardio.map((c) => c.sport);
  const togglePin = (key: string) => setPinned((p) => (p === key ? null : key));

  const onMove = (e: MouseEvent) => setCursor({ x: e.clientX, y: e.clientY });

  return (
    <>
      <PageHeader eyebrow="What you trained" title="Muscles"
        sub="Every muscle starts grey on Monday and fills in as you log gym sets. Stripes are time on the bike, running or swimming."
        right={<Link to="/plan" className="btn primary" style={{ textDecoration: "none" }}>Plan a workout</Link>} />

      <Card i={1}>
        <div className="row spread" style={{ marginBottom: 12 }}>
          <div className="row" style={{ gap: 10 }}>
            <button className="btn" onClick={() => go(-1)} disabled={!canBack} aria-label="Previous week">‹</button>
            <h2 style={{ margin: 0 }}>{map.is_current ? "This week" : `Week of ${day(map.week_start, { day: "numeric", month: "short" })}`}</h2>
            <button className="btn" onClick={() => go(1)} disabled={map.is_current} aria-label="Next week">›</button>
          </div>
          <div className="legend">
            {SHADES.map((label, i) => <span key={label}><i className="swatch" style={{ background: `var(--muscle-${i})` }} />{label}</span>)}
            {anyLeftOut && <span><i className="swatch" style={{ background: "var(--muscle-out)", outline: "1px dashed var(--ink-muted)" }} />Left out</span>}
            {sportsThisWeek.map((s) => (
              <span key={s}><i className="swatch" style={{ background: `repeating-linear-gradient(45deg, ${CARDIO_COLOR[s]} 0 3px, transparent 3px 6px)` }} />
                {s === "bike" ? "Bike" : s === "run" ? "Run" : "Swim"}</span>
            ))}
          </div>
        </div>

        {!map.first_week && <div className="note" style={{ marginBottom: 12 }}>Log a gym session in Hevy and import it to see your week fill in.</div>}

        <div className="mm-grid">
          <div className="mm-figures" onMouseMove={onMove} onMouseLeave={() => setCursor(null)}>
            {(["front", "back"] as const).map((side) => (
              <figure key={side} className="mm-figure">
                <BodyFigure side={side} muscles={map.muscles} focused={hover ?? chipHover ?? focusKey} pinned={pinned}
                  onHover={setHover} onFocusMuscle={setFocusKey} onPin={togglePin} />
                <figcaption>{side === "front" ? "Front" : "Back"}</figcaption>
              </figure>
            ))}
          </div>

          <aside className="mm-side">
            <div className="mm-big num">{map.trained_count} / {map.total ?? map.muscles.length}</div>
            <div className="secondary" style={{ marginBottom: 16 }}>muscles trained in the gym</div>
            {untrained.length > 0 ? (
              <>
                <h2 style={{ fontSize: 16, marginBottom: 8 }}>No gym work yet</h2>
                <div className="chips">
                  {untrained.map((m) => (
                    <button key={m.key} className={`chip${pinned === m.key ? " on" : ""}`} aria-pressed={pinned === m.key}
                      onMouseEnter={() => setChipHover(m.key)} onMouseLeave={() => setChipHover(null)}
                      onFocus={() => setChipHover(m.key)} onBlur={() => setChipHover(null)}
                      onClick={() => togglePin(m.key)}>
                      {m.cardio.map((c) => <span key={c.sport} className="dot" style={{ background: CARDIO_COLOR[c.sport], borderRadius: "50%" }} />)}
                      {m.name}
                    </button>
                  ))}
                </div>
              </>
            ) : <p className="ok" style={{ margin: 0 }}>Every muscle got gym work this week.</p>}
            {sideKey && byKey.get(sideKey) ? (
              <div className="mm-pinned">
                <Details m={byKey.get(sideKey)!} map={map} />
                {pinned === sideKey && <button className="link-btn" style={{ marginTop: 10 }} onClick={() => setPinned(null)}>Unpin (Esc)</button>}
              </div>
            ) : <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>Hover a muscle for details, click to keep them here.</p>}
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

      {tipKey && byKey.get(tipKey) && (
        <div ref={tipRef} className="mm-tip" role="tooltip"
          style={tipPos ? { left: tipPos.x, top: tipPos.y } : { left: cursor!.x + 18, top: cursor!.y + 18, visibility: "hidden" }}>
          <Details m={byKey.get(tipKey)!} map={map} />
        </div>
      )}
    </>
  );
}
