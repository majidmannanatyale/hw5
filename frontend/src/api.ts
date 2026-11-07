// Client for the FastAPI backend. Every route the backend offers is wrapped here.
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export type AgentId = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";

export type Ticket = {
  id: number; type: string; requester: string; subject: string;
  sku: string | null; size: string | null; qty: number | null;
  lease_id: number | null; invoice_id: number | null;
  status: string; notes: string | null; created_at: string;
};

export type AgentEvent = {
  ts: string; run_id: string | null; event: string; agent: string;
  tool: string | null; said: string; detail: string; to?: string | null;
};

export type ApprovalItem = {
  id: number; amount?: number; kind?: string; ref_id?: number; reason?: string | null;
  requested_by: string; sku?: string; size?: string; qty?: number;
  discount_pct?: number; min_qty?: number; eta?: string; ticket_id?: number | null;
};
export type Approvals = { payments: ApprovalItem[]; purchase_orders: ApprovalItem[]; promotions: ApprovalItem[] };
export type ApprovalKind = "payment" | "po" | "promo";

export type Outcome = {
  ticket_id: number; assigned_to?: string[]; decision: string; status: string;
  next_steps?: string[]; draft_ids?: number[];
};
export type Usage = { requests: number; input_tokens: number; output_tokens: number; total_tokens: number;
  token_budget: number; pct_of_budget: number };

export type RunInfo = {
  run_id: string; ticket_ids: number[]; started_at: string | null; ended_at: string | null;
  usage: Usage | null; error: string | null; manager_alerts: string[]; outcomes: Outcome[];
  agents: string[]; status: "running" | "done" | "interrupted"; resolved?: boolean;
};

export type AgentReport = { agent: AgentId; steps: number; tool_calls: number; tools: Record<string, number>;
  actions: string[]; said: string; finished: boolean };
export type RunSummary = Omit<RunInfo, "agents"> & {
  agents: AgentReport[];
  conversation: { ts: string; from: string; to: string; kind: "ask" | "reply"; text: string }[];
};

export type RunState = {
  running: boolean; run_id: string | null; ticket_id: number | null; started_at: string | null;
  last: null | { run_id: string; error: string | null; manager_alerts: string[];
    report: null | { outcomes: Outcome[] }; usage: Usage };
};

export type Summary = {
  tickets: { total: number; open: number; waiting: number; closed: number };
  cash: number; decisions_waiting: number; running: boolean; run_id: string | null;
  ticket_id: number | null; active_agents: AgentId[]; missions: number; tokens_used: number;
  last_run: RunInfo | null;
  ticket_list: Ticket[]; cash_accounts: Cash["accounts"]; approvals: Approvals; run_state: RunState;
};

export type LeaderRow = { agent: AgentId; rank: number; xp: number; level: number; missions: number;
  tasks_done: number; actions: number; tool_calls: number; handoffs_received: number; handoffs_made: number;
  drafts: number; approvals_requested: number; flags: number; decisions: number; tickets_closed: number };

export type Cash = { accounts: { name: string; balance: number; date: string }[]; total: number };

export type Draft = { id: number; author: string; audience: string; to_name: string; subject: string; body: string };
export type BoardTicket = Ticket & { drafts: Draft[]; notes: unknown; claims: { task: string; agent: string; status: string }[] };
export type Board = { today: string; tickets: BoardTicket[] };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const d = (await res.json()).detail; if (d) msg = typeof d === "string" ? d : JSON.stringify(d); } catch { /* keep */ }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean }>("/health"),
  summary: () => req<Summary>("/summary"),
  tickets: () => req<Ticket[]>("/tickets?all=true"),
  createTicket: (t: Partial<Ticket>) => req<{ ok: boolean; ticket: Ticket }>("/tickets", { method: "POST", body: JSON.stringify(t) }),
  runTicket: (id: number) => req<{ run_id: string; ticket_id: number }>(`/tickets/${id}/run`, { method: "POST" }),
  current: () => req<RunState>("/runs/current"),
  runs: (ticketId?: number) => req<RunInfo[]>(`/runs${ticketId ? `?ticket_id=${ticketId}` : ""}`),
  runSummary: (runId: string) => req<RunSummary>(`/runs/${runId}/summary`),
  /** Events for one run, oldest first. */
  events: async (runId: string) => (await req<AgentEvent[]>(`/events?limit=500&run_id=${runId}`)).reverse(),
  approvals: () => req<Approvals>("/approvals"),
  decide: (kind: ApprovalKind, id: number, approve: boolean, approver: string) =>
    req<Record<string, unknown>>(`/approvals/${kind}/${id}`, { method: "POST", body: JSON.stringify({ approve, approver }) }),
  cash: () => req<Cash>("/cash"),
  board: () => req<Board>("/board"),
  leaderboard: () => req<LeaderRow[]>("/leaderboard"),
};

export const money = (n: number | undefined | null) =>
  n === undefined || n === null ? "—" : n.toLocaleString("en-US", { style: "currency", currency: "USD" });

export const CLOSED = new Set(["resolved", "shipped", "rejected"]);
export const CELEBRATE = new Set(["resolved", "shipped"]);
export const WAITING = new Set(["waiting_for_human", "blocked", "partially_shipped"]);
