import { useCallback, useEffect, useRef, useState } from "react";
import { api, money, CELEBRATE, type Approvals, type Cash, type RunState, type Summary, type Ticket } from "./api";
import { ApprovalModal, rowsOf } from "./ApprovalModal";
import { Fireworks } from "./Fireworks";
import { Home } from "./Home";
import { Leaderboard } from "./Leaderboard";
import { isMuted, playFanfare, setMuted, unlockAudio } from "./sound";
import { TicketView } from "./TicketView";

type Tab = "home" | "leaderboard" | number;

export default function App() {
  const [tab, setTab] = useState<Tab>("home");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [run, setRun] = useState<RunState | null>(null);
  const [approvals, setApprovals] = useState<Approvals | null>(null);
  const [cash, setCash] = useState<Cash | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState<string | null>(null);
  const [modal, setModal] = useState(false);
  const [muted, setMute] = useState(isMuted());
  const [flash, setFlash] = useState(false);
  const prevStatus = useRef<Map<number, string> | null>(null);
  const seenDecisions = useRef<Set<string>>(new Set());
  const prevCash = useRef<number | null>(null);

  const celebrateTicket = useCallback((label: string) => { setCelebrate(label); playFanfare(); }, []);

  const refresh = useCallback(async () => {
    try {
      const s = await api.summary();  // one request carries tickets, cash, approvals and run state
      const t = s.ticket_list, r = s.run_state, a = s.approvals;
      const c = { accounts: s.cash_accounts, total: s.cash };
      setSummary(s); setTickets(t); setRun(r); setApprovals(a); setCash(c); setOnline(true); setErr(null);

      // Fireworks whenever a ticket newly turns resolved (or shipped).
      const before = prevStatus.current;
      if (before) for (const tk of t) {
        const was = before.get(tk.id);
        if (was && was !== tk.status && CELEBRATE.has(tk.status) && !CELEBRATE.has(was)) celebrateTicket(`#${tk.id} · ${tk.subject}`);
      }
      prevStatus.current = new Map(t.map(x => [x.id, x.status]));

      // Open the decision dialog on its own when something new needs approval.
      const keys = rowsOf(a).map(x => `${x.kind}${x.item.id}`);
      if (keys.some(k => !seenDecisions.current.has(k))) setModal(true);
      keys.forEach(k => seenDecisions.current.add(k));

      if (prevCash.current !== null && prevCash.current !== c.total) { setFlash(true); setTimeout(() => setFlash(false), 1200); }
      prevCash.current = c.total;
    } catch (e) {
      setOnline(false); setErr(`Can't reach the backend at localhost:8000 (${(e as Error).message}).`);
    }
  }, [celebrateTicket]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const t = setInterval(() => { void refresh(); }, run?.running ? 1500 : 4000);
    return () => clearInterval(t);
  }, [run?.running, refresh]);

  const start = async (id: number) => {
    unlockAudio();
    try { await api.runTicket(id); setTab(id); await refresh(); }
    catch (e) { setErr((e as Error).message); }
  };

  const toggleMute = () => { unlockAudio(); setMuted(!muted); setMute(!muted); };
  const decisions = rowsOf(approvals).length;
  const canStart = !run?.running && online !== false;
  const current = typeof tab === "number" ? tickets.find(t => t.id === tab) : undefined;
  const tickerText = [
    `CHECKING ${money(cash?.total)}`,
    cash?.accounts[0] ? `AS OF ${cash.accounts[0].date}` : "",
    `QUESTS ${summary?.tickets.total ?? "…"}`, `OPEN ${summary?.tickets.open ?? "…"}`,
    `WAITING ${summary?.tickets.waiting ?? "…"}`, `CLOSED ${summary?.tickets.closed ?? "…"}`,
    `DECISIONS ${decisions}`, run?.running ? `MISSION LIVE ON #${run.ticket_id}` : "PARTY STANDING BY",
  ].filter(Boolean).join("   ◆   ");

  return (
    <div className="deck" onPointerDown={unlockAudio}>
      <div className="scanlines" aria-hidden />
      <header className="deck-head">
        <div className="brand">
          <span className="brand-mark" aria-hidden>▚</span>
          <div><h1>CAMPUS CUSTOMS</h1><span className="brand-sub">COMMAND DECK</span></div>
          <span className={`conn ${online === false ? "off" : online ? "on" : ""}`}
                title={online === false ? "Backend offline (localhost:8000)" : "Connected to localhost:8000"}
                aria-label={online === false ? "Backend offline" : "Backend connected"} />
        </div>
        <div className="head-tools">
          <button className="btn btn-ghost" onClick={toggleMute} aria-pressed={!muted} aria-label={muted ? "Sound off" : "Sound on"}>
            {muted ? "🔇" : "🔊"}</button>
          <button className={`btn decision-badge ${decisions ? "has" : ""}`} onClick={() => setModal(true)}>
            ⚑ {decisions} decision{decisions === 1 ? "" : "s"}</button>
          <div className={`ticker ${flash ? "flash" : ""}`} aria-label={`Checking balance ${money(cash?.total)}`}>
            <span className="ticker-label">CHECKING</span>
            <strong className="ticker-value">{money(cash?.total)}</strong>
            <div className="ticker-tape" aria-hidden><span>{tickerText}   ◆   {tickerText}   ◆   </span></div>
          </div>
        </div>
      </header>

      <nav className="tabs" role="tablist" aria-label="Deck tabs">
        <button role="tab" aria-selected={tab === "home"} className="tab" onClick={() => setTab("home")}>⌂ HOME</button>
        {tickets.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className="tab" onClick={() => setTab(t.id)}>
            <span className={`tab-dot st-${t.status}`} aria-hidden />#{t.id}
            {run?.running && run.ticket_id === t.id && <span className="tab-live" aria-label="running">●</span>}
          </button>
        ))}
        <button role="tab" aria-selected={tab === "leaderboard"} className="tab" onClick={() => setTab("leaderboard")}>★ LEADERBOARD</button>
      </nav>

      {err && <div className="banner-err" role="alert">⚠ {err}<button onClick={() => setErr(null)} aria-label="Dismiss">✕</button></div>}

      <main className="deck-main">
        {tab === "home" && <Home summary={summary} tickets={tickets} canStart={canStart} onStart={start}
                                 onOpen={id => setTab(id)} onDecisions={() => setModal(true)} />}
        {tab === "leaderboard" && <Leaderboard key={summary?.missions} />}
        {current && <TicketView key={current.id} ticket={current} canStart={canStart} onStart={start}
                                running={!!run?.running && run.ticket_id === current.id} liveRunId={run?.run_id ?? null}
                                onCelebrate={celebrateTicket} />}
      </main>

      {modal && <ApprovalModal approvals={approvals} cash={cash?.total ?? 0} onClose={() => setModal(false)}
                               onDone={() => { void refresh(); }} />}
      {celebrate && <Fireworks label={celebrate} onDone={() => setCelebrate(null)} />}
    </div>
  );
}
