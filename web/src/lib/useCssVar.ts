import { useEffect, useState } from "react";

/** Resolved value of a CSS custom property, refreshed when the colour scheme flips (SVG attrs can't use var()). */
export function useCssVar(name: string): string {
  const read = () => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const [value, setValue] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setValue(read());
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [name]); // eslint-disable-line react-hooks/exhaustive-deps
  return value;
}
