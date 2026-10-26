import { useId, type KeyboardEvent } from "react";
import { CARDIO_COLOR, muscleLabel, shadeLevel, stripeOpacity } from "../lib/musclemap";
import type { CardioSport, MapMuscle } from "../lib/types";

// Drawn on a 200 × 420 canvas around the centre line x = 100. Paired muscles are the body's
// left half as seen on screen; the right half is the same path mirrored.
const SILHOUETTE =
  "M100,44 C95,44 92,46 92,52 L92,58 C86,62 74,63 64,65 C52,67 44,74 42,86 C40,98 42,110 44,122 " +
  "C45,134 46,142 46,150 C42,164 38,182 37,200 C36,210 36,216 37,222 C35,232 36,242 40,248 C44,252 48,250 49,244 " +
  "C50,236 49,228 47,222 C50,206 54,184 57,166 C59,156 60,150 60,146 C62,134 63,124 64,114 C66,132 68,152 70,172 " +
  "C70,184 68,194 68,202 C66,220 66,242 68,262 C70,280 72,294 74,304 C72,324 74,350 78,372 C80,384 80,392 80,398 " +
  "C76,404 76,410 84,412 L96,412 C98,408 97,402 95,398 C96,380 97,350 96,330 C96,316 96,306 96,300 " +
  "C98,276 99,250 99,230 L100,226 Z";

const SIDE_DELT = "M60,66 C51,68 45,74 43,84 C42,92 43,100 45,106 L48,104 C46,94 47,84 50,78 C53,72 57,68 62,67 Z";
const FOREARM = "M46,154 C41,168 39,186 39,204 L46,206 C49,190 53,172 57,158 C54,152 49,151 46,154 Z";

const FRONT_PAIRED: Record<string, string> = {
  upper_chest: "M70,72 C80,70 92,70 99,72 L99,90 C88,90 76,93 66,99 C64,90 65,79 70,72 Z",
  mid_lower_chest: "M66,101 C77,95 88,92 99,92 L99,112 C92,119 81,121 73,118 C67,115 64,108 66,101 Z",
  front_delt: "M66,68 C58,68 51,72 48,80 C46,88 47,98 50,106 C53,98 57,90 64,84 C68,80 70,72 66,68 Z",
  side_delt: SIDE_DELT,
  biceps: "M50,110 C46,120 46,134 48,146 C51,151 56,151 58,146 C60,134 60,120 57,110 C55,106 52,106 50,110 Z",
  forearms: FOREARM,
  obliques: "M70,122 C75,121 81,123 85,127 L86,184 C80,188 74,184 72,176 C70,160 69,140 70,122 Z",
  abductors: "M69,196 C66,206 65,220 67,232 L73,228 C72,216 72,206 74,198 Z",
  quads: "M75,204 C83,206 92,212 96,222 C97,248 95,274 92,294 C86,300 79,299 75,291 C71,268 70,234 75,204 Z",
  adductors: "M97,224 L99,226 L99,262 C97,266 95,268 94,264 C95,250 96,238 97,224 Z",
};
const FRONT_CENTER: Record<string, string> = {
  abs: "M88,126 Q88,123 91,123 L98,123 L98,140 L88,140 Z M102,123 L109,123 Q112,123 112,126 L112,140 L102,140 Z " +
    "M88,143 L98,143 L98,159 L88,159 Z M102,143 L112,143 L112,159 L102,159 Z " +
    "M88,162 L98,162 L98,178 L88,178 Z M102,162 L112,162 L112,178 L102,178 Z " +
    "M88,181 L112,181 L111,194 Q100,204 89,194 Z",
};
const BACK_PAIRED: Record<string, string> = {
  rear_delt: "M66,68 C58,68 51,72 48,80 C46,88 47,98 50,106 C53,98 58,90 66,86 C70,80 70,72 66,68 Z",
  side_delt: SIDE_DELT,
  triceps: "M49,110 C45,122 45,136 48,148 C52,152 57,151 59,145 C60,132 59,118 56,110 C54,106 51,106 49,110 Z",
  forearms: FOREARM,
  lats: "M68,96 C74,100 81,104 88,108 C90,128 88,150 84,170 C78,168 74,160 71,148 C67,132 66,112 68,96 Z",
  mid_back: "M80,76 C86,84 93,94 97,108 L98,146 C94,140 92,126 91,112 C88,100 84,88 80,76 Z",
  glutes: "M72,198 C79,192 92,194 99,200 L99,228 C94,236 82,238 74,232 C68,224 68,206 72,198 Z",
  hamstrings: "M74,240 C82,243 92,243 97,241 C97,262 95,282 92,298 C86,304 79,302 75,294 C71,276 71,258 74,240 Z",
  calves: "M78,312 C74,326 75,346 80,360 C84,366 92,366 95,358 C98,344 98,326 95,312 C90,306 82,306 78,312 Z",
};
const BACK_CENTER: Record<string, string> = {
  upper_back_traps: "M100,46 C97,54 90,60 76,66 C84,72 92,82 96,100 L100,110 L104,100 C108,82 116,72 124,66 C110,60 103,54 100,46 Z",
  lower_back: "M90,150 C95,152 105,152 110,150 C112,166 113,182 113,194 C105,198 95,198 87,194 C87,182 88,166 90,150 Z",
};
const MIRROR = "matrix(-1 0 0 1 200 0)";

