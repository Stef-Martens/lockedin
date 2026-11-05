import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { dayMonth, SPORT_LABEL, type Sport } from "../lib/format";
import { Card, SectionHead } from "./ui";

type Label = "on_plan" | "close" | "off_plan" | "unplanned";
type Verdict = { status: "done" | "writing" | "over_budget" | "failed" | "none"; label?: Label; text?: string };
type Reply = {
  activity: { id: number; sport: Sport; day: string; title: string | null; item_id: number | null } | null;
  verdict: Verdict;
};

const LABEL: Record<Label, { text: string; pill: string }> = {
  on_plan: { text: "On plan", pill: "done" },
  close: { text: "Close to plan", pill: "close" },
  off_plan: { text: "Off plan", pill: "behind" },
  unplanned: { text: "Not planned", pill: "" },
};
const STATE_TEXT: Record<string, string> = {
  writing: "The coach is looking at it…",
  over_budget: "Today's coach budget is used up; this appears tomorrow.",
  failed: "Couldn't write this one; it tries again next time you open this page.",
};

const POLL_MS = 3000;
const POLL_MAX = 30; // 90 seconds in all

/**
 * The coach's verdict on a workout. It loads on its own, so a slow or failed verdict never touches the page around it.
 * `latest` is the dashboard card, with a header; with an `activityId` the page already says which workout it is.
 */
export default function VerdictCard(props: { source: "latest" } | { activityId: number }) {
  const latest = "source" in props;
  const path = latest ? "/api/verdicts/latest" : `/api/verdicts/${props.activityId}`;
  const [reply, setReply] = useState<Reply | null>(null);

  useEffect(() => {
    let live = true;
    let over = false; // a final answer came, or the first request failed with nothing to show
    let shown = false;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setReply(null);
    const stop = () => { over = true; clearTimeout(timer); };
    const take = (r: Reply | null | undefined) => {
      if (!live || over || !r?.verdict) return;
      shown = true;
      setReply(r);
      if (r.verdict.status !== "writing") stop();
    };
    // The first request is the writer and can take a minute, so a poll (which only sees "writing") shows the state meanwhile.
    const poll = () => {
      polls += 1;
      apiFetch<Reply>(path).then(take, () => undefined).then(() => {
        if (live && !over && polls < POLL_MAX) timer = setTimeout(poll, POLL_MS);
      });
    };
    timer = setTimeout(poll, POLL_MS);
    apiFetch<Reply>(path).then((r) => r?.verdict ? take(r) : (shown || stop()), () => { if (!shown) stop(); });
    return () => { live = false; clearTimeout(timer); };
  }, [path]);

  if (!reply || reply.verdict.status === "none" || (latest && !reply.activity)) return null;
  const { activity: a, verdict: v } = reply;
  const label = v.status === "done" && v.label ? LABEL[v.label] : null;
  const body = label ? v.text : STATE_TEXT[v.status];
  if (!body) return null;
  const to = a ? (a.item_id != null ? `/agenda/${a.item_id}` : `/activities/${a.id}`) : null;

  return (
    <Card i={0}>
      {latest && a && (
        <SectionHead title="Last workout"
          right={to && <Link to={to} style={{ fontSize: 13, fontWeight: 600, textDecoration: "none" }}>See how it went</Link>} />
      )}
      {latest && a && <div className="secondary" style={{ fontSize: 14, marginBottom: 8 }}>
        {dayMonth(a.day)} · {SPORT_LABEL[a.sport]}{a.title ? ` · ${a.title}` : ""}</div>}
      {label && <span className={`pill ${label.pill}`}>{label.text}</span>}
      <p style={{ margin: label ? "8px 0 0" : 0 }} className={label ? undefined : "secondary"}>{body}</p>
    </Card>
  );
}
