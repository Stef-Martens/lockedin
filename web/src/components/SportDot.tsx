import type { Sport } from "../lib/format";

export default function SportDot({ sport }: { sport: Sport }) {
  return <span className="dot" style={{ background: `var(--sport-${sport})` }} aria-hidden="true" />;
}
