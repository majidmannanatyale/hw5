import type { AgentEvent, AgentId } from "./api";
import { AGENTS, AGENT_ORDER, isAgent } from "./agents";

export type LampState = "idle" | "working" | "done" | "waiting";
export type Beam = { key: number; from: string; to: string; text: string; kind: "ask" | "reply" };
export type ConvoLine = { key: number; ts: string; from: string; to: string; kind: "ask" | "reply"; text: string };

export type MissionView = {
  agents: Record<AgentId, { state: LampState; line: string; tool: string | null }>;
  beam: Beam | null;
  convo: ConvoLine[];
  lamps: { label: string; state: LampState }[];
  finished: boolean;
};

const SPECIALISTS: AgentId[] = ["accounting", "facilities", "customer_service"];

/** Turn a run's events (oldest first) into what the arena shows. Progress only moves forward. */
export function deriveMission(events: (AgentEvent & { to?: string | null })[], closedOutcome: boolean): MissionView {
  const agents = Object.fromEntries(AGENT_ORDER.map(a => [a, { state: "idle" as LampState, line: "", tool: null as string | null }])) as MissionView["agents"];
  const convo: ConvoLine[] = [];
  const askedBy: Record<string, string> = {};
  let beam: Beam | null = null;
  let readDone = false, decisionStarted = false, decisionDone = false, finished = false;

  events.forEach((e, i) => {
    const a = e.agent;
    if (e.event === "run_end") finished = true;
    if (!isAgent(a)) return;
    const s = agents[a];
    switch (e.event) {
      case "agent_start":
        if (s.state !== "done") s.state = "working";
        s.line = AGENTS[a].start;
        break;
      case "tool_call":
        s.tool = e.tool;
        if (e.tool === "record_decision") decisionStarted = true;
        break;
      case "tool_result":
        if (e.tool === "get_board") readDone = true;
        if (e.tool === "record_decision") decisionDone = true;
        break;
      case "agent_step":
        if (e.said) s.line = e.said;
        break;
      case "delegate":
      case "ask_teammate": {
        const to = e.to ?? "";
        const text = e.said.replace(/^Asked [^:]+:\s*/, "");
        askedBy[to] = a;
        convo.push({ key: i, ts: e.ts, from: a, to, kind: "ask", text });
        beam = { key: i, from: a, to, text, kind: "ask" };
        s.line = text;
        readDone = readDone || a === "boss";
        break;
      }
      case "agent_end": {
        s.state = "done"; s.tool = null;
        s.line = e.said || AGENTS[a].done;
        const to = askedBy[a] ?? "majid";
        convo.push({ key: i, ts: e.ts, from: a, to, kind: "reply", text: s.line });
        beam = { key: i, from: a, to, text: s.line, kind: "reply" };
        if (a === "boss") decisionDone = true;
        break;
      }
    }
  });

  const boss = agents.boss.state, inv = agents.inventory.state;
  const started = SPECIALISTS.filter(x => agents[x].state !== "idle");
  const team: LampState = started.length
    ? (started.every(x => agents[x].state === "done") ? "done" : "working")
    : decisionStarted || decisionDone ? "done" : inv === "done" ? "working" : "idle";
  const lamps = [
    { label: "Read ticket", state: (readDone ? "done" : boss !== "idle" ? "working" : "idle") as LampState },
    { label: "Inventory check", state: inv },
    { label: "Team work", state: team },
    { label: "Boss decision", state: (decisionDone ? "done" : decisionStarted ? "working" : "idle") as LampState },
    { label: "Closed", state: (finished ? (closedOutcome ? "done" : "waiting") : "idle") as LampState },
  ];
  return { agents, beam, convo, lamps, finished };
}

export const LAMP_TEXT: Record<LampState, string> = {
  idle: "not started", working: "in progress", done: "done", waiting: "waiting on Majid",
};
