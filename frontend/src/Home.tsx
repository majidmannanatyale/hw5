import { money, CLOSED, type Summary, type Ticket } from "./api";
import { AGENTS, AGENT_ORDER } from "./agents";
import { Lamp } from "./Arena";
import { Sprite } from "./Sprite";
import { Stat, StatusPill } from "./ui";

export function Home({ summary, tickets, canStart, onStart, onOpen, onDecisions }: {
  summary: Summary | null; tickets: Ticket[]; canStart: boolean;
  onStart: (id: number) => void; onOpen: (id: number) => void; onDecisions: () => void;
}) {
  const s = summary;
  const last = s?.last_run;
  return (
    <div className="home">
      <section className="stats-row">
        <Stat label="Quests" value={s?.tickets.total ?? "…"} />
        <Stat label="Open" value={s?.tickets.open ?? "…"} tone="info" />
        <Stat label="Waiting" value={s?.tickets.waiting ?? "…"} tone="warn" />
        <Stat label="Closed" value={s?.tickets.closed ?? "…"} tone="ok" />
        <Stat label="Checking" value={s ? money(s.cash) : "…"} />
        <Stat label="Tokens used" value={s ? s.tokens_used.toLocaleString() : "…"} />
      </section>

      <div className="home-grid">
        <section className="panel">
          <div className="panel-title">THE PARTY {s?.running && <span className="live-tag">● MISSION ON #{s.ticket_id}</span>}</div>
          <div className="party">
            {AGENT_ORDER.map(a => {
              const m = AGENTS[a];
              const working = !!s?.active_agents.includes(a);
              const joinedLast = !!last?.agents.includes(a);
              const state = working ? "working" : s?.running ? "idle" : joinedLast ? "done" : "idle";
              return (
                <article key={a} className={`member member-${state}`} style={{ borderColor: working ? m.color : undefined }}>
                  <Sprite agent={a} size={a === "boss" ? 64 : 52} />
                  <div className="member-text">
                    <strong style={{ color: m.color }}>{m.name}</strong>
                    <span className="muted small">{m.title}</span>
                    <span className="small">{m.personality}</span>
                  </div>
                  <div className="member-lamp"><Lamp state={state} label={m.name} />
                    <span className="small muted">{working ? "working" : s?.running ? "standing by" : joinedLast ? "last mission" : "idle"}</span></div>
                </article>
              );
            })}
          </div>
        </section>

        <div className="home-side">
          <section className={`panel decisions ${s?.decisions_waiting ? "has" : ""}`}>
            <div className="panel-title">YOUR DECISIONS</div>
            {s?.decisions_waiting
              ? <><p><b>{s.decisions_waiting}</b> waiting for Majid.</p>
                  <button className="btn btn-primary" onClick={onDecisions}>Review now</button></>
              : <p className="muted">Nothing needs your approval.</p>}
          </section>
          <section className="panel">
            <div className="panel-title">LAST MISSION</div>
            {last ? <>
              <p className="small muted">Run {last.run_id} · quest #{last.ticket_ids.join(", #")} · {last.usage?.total_tokens.toLocaleString()} tokens</p>
              {last.outcomes.map(o => <div key={o.ticket_id} className="last-out"><StatusPill status={o.status} /><p>{o.decision}</p></div>)}
              <div className="last-party">{last.agents.filter(a => a in AGENTS).map(a =>
                <Sprite key={a} agent={a as keyof typeof AGENTS} size={28} />)}</div>
            </> : <p className="muted">No missions yet.</p>}
          </section>
        </div>
      </div>

      <section className="panel">
        <div className="panel-title">QUEST BOARD <span className="muted small">pick a quest to send the party in</span></div>
        <div className="quests">
          {tickets.map(t => {
            const live = s?.running && s.ticket_id === t.id;
            return (
              <article key={t.id} className={`quest ${live ? "live" : ""} ${CLOSED.has(t.status) ? "closed" : ""}`}>
                <button className="quest-open" onClick={() => onOpen(t.id)} aria-label={`Open quest ${t.id}`}>
                  <span className="qid">#{t.id}</span>
                  <strong>{t.subject}</strong>
                  <span className="muted small">{t.requester}</span>
                </button>
                <StatusPill status={t.status} />
                <button className="btn btn-sm btn-primary" disabled={!canStart || CLOSED.has(t.status)} onClick={() => onStart(t.id)}>
                  {live ? "Running…" : CLOSED.has(t.status) ? "Closed" : "▶ Start"}
                </button>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
