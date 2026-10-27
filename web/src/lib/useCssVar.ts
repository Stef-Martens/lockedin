import { useEffect, useState } from "react";

const read = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Resolved value of a CSS custom property, refreshed when the colour scheme flips (SVG attrs can't use var()). */
export function useCssVar(name: string): string {
  const [value, setValue] = useState(() => read(name));
  useEffect(() => {
    setValue(read(name));
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setValue(read(name));
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [name]);
  return value;
}
