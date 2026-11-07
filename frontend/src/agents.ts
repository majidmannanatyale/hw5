import type { AgentId } from "./api";

// The party. Colors are used for every sprite, name, bubble, summary and leaderboard row.
// Lines are flavor only; every fact on screen comes from the backend.
export type AgentMeta = {
  id: AgentId; name: string; title: string; color: string; dark: string;
  personality: string; start: string; done: string;
};

export const AGENTS: Record<AgentId, AgentMeta> = {
  boss: {
    id: "boss", name: "King Grimhorn", title: "The Boss", color: "#b28dff", dark: "#6c4fc0",
    personality: "Gruff, theatrical and fair. Hates waste, loves a decision, breaks every tie.",
    start: "GRRAH. Who's on this?", done: "Decision made. Next!",
  },
  inventory: {
    id: "inventory", name: "Pip Stockwell", title: "Inventory", color: "#4fd1c5", dark: "#2a8f87",
    personality: "Quick and eager. Counts everything twice.",
    start: "On it! Counting now…", done: "Shelf checked!",
  },
  accounting: {
    id: "accounting", name: "Ada Ledger", title: "Accounting", color: "#7aa2ff", dark: "#4466c4",
    personality: "Precise and calm. Protects every dollar.",
    start: "Let me check the numbers.", done: "Books balanced.",
  },
  facilities: {
    id: "facilities", name: "Bo Brickley", title: "Facilities", color: "#ff9f5a", dark: "#bf6a2c",
    personality: "Laid-back and practical. Knows the building inside out.",
    start: "Rent's my beat. I'll handle it.", done: "Space is squared away.",
  },
  customer_service: {
    id: "customer_service", name: "Sunny Vale", title: "Customer Service", color: "#ff7eb6", dark: "#c44d83",
    personality: "Warm and clear. Never promises what isn't approved.",
    start: "I'll write them something kind.", done: "Draft's on the board.",
  },
};

export const AGENT_ORDER: AgentId[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

export const isAgent = (s: string): s is AgentId => s in AGENTS;

export const nameOf = (s: string) => (isAgent(s) ? AGENTS[s].name : s === "majid" ? "Majid" : s);
export const colorOf = (s: string) => (isAgent(s) ? AGENTS[s].color : s === "majid" ? "#ffd166" : "#8a97b3");
