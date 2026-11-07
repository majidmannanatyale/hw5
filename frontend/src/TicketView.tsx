import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, CELEBRATE, CLOSED, type AgentEvent, type Draft, type RunInfo, type RunSummary, type Ticket } from "./api";
import { AGENTS } from "./agents";
import { Arena, Conversation, MissionLamps } from "./Arena";
import { deriveMission } from "./mission";
import { playBlip } from "./sound";
import { Sprite } from "./Sprite";
import { StatusPill } from "./ui";

const REPLAY_MS = 420;
const paced = (evs: AgentEvent[]) =>
  evs.filter(e => e.event !== "tool_result" || e.tool === "get_board" || e.tool === "record_decision");

export function TicketView({ ticket, liveRunId, running, canStart, onStart, onCelebrate }: {
  ticket: Ticket; liveRunId: string | null; running: boolean; canStart: boolean;
  onStart: (id: number) => void; onCelebrate: (label: string) => void;
}) {
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [replayAt, setReplayAt] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const isLive = running && !!liveRunId;
  const doneCount = useRef(0);

  const loadRuns = useCallback(async () => {
    const r = await api.runs(ticket.id);
    setRuns(r);
    return r;
  }, [ticket.id]);

  // Pick the run to show: the live one, else the newest one for this ticket.
  useEffect(() => {
    let alive = true;
    loadRuns().then(r => { if (alive && !isLive) setRunId(r[0]?.run_id ?? null); }).catch(() => {});
    api.board().then(b => alive && setDrafts(b.tickets.find(t => t.id === ticket.id)?.drafts ?? [])).catch(() => {});
    return () => { alive = false; };
  }, [ticket.id, isLive, loadRuns]);

  useEffect(() => { if (isLive) { setRunId(liveRunId); setReplayAt(null); setSummary(null); } }, [isLive, liveRunId]);

  // Events: poll while live, load once otherwise.
  useEffect(() => {
    if (!runId) { setEvents([]); return; }
    let alive = true;
    const load = () => api.events(runId).then(e => alive && setEvents(e)).catch(() => {});
    load();
    const t = isLive ? setInterval(load, 1500) : undefined;
    return () => { alive = false; if (t) clearInterval(t); };
  }, [runId, isLive]);

  // Mission report once the run is over.
  useEffect(() => {
    if (!runId || isLive) return;
    api.runSummary(runId).then(setSummary).catch(() => setSummary(null));
    loadRuns().catch(() => {});
    api.board().then(b => setDrafts(b.tickets.find(t => t.id === ticket.id)?.drafts ?? [])).catch(() => {});
  }, [runId, isLive, loadRuns, ticket.id]);

  // Replay: step through the run's events.
  const steps = useMemo(() => paced(events), [events]);
  useEffect(() => {
    if (replayAt === null) return;
    if (replayAt >= steps.length) {
      setReplayAt(null);
      if (summary?.outcomes.some(o => CELEBRATE.has(o.status))) onCelebrate(`#${ticket.id} · replay`);
      return;
    }
    const t = setTimeout(() => setReplayAt(i => (i === null ? null : i + 1)), REPLAY_MS);
    return () => clearTimeout(t);
  }, [replayAt, steps.length, summary, onCelebrate, ticket.id]);

  const shown = replayAt === null ? events : steps.slice(0, replayAt);
  const closedOutcome = CLOSED.has(ticket.status) || !!summary?.outcomes.some(o => CELEBRATE.has(o.status));
  const view = useMemo(() => deriveMission(shown, closedOutcome), [shown, closedOutcome]);

  // A soft blip each time an agent finishes its part (live or replay).
  useEffect(() => {
    const n = Object.values(view.agents).filter(a => a.state === "done").length;
    if (n > doneCount.current) playBlip();
    doneCount.current = n;
  }, [view]);

  const item = [ticket.qty && `${ticket.qty} ×`, ticket.sku, ticket.size && `size ${ticket.size}`].filter(Boolean).join(" ");
  const notes = (ticket.notes ?? "").split("\n").filter(Boolean);

  return (
    <div className="ticket-view">
      <section className="quest-head panel">
        <div className="qh-main">
          <div className="qh-top"><span className="qid">QUEST #{ticket.id}</span><StatusPill status={ticket.status} /></div>
          <h2>{ticket.subject}</h2>
          <p className="muted">{ticket.requester} · {ticket.type.replaceAll("_", " ")}
            {item && <> · <span className="mono">{item}</span></>}
            {ticket.lease_id && <> · lease #{ticket.lease_id}</>}
            {ticket.invoice_id && <> · invoice #{ticket.invoice_id}</>}</p>
          <p className="qh-note">“{notes[0] ?? ""}”</p>
        </div>
        <div className="qh-actions">
          <button className="btn btn-primary" disabled={!canStart || CLOSED.has(ticket.status)} onClick={() => onStart(ticket.id)}>
            {isLive ? "Mission running…" : CLOSED.has(ticket.status) ? "Quest closed" : "▶ Start mission"}
          </button>
          {!isLive && steps.length > 0 && (
            <button className="btn" onClick={() => setReplayAt(0)} disabled={replayAt !== null}>
              {replayAt !== null ? `Replaying ${replayAt}/${steps.length}` : "⟲ Replay last run"}
            </button>
          )}
          {runs.length > 1 && !isLive && (
            <select className="run-pick" value={runId ?? ""} onChange={e => { setReplayAt(null); setRunId(e.target.value); }}
                    aria-label="Choose a past run">
              {runs.map(r => <option key={r.run_id} value={r.run_id}>Run {r.run_id} · {r.started_at?.slice(11, 16)}</option>)}
            </select>
          )}
        </div>
      </section>

      {runId ? <>
        <section className="panel"><MissionLamps lamps={view.lamps} /></section>
        <div className="arena-row">
          <section className="panel arena-panel">
            <div className="panel-title">ARENA {isLive && <span className="live-tag">● LIVE</span>}
              {replayAt !== null && <span className="live-tag replay">⟲ REPLAY</span>}
              <span className="muted small">run {runId}</span></div>
            <Arena view={view} live={isLive || replayAt !== null} />
          </section>
          <section className="panel convo-panel">
            <div className="panel-title">WHO SAID WHAT</div>
            <Conversation convo={view.convo} />
          </section>
        </div>
      </> : (
        <section className="panel empty-quest">
          <div className="eq-sprites">{(["boss", "inventory", "accounting", "facilities", "customer_service"] as const)
            .map(a => <Sprite key={a} agent={a} size={48} />)}</div>
          <p>No mission has run on this quest yet. Press <b>Start mission</b> to send the party in.</p>
        </section>
      )}

      {summary && !isLive && replayAt === null && <MissionReport s={summary} />}

      {drafts.length > 0 && (
        <section className="panel">
          <div className="panel-title">DRAFTS ON THE BOARD <span className="muted small">never sent</span></div>
          {drafts.map(d => (
            <article key={d.id} className="draft" style={{ borderColor: AGENTS[d.author as keyof typeof AGENTS]?.color }}>
              <div className="small muted">Draft #{d.id} · to {d.to_name} ({d.audience}) · by {d.author}</div>
              <strong>{d.subject}</strong><p>{d.body}</p>
            </article>
          ))}
        </section>
      )}
    </div>
  );
}

function MissionReport({ s }: { s: RunSummary }) {
  const o = s.outcomes[0];
  return (
    <section className="panel report">
      <div className="panel-title">MISSION REPORT <span className="muted small">run {s.run_id}</span></div>
      {o && <div className="report-outcome"><StatusPill status={o.status} /><p>{o.decision}</p></div>}
      {s.manager_alerts.length > 0 && <ul className="alerts">{s.manager_alerts.map((a, i) => <li key={i}>{a}</li>)}</ul>}
      <div className="report-grid">
        {s.agents.map(a => {
          const m = AGENTS[a.agent];
          return (
            <article key={a.agent} className="agent-card" style={{ borderColor: m.color }}>
              <header><Sprite agent={a.agent} size={40} /><div><strong style={{ color: m.color }}>{m.name}</strong>
                <span className="muted small">{m.title}</span></div></header>
              <p>{a.said || "—"}</p>
              {a.actions.length > 0 && <div className="chips">{a.actions.map((t, i) => <code key={i} className="chip act">{t}</code>)}</div>}
              <div className="small muted">{a.steps} steps · {a.tool_calls} tool calls · {Object.keys(a.tools).length} different tools</div>
            </article>
          );
        })}
      </div>
      {s.usage && <p className="small muted">{s.usage.requests} model calls · {s.usage.total_tokens.toLocaleString()} tokens
        ({s.usage.pct_of_budget}% of budget)</p>}
    </section>
  );
}
