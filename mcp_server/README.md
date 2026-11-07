# Campus Customs MCP Server

## Why there is an MCP server

The agent team (boss, inventory, accounting, facilities, customer service) never touches the database directly. Instead, every agent works through this server's tools. That lets the shop rules live in one place, in code, rather than relying on each agent's prompt:

* An agent can only do what a tool allows. For example, no tool can pay without human approval, and no tool can send an email.
* Every tool checks the rules before it changes anything, and refuses with a plain reason if a rule would be broken.
* Every change is logged to `output/audit_trail.json`, so each step the team takes can be traced.

It is built with FastMCP, so any MCP client (Claude Code, the FastAPI backend's agents) can connect to the same tools.

## The database file

* **`data/campus_customs_new.db` is the only database the tools read or write.** It is the shop's working copy, and every fact the agents use comes from it.
* **`data/campus_customs.db` is the original and is never changed.** No tool opens it. If the server is ever pointed at it, the server refuses. The only thing that reads it is the human-run `reset` command, which copies it over the new DB before a full ticket run.
* The server adds helper tables to the new DB (never to the original):
  * `payment_requests`, `purchase_orders`, `promotions`: the human-approval queues.
  * `restocks`: which paid reprint bills have already been added to inventory, so stock is never added twice.
  * `shipments`: each shipment for a ticket, so an order can ship in parts.
  * `drafts`: drafted messages. They stay on the board and can never be marked as sent.
  * `task_claims`, `team_notes`: who is doing what, team notes, escalations, risk flags, and the boss's decisions.

## The three new tools

**Restock tool: `receive_stock(invoice_id, qty?)`**

* Adds reprinted items to inventory once their reprint bill is **paid**.
* It reads the item and size from the bill (for example "Rush reprint CC-TEE-WHITE S"). The quantity comes from the bill if it lists one, otherwise from the `qty` you pass, otherwise from the tickets linked to that bill.
* It refuses if the bill is unpaid, isn't a reprint, or was already received.
* **For ticket 101:** inventory shows 0 white tees in size S. After invoice 501 is approved and paid, this tool puts the reprinted tee on the shelf so the order can ship.

**Balance check tool: `cash_forecast(within_days=30)`**

* Lists every unpaid bill (overdue invoices, open invoices, and rent coming due) in due-date order, with the cash left after each one.
* It flags the first bill the shop could not afford.
* It only reads. It pays nothing, and every payment still needs human approval.
* **For ticket 102:** it shows whether the $3,400 in cash covers the $2,400 rent alongside the $840 overdue invoice, before anyone is asked to approve.

**Partial-order tool: `ship_partial(ticket_id)`**

* Ships what is on hand now, records the rest as still owed, and marks the ticket `partially_shipped`.
* It returns a **draft** notice telling the customer the order will arrive in two parts. The draft is never sent.
* It follows the same rule as a full shipment: nothing ships while any bill is open and unpaid.
* Once the rest is restocked, `ship_order` ships only what is still owed.
* **For ticket 103:** the AI Club ordered 20 navy hoodies in size M, and inventory shows 8. This ships 8 now and records 12 as owed.
* A coupon or discount option will be added later.

## Shop rules enforced in code

* "Today" is `desk.date_today`, never the system clock.
* Lead times come from `vendors.lead_days`.
* `ship_order` and `ship_partial` refuse while **any** invoice is open and unpaid.
* **Human approval is required for every payment**, and also for every purchase order and promotion. Agents can only request them. Approving is a human-only command and is **not** an MCP tool, so no agent can approve anything.
* `pay` refuses unless the request is human-approved, and refuses if cash is insufficient. Balances can never go negative. Approving a payment runs the same check.
* The payment amount must equal the amount owed (the invoice amount or the monthly rent).
* Discounts can never go below unit cost.
* Cash only goes out. There is no deposit, revenue, or refund tool.
* There is no email or vendor-contact tool. `draft_message` saves drafts on the board that are never sent, and only `customer_service` may draft to a customer.
* Anti-spam: `create_ticket` refuses exact duplicates of an open ticket, caps each requester at 3 open tickets, and refuses quantities over 200.
* Only the boss can record a final decision. A claimed task can't be claimed by a second agent.
* Every write is logged to `output/audit_trail.json`.

## All tools (35)

| Tool | What it does | Agents that get it |
|---|---|---|
| `get_today` | The shop's "today" from the desk | all |
| `get_board` | One-call snapshot: tickets, claims, notes, drafts, cash, items waiting for a human | boss |
| `list_tickets` | The ticket queue | boss |
| `get_ticket` | One ticket with its linked invoice or lease | all |
| `check_inventory` | Stock by SKU and size | inventory, customer service |
| `get_pricing` | Unit cost and list price | inventory, accounting, customer service |
| `quote_price` | A price quote that refuses to go below cost | accounting, customer service |
| `list_vendors` | Vendors and their lead days | inventory, accounting, customer service |
| `list_invoices` | Invoices, with overdue days counted from desk today | inventory, accounting |
| `list_leases` | Leases, with days until rent is due | accounting, facilities |
| `get_cash` | Cash balance | accounting, facilities |
| `list_payments` | Payment ledger (with the human approver) | accounting |
| `list_payment_requests` | Payment approval queue | boss, accounting, facilities |
| `cash_forecast` | Cash left after each bill that's due, plus pending purchase orders | boss, accounting, facilities |
| `can_ship` | Checks stock and open invoices before shipping | inventory |
| `ship_order` | Ships everything still owed on a ticket | inventory |
| `ship_partial` | Ships what's on hand and records the rest as owed | inventory |
| `receive_stock` | Adds a paid reprint to inventory, once | inventory |
| `request_payment` | Asks a human to approve a payment | accounting |
| `request_purchase_order` | **New** (replaces `order_reprint`). Prepares a reprint order for human approval; approved, it becomes an open invoice | accounting |
| `list_purchase_orders` | **New.** Purchase orders and their status | boss, inventory, accounting |
| `propose_promotion` | **New.** Proposes a discount for human approval; refuses below cost | accounting |
| `list_promotions` | **New.** Promotions and their status; only approved ones may be quoted | boss, accounting, customer service |
| `update_ticket` | Changes a ticket's status and adds a dated note | boss |
| `create_ticket` | Logs a new request, with anti-spam checks | **none** (intake API only) |
| `draft_message` | Saves a draft on the board; never sent | facilities (landlord), customer service |
| `list_drafts` | **New.** Drafts on the board | boss, facilities, customer service |
| `claim_task` | **New.** Claims a task so no one else repeats it | all |
| `complete_task` | **New.** Marks a claimed task done, with a result | all |
| `list_claims` | **New.** Who is doing what | all |
| `post_note` | **New.** Team note, or an escalation for the boss | all |
| `read_notes` | **New.** Team notes, escalations, flags, decisions | all |
| `flag_risk` | **New.** Flags anything that could harm the business for a human | all |
| `record_decision` | **New.** The boss's final call on a ticket | boss (server refuses anyone else) |
| `pay` | Pays a human-approved request; refuses if cash is short | **none** |

## Commands (run from `hw5/mcp_server/`)

```bash
python server.py                                     # start the MCP server (stdio)
python server.py reset                               # human: reset the new DB from the original
python server.py approve payment|po|promo <id> <name>  # human: approve (a payment is also paid)
python server.py reject  payment|po|promo <id> <name>  # human: reject
```

Requires `fastmcp` (only for starting the server; `reset`, `approve` and `reject` work without it). The project's `.mcp.json` starts this server with the `~/.venvs/hw5` Python, so Claude Code and the backend use the same tools.
