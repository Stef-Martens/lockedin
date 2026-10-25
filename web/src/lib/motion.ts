import { type CSSProperties, useEffect, useState } from "react";

export const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3);

/** Inline animation-delay for the n-th item of a staggered entrance. */
export function stagger(i: number, base = 0.05, step = 0.04): CSSProperties {
  return { animationDelay: `${(base + i * step).toFixed(2)}s` };
}

/** Counts from 0 to target once (ease-out); jumps straight to target with reduced motion. */
export function useCountUp(target: number, ms = 900): number {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0));
  useEffect(() => {
    if (prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      setValue(Math.round(target * easeOutCubic(t)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return value;
}
