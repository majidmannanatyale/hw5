# Harness — Campus Customs Multi-Agent Team

## Shop rules (apply to every agent, prompt, tool, and constraint)

1. **"Today" is `desk.date_today`.** Overdue means a due date earlier than this date. Never use the system clock.
2. **Vendor lead times come from `vendors.lead_days`.** Never guess a lead time.
3. **New product ships only when there are no open unpaid invoices.**
4. **Human approval is REQUIRED for every payment.** This rule is absolute. No agent may pay, or tell anyone a payment was made, without explicit human approval recorded in `payments.approved_by`.
5. **No negative balances.** If cash is short, the pay tool must refuse.
6. **Cash only goes out.** Revenue is not modeled, so no money comes in.
7. **Never email customers or call real vendors.** Every outreach is a draft or note only.
8. **Database:** the MCP server reads and writes only `data/campus_customs_new.db`. `data/campus_customs.db` is the read-only original and must never be modified. Before the full ticket-resolution run, `campus_customs_new.db` is reset from `campus_customs.db`.

## Database tables and why they matter

**desk**

* **Fields:** `date_today`, `notes`
* Sets what "today" is for the shop, so the agents know what is overdue and what is coming due soon.

**inventory**

* **Fields:** `sku`, `name`, `size`, `qty`, `location`
* Shows how many of each item and size are on the shelf, so the agents know whether an order can go out now or needs a reprint first.

**pricing**

* **Fields:** `sku`, `unit_cost`, `list_price`
* Lists what each item costs the shop and what it sells for, so any discount stays above cost and the shop never sells at a loss.

**vendors**

* **Fields:** `id`, `name`, `specialty`, `lead_days`
* Lists who makes or delivers each kind of product and how many days they take, so the agents can give honest delivery dates.

**leases**

* **Fields:** `id`, `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`
* Holds the shop's rent and when it is due, so rent is planned for and never missed.

**cash_accounts**

* **Fields:** `name`, `balance`, `date`
* Holds the shop's only cash balance. Every payment is checked against it so the shop never goes into the negative.

**payments**

* **Fields:** `id`, `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`
* The record of every payment made, including who approved it. It is the proof that a human signed off on each payment.

**invoices**

* **Fields:** `id`, `vendor_id`, `amount`, `due_date`, `status`, `description`
* Lists the bills the shop owes vendors and when they are due. Any unpaid bill stops new product from shipping.

**tickets**

* **Fields:** `id`, `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id`, `invoice_id`, `status`, `notes`, `created_at`
* The team's to-do list of customer and business requests. Each ticket points to the item, lease, or bill it depends on.

### Helper tables (added to campus_customs_new.db by the MCP server, never to the original)

**payment_requests**

* **Fields:** `id`, `kind`, `ref_id`, `amount`, `account`, `reason`, `requested_by`, `requested_at`, `status`, `decided_by`, `decided_at`
* The human-approval queue for payments. Agents can only add rows; only Majid's approval turns one into a payment.

**purchase_orders**

* **Fields:** `id`, `ticket_id`, `vendor_id`, `sku`, `size`, `qty`, `amount`, `eta`, `reason`, `requested_by`, `requested_at`, `status`, `invoice_id`, `decided_by`, `decided_at`
* Reprint orders waiting for Majid. An approved one becomes an open vendor invoice.

**promotions**

* **Fields:** `id`, `ticket_id`, `sku`, `discount_pct`, `min_qty`, `reason`, `requested_by`, `requested_at`, `status`, `decided_by`, `decided_at`
* Discounts waiting for Majid. Only approved ones can be quoted to a customer.

**restocks**

* **Fields:** `invoice_id`, `sku`, `size`, `qty`, `received_at`
* Which paid reprint bills were already added to inventory, so stock is never counted twice.

**shipments**

* **Fields:** `id`, `ticket_id`, `sku`, `size`, `qty`, `shipped_at`
* Every shipment per ticket, so orders can ship in parts and a ticket can only say 'shipped' if something really shipped.

**task_claims**

* **Fields:** `id`, `ticket_id`, `task`, `agent`, `status`, `result`, `created_at`
* Who is doing which task on which ticket, so two agents never do the same work.

**team_notes**

