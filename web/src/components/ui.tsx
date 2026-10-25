import type { CSSProperties, ReactNode } from "react";
import { stagger } from "../lib/motion";

/** Surface with the staggered entrance; `i` orders it within the page. */
export function Card({ children, i, variant, className = "", style }: {
  children: ReactNode; i?: number; variant?: "outline" | "accent"; className?: string; style?: CSSProperties;
}) {
  return (
    <section className={`card rise ${variant ?? ""} ${className}`} style={{ ...(i != null ? stagger(i) : {}), ...style }}>
      {children}
    </section>
  );
}

export function SectionHead({ title, right }: { title: ReactNode; right?: ReactNode }) {
  return (
    <div className="section-head">
      <h2>{title}</h2>
      {right}
    </div>
  );
}

export function PageHeader({ eyebrow, title, sub, right }: { eyebrow?: ReactNode; title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="page-header rise">
      <div>
        {eyebrow && <div className="eyebrow" style={{ marginBottom: 6 }}>{eyebrow}</div>}
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {right}
    </div>
  );
}

export function Tile({ label, value, hint, dot, i }: { label: ReactNode; value: ReactNode; hint?: ReactNode; dot?: string; i?: number }) {
  return (
    <div className="tile rise" style={i != null ? stagger(i) : undefined}>
      <div className="label">{dot && <span className="dot" style={{ background: dot }} />}{label}</div>
      <div className="value num">{value}</div>
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export function Segmented<T extends string | number>({ options, value, onChange, label }: {
  options: { value: T; label: ReactNode }[]; value: T; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
