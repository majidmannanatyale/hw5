import type { CSSProperties } from "react";
import type { AgentId } from "./api";
import { AGENTS, AGENT_ORDER, colorOf, isAgent, nameOf } from "./agents";
import { LAMP_TEXT, type LampState, type MissionView } from "./mission";
import { Sprite } from "./Sprite";

// Where each character stands in the arena (percent of the stage).
const POS: Record<string, { x: number; y: number }> = {
  boss: { x: 50, y: 47 },
  inventory: { x: 15, y: 22 }, accounting: { x: 85, y: 22 },
  facilities: { x: 15, y: 74 }, customer_service: { x: 85, y: 74 },
  majid: { x: 50, y: 97 },
};

export function Lamp({ state, label, size = "md" }: { state: LampState; label: string; size?: "sm" | "md" | "lg" }) {
  return <span className={`lamp lamp-${state} lamp-${size}`} role="img" aria-label={`${label}: ${LAMP_TEXT[state]}`} />;
}

export function MissionLamps({ lamps }: { lamps: MissionView["lamps"] }) {
  return (
    <ol className="mission-lamps" aria-label="Mission progress">
      {lamps.map((l, i) => (
        <li key={l.label} className={`ml ml-${l.state}`}>
          <Lamp state={l.state} label={l.label} size="lg" />
          <span className="ml-label">{l.label}</span>
          <span className="ml-state">{LAMP_TEXT[l.state]}</span>
          {i < lamps.length - 1 && <span className={`ml-wire ${l.state === "done" ? "lit" : ""}`} aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

export function Arena({ view, live }: { view: MissionView; live: boolean }) {
  const beam = view.beam;
  const from = beam ? POS[beam.from] : null, to = beam ? POS[beam.to] : null;
  return (
    <div className={`arena ${live ? "is-live" : ""}`}>
      <div className="arena-floor" aria-hidden />
      <svg className="arena-wires" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {AGENT_ORDER.filter(a => a !== "boss").map(a => (
          <line key={a} x1={POS.boss.x} y1={POS.boss.y} x2={POS[a].x} y2={POS[a].y} className="wire" />
        ))}
        {from && to && beam && (
          <line key={`b${beam.key}`} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="beam"
                style={{ stroke: colorOf(beam.from) }} />
        )}
      </svg>
      {from && to && beam && (
        <span key={`d${beam.key}`} className="beam-dot"
              style={{ "--x1": `${from.x}%`, "--y1": `${from.y}%`, "--x2": `${to.x}%`, "--y2": `${to.y}%`,
                       background: colorOf(beam.from), boxShadow: `0 0 14px ${colorOf(beam.from)}` } as CSSProperties} />
      )}

      {AGENT_ORDER.map(a => {
        const s = view.agents[a], p = POS[a], meta = AGENTS[a];
        const talking = beam && (beam.from === a || beam.to === a);
        const below = p.y < 40;
        return (
          <div key={a} className={`node node-${s.state} ${talking ? "talking" : ""} ${a === "boss" ? "node-boss" : ""}`}
               style={{ left: `${p.x}%`, top: `${p.y}%`, "--c": meta.color } as CSSProperties}>
            {s.line && <div key={s.line} className={`bubble ${below ? "bubble-below" : ""}`} style={{ borderColor: meta.color }}>
              <span>{s.line.length > 150 ? s.line.slice(0, 150) + "…" : s.line}</span></div>}
            <div className="avatar"><Sprite agent={a} size={a === "boss" ? 88 : 68} /></div>
            <div className="nameplate">
              <Lamp state={s.state} label={meta.name} size="sm" />
              <strong style={{ color: meta.color }}>{meta.name}</strong>
            </div>
            <div className="node-sub">{s.tool && s.state === "working" ? <code>{s.tool}</code> : meta.title}</div>
          </div>
        );
      })}
      <div className="node node-majid" style={{ left: `${POS.majid.x}%`, top: `${POS.majid.y}%` }}>
        <span className="majid-chip">MAJID · HUMAN</span>
      </div>
    </div>
  );
}

export function Conversation({ convo }: { convo: MissionView["convo"] }) {
  if (!convo.length) return <p className="muted small">No one has spoken yet.</p>;
  return (
    <ol className="convo">
      {convo.map(c => (
        <li key={c.key} className={`cv cv-${c.kind}`}>
          <div className="cv-head">
            {isAgent(c.from) && <Sprite agent={c.from as AgentId} size={22} />}
            <strong style={{ color: colorOf(c.from) }}>{nameOf(c.from)}</strong>
            <span className="cv-arrow">{c.kind === "ask" ? "asks" : "reports to"}</span>
            <strong style={{ color: colorOf(c.to) }}>{nameOf(c.to)}</strong>
            <time>{c.ts.slice(11, 19)}</time>
          </div>
          <p style={{ borderColor: colorOf(c.from) }}>{c.text}</p>
        </li>
      ))}
    </ol>
  );
}