export default function BodyFigure({ side, muscles, focused, pinned, onHover, onFocusMuscle, onPin }: {
  side: "front" | "back";
  muscles: MapMuscle[];
  focused: string | null;
  pinned: string | null;
  /** Mouse over a muscle (null when it leaves). */
  onHover: (key: string | null) => void;
  /** Keyboard focus on a muscle (null on blur). */
  onFocusMuscle?: (key: string | null) => void;
  onPin: (key: string) => void;
}) {
  const uid = useId().replace(/:/g, "");
  const byKey = new Map(muscles.map((m) => [m.key, m]));
  const paired = side === "front" ? FRONT_PAIRED : BACK_PAIRED;
  const centered = side === "front" ? FRONT_CENTER : BACK_CENTER;
  const keys = [...Object.keys(paired), ...Object.keys(centered)];

  // One stripe pattern per combination of sports present on this view; two sports alternate colours.
  const combos = new Map<string, CardioSport[]>();
  keys.forEach((k) => {
    const sports = (byKey.get(k)?.cardio ?? []).map((c) => c.sport);
    if (sports.length) combos.set(sports.join("-"), sports);
  });
  const patternId = (sports: CardioSport[]) => `${uid}-${side}-${sports.join("-")}`;

  const shape = (key: string, d: string, primary: boolean) => {
    const m = byKey.get(key);
    const level = m ? shadeLevel(m.sets, m.target_low, m.target_high) : 0;
    const cls = `muscle${focused === key ? " hl" : ""}${pinned === key ? " pinned" : ""}`;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPin(key); }
    };
    return (
      <path key={key} data-m={key} style={{ fill: `var(--muscle-${level})` }} className={cls} d={d}
        {...(primary
          ? { tabIndex: 0, role: "button", "aria-label": m ? muscleLabel(m) : key, "aria-pressed": pinned === key }
          : { "aria-hidden": true })}
        onMouseEnter={() => onHover(key)} onMouseLeave={() => onHover(null)}
        onFocus={() => onFocusMuscle?.(key)} onBlur={() => onFocusMuscle?.(null)}
        onClick={() => onPin(key)} onKeyDown={primary ? onKey : undefined} />
    );
  };
  const stripes = (key: string, d: string) => {
    const cardio = byKey.get(key)?.cardio ?? [];
    if (!cardio.length) return null;
    const opacity = stripeOpacity(Math.max(...cardio.map((c) => c.minutes)));
    return <path key={`${key}-stripes`} className="muscle-stripes" d={d} aria-hidden="true"
      fill={`url(#${patternId(cardio.map((c) => c.sport))})`} opacity={opacity} />;
  };
  const half = (primary: boolean) => Object.entries(paired).map(([k, d]) => [shape(k, d, primary), stripes(k, d)]);

  return (
    <svg className="body-figure" viewBox="28 0 144 420" role="group" aria-label={`${side === "front" ? "Front" : "Back"} of the body`}>
      <defs>
        {[...combos.values()].map((sports) => (
          <pattern key={sports.join("-")} id={patternId(sports)} width={6 * sports.length} height="6"
            patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            {sports.map((s, i) => <rect key={s} x={i * 6} width="2.6" height="6" style={{ fill: CARDIO_COLOR[s] }} />)}
          </pattern>
        ))}
      </defs>
      <ellipse className="body-base" cx="100" cy="26" rx="14" ry="18" />
      <path className="body-base" d={SILHOUETTE} />
      <path className="body-base" d={SILHOUETTE} transform={MIRROR} />
      {/* Fill again without the outline so the two halves don't show a seam down the middle. */}
      <path className="body-base fill-only" d={SILHOUETTE} />
      <path className="body-base fill-only" d={SILHOUETTE} transform={MIRROR} />
      {half(true)}
      <g transform={MIRROR}>{half(false)}</g>
      {Object.entries(centered).map(([k, d]) => [shape(k, d, true), stripes(k, d)])}
    </svg>
  );
}
