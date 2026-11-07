import { useEffect, useState } from "react";
import { api, type LeaderRow } from "./api";
import { AGENTS } from "./agents";
import { Sprite } from "./Sprite";

const MEDAL = ["🥇", "🥈", "🥉"];

export function Leaderboard() {
  const [rows, setRows] = useState<LeaderRow[] | null>(null);
  useEffect(() => { api.leaderboard().then(setRows).catch(() => setRows([])); }, []);
  if (!rows) return <p className="muted">Loading the hall of fame…</p>;
  return (
    <div className="leaderboard">
      <section className="podium">
        {rows.slice(0, 3).map(r => {
          const m = AGENTS[r.agent];
          return (
            <article key={r.agent} className={`podium-spot rank-${r.rank}`} style={{ borderColor: m.color }}>
              <span className="medal" aria-hidden>{MEDAL[r.rank - 1]}</span>
              <Sprite agent={r.agent} size={r.rank === 1 ? 84 : 64} />
              <strong style={{ color: m.color }}>{m.name}</strong>
              <span className="lvl">LV {r.level} · {r.xp} XP</span>
            </article>
          );
        })}
      </section>
      <section className="panel">
        <div className="panel-title">AGENT STATS <span className="muted small">XP: +25 ticket closed · +10 task · +5 action · +3 hand-off · +1 tool call</span></div>
        <div className="table-wrap">
          <table className="lb">
            <thead><tr>
              <th>#</th><th>Agent</th><th>Level / XP</th><th>Missions</th><th>Closed</th><th>Tasks</th><th>Actions</th>
              <th>Tool calls</th><th>Hand-offs in</th><th>Hand-offs out</th><th>Drafts</th><th>Approvals asked</th><th>Flags</th><th>Decisions</th>
            </tr></thead>
            <tbody>{rows.map(r => {
              const m = AGENTS[r.agent];
              const pct = r.xp % 100;
              return (
                <tr key={r.agent}>
                  <td className="rank">{r.rank}</td>
                  <td><div className="lb-agent"><Sprite agent={r.agent} size={28} /><strong style={{ color: m.color }}>{m.name}</strong></div></td>
                  <td><div className="xp"><span>LV {r.level}</span>
                    <div className="xp-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
                         aria-label={`${pct} of 100 XP to next level`}>
                      <i style={{ width: `${pct}%`, background: m.color }} /></div><span className="small muted">{r.xp}</span></div></td>
                  <td>{r.missions}</td><td>{r.tickets_closed}</td><td>{r.tasks_done}</td><td>{r.actions}</td>
                  <td>{r.tool_calls}</td><td>{r.handoffs_received}</td><td>{r.handoffs_made}</td><td>{r.drafts}</td>
                  <td>{r.approvals_requested}</td><td>{r.flags}</td><td>{r.decisions}</td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