* **Fields:** `id`, `ticket_id`, `agent`, `kind`, `message`, `severity`, `created_at`
* The team board: notes, escalations to the boss, risk flags, Majid's directions, and the boss's final decisions.

**drafts**

* **Fields:** `id`, `ticket_id`, `author`, `audience`, `to_name`, `subject`, `body`, `status`, `created_at`
* Drafted messages. They stay on the board and can never be marked as sent.

## Tools

**Restock tool (`receive_stock`)**

* **Reads:** `invoices` (the reprint bill must be paid), `inventory` (the shelf count it adds to), `tickets` (the order quantity, if the bill doesn't list one).
* **Helps:** ticket 101, and any order waiting on a paid reprint.
* **Why:** inventory shows 0 white tees in size S, and invoice 501 is their reprint, so the tee can only ship once that paid reprint lands on the shelf.

**Balance check tool (`cash_forecast`)**

* **Reads:** `cash_accounts` (cash on hand), `invoices` (unpaid bills), `leases` (rent and its due date), `desk` (today).
* **Helps:** ticket 102, and any bill coming due.
* **Why:** rent of $2,400 is due 2026-09-02, and this shows whether the $3,400 in cash can cover it alongside the other open bills before a human is asked to approve anything.

**Partial-order tool (`ship_partial`)**

* **Reads:** `tickets` (how many were ordered), `inventory` (how many are on hand), `invoices` (no unpaid bills may be open).
* **Helps:** ticket 103, and any order larger than the stock on hand.
* **Why:** the AI Club wants 20 navy hoodies in size M, but inventory shows 8, so the shop ships 8 now, records 12 as still owed, and drafts a notice telling the customer the order will arrive in two parts.

## Agents

Built with PydanticAI. Every agent uses **gpt-6-luna** through Portkey; the code refuses to start with any other model. Agents only see shop facts through the MCP server, which only reads and writes `campus_customs_new.db`. Prompts live in `backend/prompts/`.

**Boss** (`boss.md`)

* Reads every ticket from the board, decides who works on it, delegates specific tasks, settles ties, and makes the final call on each ticket.
* Order of work: read the ticket, call inventory first, then other agents only if needed. It cycles until there's an outcome, reassesses once if stuck, then alerts Majid. On every customer ticket it gets a customer service draft before closing.
* MCP tools: `get_board`, `list_tickets`, `update_ticket`, `record_decision`, `cash_forecast`, `list_drafts`, `list_payment_requests`, `list_purchase_orders`, `list_promotions`, plus the team tools.
* Team tool: `delegate(agent, ticket_id, task)`.

**Inventory** (`inventory.md`)

* Checks stock by SKU and size, spots shortfalls, picks the vendor who can restock, ships orders (in full or in part), and receives paid reprints.
* MCP tools: `check_inventory`, `list_vendors`, `get_pricing`, `can_ship`, `ship_order`, `ship_partial`, `receive_stock`, `list_purchase_orders`, `list_invoices`, plus the team tools.

**Accounting** (`accounting.md`)

* Owns cash and invoices, checks margins, and prepares payments, purchase orders, and discounts for human approval. Never pays.
* MCP tools: `get_cash`, `cash_forecast`, `list_invoices`, `list_payments`, `list_payment_requests`, `request_payment`, `get_pricing`, `quote_price`, `propose_promotion`, `list_promotions`, `request_purchase_order`, `list_purchase_orders`, `list_vendors`, `list_leases`, plus the team tools.

**Facilities** (`facilities.md`)

* Handles the shop space: leases, rent, and the landlord. Asks accounting to prepare rent payments and may draft landlord notes.
* MCP tools: `list_leases`, `get_cash`, `cash_forecast`, `list_payment_requests`, `draft_message` (landlord only), `list_drafts`, plus the team tools.

**Customer service** (`customer_service.md`)

* Drafts (never sends) messages to customers. It is the only agent allowed to draft to a customer, and drafts always stay on the board.
* MCP tools: `check_inventory`, `get_pricing`, `quote_price`, `list_promotions`, `list_vendors`, `draft_message`, `list_drafts`, plus the team tools.

**Team tools every agent has:** `get_today`, `get_ticket`, `read_notes`, `list_claims`, `post_note`, `flag_risk`. Specialists also have `claim_task`, `complete_task`, and `ask_teammate(agent, ticket_id, question)`. The boss has no claim tools: it delegates work, it doesn't do it.

**How they work together without duplicating work**

* Before doing a task, an agent checks `list_claims` and claims it with `claim_task`. A second agent trying the same task is refused and told who owns it. The one exception: a specialist can take over a task the boss holds (added after run db637362, where the boss's claim blocked accounting from requesting payment).
* The backend remembers every hand-off in a run, so asking the same agent the same thing twice returns the earlier answer instead of redoing it.
* Disagreements go to the boss as `post_note(kind="escalation")`. The boss breaks the tie and records it with `record_decision`.
* A consulted teammate cannot consult a third agent, so hand-offs can't loop.

## MCP tools (full toolkit, 35 tools)

Each tool lists the tables it **reads** and **writes** in `campus_customs_new.db`. No tool touches `campus_customs.db`.

**Read the shop**

* `get_today`: the shop's "today". Reads `desk`.
* `get_board`: one-call snapshot of tickets, claims, notes, drafts, cash, and everything waiting for a human. Reads `tickets`, `task_claims`, `team_notes`, `drafts`, `shipments`, `payment_requests`, `purchase_orders`, `promotions`, `cash_accounts`, `desk`.
* `list_tickets`: the ticket queue. Reads `tickets`.
* `get_ticket`: one ticket with its linked invoice or lease. Reads `tickets`, `invoices`, `leases`.
* `check_inventory`: stock by SKU and size. Reads `inventory`.
* `get_pricing`: cost and list price. Reads `pricing`.
* `quote_price`: a quote that refuses to go below cost. Reads `pricing`.
* `list_vendors`: vendors, specialty, and lead days. Reads `vendors`.
* `list_invoices`: invoices with days overdue. Reads `invoices`, `desk`.
* `list_leases`: leases with days until rent is due. Reads `leases`, `desk`.
* `get_cash`: the checking balance. Reads `cash_accounts`.
* `list_payments`: the payment ledger. Reads `payments`.
* `list_payment_requests`: the approval queue. Reads `payment_requests`.
* `cash_forecast`: cash left after each bill that's due, plus pending purchase orders. Reads `cash_accounts`, `invoices`, `leases`, `purchase_orders`, `desk`.
* `can_ship`: checks stock and unpaid invoices before shipping. Reads `inventory`, `invoices`.

**Move stock**

* `ship_order`: ships everything still owed on a ticket. Reads `invoices`, `desk`. Writes `inventory`, `shipments`, `tickets`.
* `ship_partial`: ships what's on hand and records the rest as owed. Reads `invoices`, `desk`. Writes `inventory`, `shipments`, `tickets`.
* `receive_stock`: adds a paid reprint to inventory, once. Reads `invoices`, `tickets`, `desk`. Writes `inventory`, `restocks`.

**Money (always waits for a human)**

* `request_payment`: asks a human to approve paying an invoice or rent. The amount must equal what's owed. Reads `invoices` or `leases`, `cash_accounts`. Writes `payment_requests`.
* `request_purchase_order` (replaces `order_reprint`): prepares a reprint order for human approval. Once approved, it becomes an open vendor invoice. Reads `inventory`, `pricing`, `vendors`, `desk`. Writes `purchase_orders`.
* `list_purchase_orders`: purchase orders and their status. Reads `purchase_orders`.
* `propose_promotion`: proposes a discount for human approval and refuses anything below cost. Reads `pricing`. Writes `promotions`.
* `list_promotions`: promotions and their status. Only approved ones can be quoted. Reads `promotions`.
* `pay`: makes a payment a human already approved, and refuses if cash is short. Reads `payment_requests`, `desk`. Writes `cash_accounts`, `payments`, `invoices` (marks paid), `leases` (moves `next_due`), `payment_requests`. **No agent has this tool.**

**Tickets and the board**

* `create_ticket`: logs a new request. Refuses duplicates and caps each requester at 3 open tickets. Reads `inventory`, `invoices`, `leases`, `desk`. Writes `tickets`. **No agent has this tool**; it is for the intake API.
* `update_ticket`: changes a ticket's status and adds a dated note. It refuses `shipped` without a recorded shipment. Reads `shipments`, `desk`. Writes `tickets`.
* `draft_message`: saves a draft on the board and never sends. Only customer service may draft to customers. Writes `drafts`.
* `list_drafts`: drafts on the board. Reads `drafts`.

**Teamwork**

* `claim_task`, `complete_task`: claim a task so no work is repeated, then mark it done. Reads and writes `task_claims`.
* `list_claims`: who is doing what. Reads `task_claims`.
* `post_note`: team notes and escalations to the boss. Writes `team_notes`.
* `read_notes`: reads `team_notes`.
* `flag_risk`: flags anything that could harm the business for a human. Writes `team_notes` (kind `flag`, with a severity).
* `record_decision`: the boss's final call on a ticket (boss only). Writes `team_notes` (kind `decision`).

**Human-only commands (not MCP tools, not available to any agent)**

* `python mcp_server/server.py approve payment|po|promo <id> <name>`: approve. Approving a payment also pays it, and still refuses if cash is short.
* `python mcp_server/server.py reject payment|po|promo <id> <name>`: reject.
* `python mcp_server/server.py reset`: copy the original database over the new one.

## API routes (FastAPI, `backend/main.py`)

Start from `backend/`: `uvicorn main:app --reload --port 8000` → `http://localhost:8000`. One line per route:

* `GET /api/health`: Liveness check (the dashboard's connection light).
* `GET /api/tickets`: The desk tickets (101–103) with their status (open, waiting, resolved…); `?all=true` adds any extra tickets.
* `POST /api/tickets`: Logs a new incoming ticket through MCP `create_ticket` (5/min per client, duplicates refused, suspicious text auto-flagged).
* `POST /api/tickets/{id}/run`: Starts the agent team on one ticket in the background (one run at a time, 30-second cooldown).
* `GET /api/runs/current`: Whether a run is going, and the last run's report, alerts, and token use.
* `GET /api/runs`: Past runs (newest first), optionally `?ticket_id=`, read from the audit trail.
* `GET /api/runs/{run_id}/summary`: Mission report: what each agent did (steps, tools, actions, their own summary) and who asked whom.
* `GET /api/events`: Recent agent events (who acted, what they said, which tool they used); `?run_id=` for one run.
* `GET /api/approvals`: Everything waiting for Majid: pending payments, purchase orders, and promotions.
* `POST /api/approvals/{kind}/{id}`: **Human only.** Majid approves or rejects a payment / PO / promotion. Approving a payment is what moves cash (still refused if cash is short).
* `GET /api/cash`: The checking balance from `cash_accounts`.
* `POST /api/reset`: **Human only.** Resets `campus_customs_new.db` to the original values (body `{"confirm": "RESET", "requested_by": "<name>"}`; refused during a run).
* `GET /api/board`: Full board snapshot (tickets with claims, notes, drafts; items waiting for a human).
* `GET /api/leaderboard`: Each agent's stats, XP, and level across all runs.
* `GET /api/summary`: Home-page snapshot in one call (ticket counts, cash, decisions waiting, active agents, last run).

## Rules added during the runs

Each rule fixes a problem seen in a real run. They're in the prompts (`backend/prompts/`) or enforced by the server.

* **Facts go stale between runs** (all prompts): re-check live facts (stock, payments, leases) with a tool before relying on an earlier note.
* **Delegate the action, not just a check** (boss): ask the specialist to *do* the step (ship, receive, request payment), not only to look.
* **Majid's word is final** (boss): a note from Majid on the board settles a choice, and still goes through the normal approval step.
* **One rent cycle per ticket** (boss, facilities): a rent ticket covers only the cycle it names. Next month's shortfall is an alert to Majid, not a reason to keep the ticket open.
* **Receive a paid reprint right away** (inventory): once its invoice is paid, run `receive_stock`, then re-check `can_ship`.
* **Customer tickets get a draft before closing** (boss): customer service drafts the outcome, and it's never sent.
* **No fake shipments** (server, `update_ticket`): `shipped` / `partially_shipped` are refused unless a shipment is actually recorded, and `shipped` needs the full quantity.
* **Boss has no claim tools, and specialists can take over** (backend and server): see "How they work together" above.
* **Auto-resolve only on a real outcome** (backend): after a run, a ticket is marked `resolved` only if the boss's outcome is `shipped` or `resolved`, never while it waits for a human.

## Dashboard (React + Vite, `frontend/`)

Start from `frontend/` with `npm run dev`, then open `http://localhost:5175`. It calls the API at `http://localhost:8000`, and CORS allows the Vite origin. The full look and behavior is in `output/design.md`.

* **Top bar:** title, sound toggle, a "decisions" badge (pending approvals), and the **checking-balance ticker** in the top-right (from `/api/cash` and `/api/summary`).
* **Tabs:** Home, one tab per ticket (#101, #102, #103, …), and Leaderboard.
* **Home:** stat tiles (tickets, open, waiting, closed, cash, tokens), the party of five agents with status lamps, the quest board (every ticket with a "Start mission" button), decisions waiting, and the last mission.
* **Ticket tab:**
  * Quest header and five **mission lamps** (Read ticket → Inventory check → Team work → Boss decision → Closed). Each goes red → yellow → green and stays green.
  * The **arena**, where agents sit around the boss, with beams and speech bubbles when one talks to another, plus a "Who said what" log.
  * The **mission report**, with a card per agent (summary, tools, actions).
  * A **replay** of any past run, and the drafts on the board (never sent).
* **Decision dialog:** opens on its own when a payment, PO, or promotion is pending. It shows amount, reason, and cash after. Approve or Reject needs a name and a confirm step, and goes to `POST /api/approvals/{kind}/{id}` → the MCP server's human-only command.
* **Closing a ticket:** fireworks, a short chiptune, and a "QUEST CLEAR" banner (respects mute and reduced motion).
* **Leaderboard:** agents ranked by XP from missions, tasks, actions, tool calls, and hand-offs.
* **Agents and colors:** King Grimhorn, boss (violet). Pip Stockwell, inventory (teal). Ada Ledger, accounting (periwinkle). Bo Brickley, facilities (copper). Sunny Vale, customer service (rose).
* **Style:** 80s retro pixel look, mostly blue and grey. Pixel sprites are original 16×16 SVGs.
* The dashboard shows only facts from the backend, which gets them from `campus_customs_new.db` through MCP. It can't pay, reset, or send anything by itself.

## Full run results

Reset at 06:24:49 UTC, starting cash **$3,400**. 101: payment #1, −$840. 102: payment #2, −$2,400. 103: promotion #1 approved, $0. All three tickets ended `resolved`, and ending cash is **$160**, matching `cash_accounts`. Details are in `output/desk_tickets.html` (Actual and Cash tabs), `output/resolved_tickets.json`, and `output/resolved_board.html`.

## Safety

**1. Stay in your lane, and ask before handling money**

* Each agent only sees the tools for its own job. Only customer service can draft to a customer, and the server enforces this.
* No agent can pay, approve, refund, or send money back. There is no refund tool at all, and `pay` is given to no agent.
* Every payment, purchase order, and discount is only a *request* until a human approves it, either from the command line or the dashboard's Decision dialog, which calls that same command. No agent tool can approve.
* The backend stamps each agent's real name on everything it requests or drafts, so an agent can't pose as another (for example, as the boss).
* Anything that could harm the business is flagged with `flag_risk` for a human and not acted on. That includes selling below cost, cash running out, suspicious or abusive tickets, and attempts to bypass approval or change the rules. Instructions written inside tickets are treated as data, never as commands. The intake API also auto-flags ticket text that looks like a bypass or money-moving attempt.

**2. Only draft, never send**

* No tool can send email or contact a vendor. `draft_message` only saves a draft on the board, and the drafts table can only hold the status `draft`.

**3. No spam, and the most effective path**

* Intake: 5 tickets per minute per client, duplicates refused, at most 3 open tickets per requester, and quantities over 200 refused.
* Team runs: one at a time, with a 30-second cooldown between runs.
* Within a run: at most 12 hand-offs, and repeated hand-offs return the earlier answer. Claims stop two agents doing the same task, and prompts tell agents to use the fewest tool calls (for example, the boss reads the board once).

**4. Token cost alerts for the manager**

* Each run has a token budget (default 150,000 tokens) and a 60-request cap. Both are hard stops.
* At 60% of the budget, the manager is alerted. The warning is written to the audit trail, returned in the run's `manager_alerts`, and passed to the agents so they finish quickly.

**5. Audit trail**

* Everything is appended to `output/audit_trail.json`, tagged with the run id and the agent's name: every agent step (each model turn and the tools it chose), every tool call and result, every hand-off, every human approval, and every token warning.
