import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../lib/api";
import { MAC_STALE_MS, ago, olderThan, recent } from "../lib/format";
import { stagger } from "../lib/motion";
import type { MacStatus, Status } from "../lib/types";

const POLL_MS = 5000;
const GIVE_UP_MS = 5 * 60 * 1000;
const QUIET_MS = 3 * 60 * 1000; // the Mac polls every minute while it's awake

const isOpen = (m: MacStatus) => !!m.check_requested_at && (!m.check_done_at || m.check_done_at < m.check_requested_at);
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function found(n: number | null): string {
  if (!n) return "Done · nothing new";
  return `Done · ${n} new workout${n === 1 ? "" : "s"}`;
}

/** The Mac's last check, and "Check again": the Mac picks the request up within a minute, nudges iCloud,
 * rescans and reports back. The site can't reach the Mac, so all this card can do is ask and wait. */
export default function MacCheck({ mac: initial, lastWorkout }: { mac: MacStatus; lastWorkout: string | null }) {
  const [mac, setMac] = useState(initial);
  const [pressed, setPressed] = useState(false);
  const [gaveUp, setGaveUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const since = useRef(Date.now());
  const waiting = isOpen(mac);

  useEffect(() => { setMac(initial); }, [initial]);

  useEffect(() => {
    if (!waiting || gaveUp) return;
    const id = setInterval(() => {
      if (Date.now() - since.current >= GIVE_UP_MS) { setGaveUp(true); return; }
      apiFetch<Status>("/api/status").then((s) => { if (s.mac) setMac(s.mac); }).catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [waiting, gaveUp]);

  async function check() {
    setError(null);
    setGaveUp(false);
    since.current = Date.now();
    try {
      setMac(await apiFetch<MacStatus>("/api/sync/mac/check", { method: "POST" }));
      setPressed(true);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const stale = olderThan(mac.last_run_at, MAC_STALE_MS);
  let line: string | null = null;
  if (waiting && mac.last_seen_at && olderThan(mac.last_seen_at, QUIET_MS)) {
    line = `Your Mac hasn't been in touch since ${hhmm(mac.last_seen_at)}. It'll check as soon as it wakes up.`;
  } else if (waiting && gaveUp) {
    line = "Still waiting. It'll show up here once your Mac has checked.";
  } else if (waiting) {
    line = "Waiting for your Mac…";
  } else if (pressed) {
    line = found(mac.check_uploaded);
  }

  return (
    <div className="card rise" style={stagger(4)}>
      <div className="row spread"><span className="eyebrow">Your Mac</span>
        <span className={`sync-dot${mac.last_run_at && stale ? " stale" : recent(lastWorkout) ? " live pulse" : ""}`} aria-hidden="true" />
      </div>
      <div className="display" style={{ fontSize: 34, marginTop: 10 }}>{mac.last_run_at ? `Checked ${ago(mac.last_run_at)}` : "Not reported yet"}</div>
      <div className="secondary" style={{ fontSize: 14 }}>Last workout {ago(lastWorkout)}</div>
      <div className="row" style={{ gap: 12, marginTop: 14, flexWrap: "wrap" }}>
        <button type="button" className="btn" disabled={waiting && !gaveUp} onClick={check}>Check again</button>
        {line && <span className="secondary" role="status" style={{ fontSize: 14 }}>{line}</span>}
        {error && <span className="error" style={{ fontSize: 14 }}>{error}</span>}
      </div>
    </div>
  );
}
