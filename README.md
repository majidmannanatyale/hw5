# Campus Customs: Multi-Agent Desk (HW5)

An AI team that runs the Campus Customs shop desk. Five PydanticAI agents (boss, inventory, accounting, facilities, customer service) on **gpt-6-luna** work the open tickets through a **FastMCP** server, a **FastAPI** backend serves their runs, and a **React + Vite** "Command Deck" shows them live. Every payment, purchase order and promotion waits for a human (Majid) to approve it.

```
hw5/
├─ AI_prompts.md          # prompts used to build this, per problem
├─ requirements.txt       # Python dependencies
├─ .env.example           # copy to .env and fill in
├─ .gitignore
├─ .mcp.json              # MCP server config (used by Claude Code and the backend)
├─ README.md
├─ data/
│  ├─ campus_customs.db       # ORIGINAL database, read-only, never modified
│  └─ campus_customs_new.db   # WORKING copy, the only database the MCP server touches
├─ mcp_server/
│  ├─ server.py           # FastMCP server: 35 tools + human-only approve / reject / reset commands
│  ├─ audit_log.py        # safe, append-only audit writer (extra helper)
│  └─ README.md
├─ backend/
│  ├─ main.py             # FastAPI routes
│  ├─ models.py           # Pydantic data types
│  ├─ agents.py           # the agent team, MCP toolsets, budgets (extra helper)
│  └─ prompts/            # boss.md, inventory.md, accounting.md, facilities.md, customer_service.md
├─ frontend/              # React + Vite + TypeScript dashboard
└─ output/                # harness.md, mcp_smoke.json, desk_tickets.html, design.md,
                          # resolved_tickets.json, resolved_board.html, audit_trail.json, github_url.txt
```

## Shop rules (enforced in every prompt and in the server)

* "Today" is `desk.date_today`. Vendor lead times come from `vendors.lead_days`.
* New product ships only when there are no open unpaid invoices.
* **Human approval is required for every payment.** No agent has the `pay` tool.
* The pay step refuses if cash is short: no negative balances. Cash only goes out.
* Agents only draft: they never email customers or contact real vendors.

## Prerequisites

* **Python 3.12** (x64) and **Node.js 18+**
* A **Portkey API key** with access to `gpt-6-luna` (only needed to run the agents)

## 1. Set up

```bash
git clone https://github.com/majidmannanatyale/hw5.git
cd hw5

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env        # then put your PORTKEY_API_KEY in .env
```

Tip: keep the virtual environment outside OneDrive or Dropbox, or pause syncing while installing.

## 2. Copy the database

The original `data/campus_customs.db` is never modified. The MCP server reads and writes **only** the working copy, `data/campus_customs_new.db`. Both are included in the repo. To create the working copy yourself from the original:

```bash
# from hw5/
python mcp_server/server.py reset
```

This copies `campus_customs.db` over `campus_customs_new.db` (same as `cp data/campus_customs.db data/campus_customs_new.db`). The server adds its helper tables (payment requests, shipments, notes, drafts, and so on) to the working copy the first time it runs. They are never added to the original.

## 3. Start the MCP server

The server talks over stdio, so a client starts it. Its config is in `.mcp.json`:

```json
{"mcpServers": {"campus-customs": {"type": "stdio",
  "command": "C:\\Users\\majma\\.venvs\\hw5\\Scripts\\python.exe",
  "args": ["mcp_server/server.py"], "env": {"PYTHONUTF8": "1"}}}}
```

**Change `command` to your own Python** (for example `.venv\\Scripts\\python.exe`, or `.venv/bin/python` on macOS / Linux). Then:

* **Claude Code** (opened in `hw5/`) picks up `.mcp.json` and can call the 35 tools directly.
* **The backend** reads the same `.mcp.json` and starts the server for each team run. You don't need to start it separately.
* To run it by hand (it waits for a client on stdin/stdout):

  ```bash
  # from hw5/
  python mcp_server/server.py
  ```

Human-only commands (no agent can run these):

```bash
python mcp_server/server.py approve payment 1 Majid    # also pays it; refused if cash is short
python mcp_server/server.py reject  promo 1 Majid
python mcp_server/server.py reset                       # restore the working database
```

## 4. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API runs at `http://localhost:8000` (health check: `GET /api/health`). CORS allows the Vite dev origin. All routes are listed in `output/harness.md` under "API routes".

## 5. Run the React board

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5175**. Pick a ticket on Home and press **Start mission**. When a payment, purchase order or promotion needs approval, the Decision dialog opens. Approve or reject it there.

## 6. Reset the database before the final 3-ticket run

Before running tickets 101, 102 and 103 for real, restore the working database to the original values. Use either option:

```bash
# Option A: command line, from hw5/
python mcp_server/server.py reset

# Option B: API, with the backend running (refused while a run is in progress)
curl -X POST http://localhost:8000/api/reset \
     -H "Content-Type: application/json" \
     -d '{"confirm": "RESET", "requested_by": "Majid"}'
```

After the reset, checking is **$3,400.00**. Then run 101 → 102 → 103 from the board, approving each decision as it comes up. In our full run the ending balance was **$160.00** (−$840 invoice 501, −$2,400 rent, $0 for the approved 20% promotion), matching `cash_accounts`. The reset is logged in `output/audit_trail.json`. The audit trail is append-only and is never cleared.

## Outputs

| File | What it is |
|---|---|
| `output/harness.md` | Tables, tools, agents, MCP tools, API routes, rules, dashboard, safety |
| `output/mcp_smoke.json` | MCP tool tests checked against the database |
| `output/desk_tickets.html` | Expected and actual for each ticket, Cash, Reflection (double-click to open) |
| `output/design.md` | Dashboard design reference |
| `output/resolved_tickets.json` | Final status, outcome, agent contributions, approvals |
| `output/resolved_board.html` | Screenshots of each resolved ticket (double-click to enlarge) |
| `output/audit_trail.json` | Every agent step, tool call, hand-off and human approval |
| `output/github_url.txt` | This repository's URL |
