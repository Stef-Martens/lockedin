import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../components/ui";
import Bike from "./trends/Bike";
import Gym from "./trends/Gym";
import Run from "./trends/Run";
import Swim from "./trends/Swim";

type Tab = "bike" | "run" | "swim" | "gym";
const TABS: { key: Tab; label: string }[] = [
  { key: "bike", label: "Bike" }, { key: "run", label: "Run" }, { key: "swim", label: "Swim" }, { key: "gym", label: "Gym" },
];

export default function Trends() {
  const { sport = "bike" } = useParams();
  const tab = (TABS.some((t) => t.key === sport) ? sport : "bike") as Tab;
  return (
    <>
      <PageHeader title="Trends" right={
        <nav className="segmented" aria-label="Sport">
          {TABS.map((t) => (
            <Link key={t.key} to={`/trends/${t.key}`} aria-current={tab === t.key ? "page" : undefined} style={{ minWidth: 72 }}>{t.label}</Link>
          ))}
        </nav>
      } />
      {tab === "bike" && <Bike />}
      {tab === "run" && <Run />}
      {tab === "swim" && <Swim />}
      {tab === "gym" && <Gym />}
    </>
  );
}
