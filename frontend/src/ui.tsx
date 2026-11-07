import { CLOSED, WAITING } from "./api";

export function StatusPill({ status }: { status: string }) {
  const tone = CLOSED.has(status) ? (status === "rejected" ? "bad" : "ok") : WAITING.has(status) ? "warn" : "info";
  return <span className={`pill pill-${tone}`}>{status.replaceAll("_", " ")}</span>;
}

export function Stat({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
    </div>
  );
}
