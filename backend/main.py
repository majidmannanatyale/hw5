"""Campus Customs backend (FastAPI).

Start from hw5/backend/:
    uvicorn main:app --reload --port 8000

What it does:
  * GET  /api/tickets               the desk tickets (101-103) and their statuses
  * POST /api/tickets/{id}/run      run the agent team on one ticket (in the background)
  * GET  /api/runs/current          is a run going, and the last run's result
  * GET  /api/events                recent agent events: what agents said and which tools they used
  * GET  /api/approvals             payments / purchase orders / promotions waiting for Majid
  * POST /api/approvals/{kind}/{id} Majid approves or rejects one of them
  * GET  /api/cash                  the balance from cash_accounts

Every shop read and write goes through the campus-customs MCP server (.mcp.json),
which only touches data/campus_customs_new.db. Approval is a human action: it runs
the MCP server's own human-only approve/reject command; no agent can reach it.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from pydantic import BaseModel, Field

from agents import AUDIT_PATH, HW5_DIR, audit, mcp_config, run_team
from models import RunResponse, TicketIn

DESK_TICKETS = (101, 102, 103)
SERVER_PY = HW5_DIR / "mcp_server" / "server.py"

app = FastAPI(title="Campus Customs agent team")
app.add_middleware(CORSMiddleware,
                   # The Vite dev server (npm run dev) may call every route.
                   allow_origins=["http://localhost:5175", "http://127.0.0.1:5175",
                                  "http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["*"])


# --------------------------------------------------------------------------
# Windows: MCP talks to its server over a subprocess, which needs a Proactor
# event loop. `uvicorn --reload` uses a Selector loop, so MCP work runs on its
# own Proactor loop in a worker thread.
# --------------------------------------------------------------------------

def _run_coro(coro_factory):
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
        try:
            return loop.run_until_complete(coro_factory())
        finally:
            loop.close()
    return asyncio.run(coro_factory())


async def in_mcp_loop(coro_factory):
    return await asyncio.to_thread(_run_coro, coro_factory)


async def _mcp_call(tool: str, args: dict | None = None):
    async with Client(mcp_config()) as client:
        res = await client.call_tool(tool, args or {}, raise_on_error=False)
    out = res.structured_content
    return out["result"] if isinstance(out, dict) and set(out) == {"result"} else out


async def mcp_call(tool: str, args: dict | None = None):
    return await in_mcp_loop(lambda: _mcp_call(tool, args))


# --------------------------------------------------------------------------
# Anti-spam
# --------------------------------------------------------------------------

TICKETS_PER_MINUTE = 5
RUN_COOLDOWN_SECONDS = 30
_ticket_hits: dict[str, deque] = defaultdict(deque)

SUSPICIOUS = re.compile(
    r"ignore (all|previous|your) (rules|instructions)|system prompt|bypass|skip (the )?approval|"
    r"without approval|wire (the )?money|send (me )?(money|cash|a refund)|refund|api key|password|"
    r"drop table|delete from|;\s*--", re.IGNORECASE)


def rate_limited(ip: str) -> bool:
    now, hits = time.monotonic(), _ticket_hits[ip]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= TICKETS_PER_MINUTE:
        return True
    hits.append(now)
    return False


# --------------------------------------------------------------------------
# Team runs (one at a time, in the background)
# --------------------------------------------------------------------------

class RunState(BaseModel):
    running: bool = False
    run_id: str | None = None
    ticket_id: int | None = None
    started_at: str | None = None
    last: RunResponse | None = None


_state = RunState()
_last_run_at = 0.0


def _team_run_blocking(ticket_id: int, run_id: str) -> RunResponse:
    return _run_coro(lambda: run_team([ticket_id], run_id=run_id))


CLOSING_STATUSES = {"shipped", "resolved"}


async def _run_in_background(ticket_id: int, run_id: str) -> None:
    try:
        result = await asyncio.to_thread(_team_run_blocking, ticket_id, run_id)
        _state.last = result
        # When the boss's outcome is complete, mark the ticket resolved. A ticket that
        # waits for Majid (or is blocked) is never marked resolved.
        for o in (result.report.outcomes if result.report else []):
            if o.status in CLOSING_STATUSES:
                await mcp_call("update_ticket", {"ticket_id": o.ticket_id, "status": "resolved",
                                                 "note": f"Resolved by run {run_id}: {o.decision}"})
                audit("ticket_resolved", run_id=run_id, ticket_id=o.ticket_id, from_status=o.status)
    except Exception as exc:  # keep the server alive; details go to the audit trail
        audit("run_error", run_id=run_id, error_type=type(exc).__name__, detail=str(exc)[:300])
    finally:
        _state.running = False


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/tickets")
async def tickets(all: bool = False):
    """The desk tickets (101-103) with their statuses. ?all=true includes test tickets."""
    rows = await mcp_call("list_tickets")
    return rows if all else [t for t in rows if t["id"] in DESK_TICKETS]


@app.post("/api/tickets")
async def create_ticket(ticket: TicketIn, request: Request):
    ip = request.client.host if request.client else "unknown"
    if rate_limited(ip):
        audit("spam_blocked", reason="rate_limit", ip=ip)
        raise HTTPException(429, "Too many tickets. Please wait a minute.")
    result = await mcp_call("create_ticket", ticket.model_dump(exclude_none=True))
    if not result.get("ok"):
        raise HTTPException(409, result.get("reason", "Ticket refused."))
    if SUSPICIOUS.search(f"{ticket.subject} {ticket.notes}"):
        await mcp_call("flag_risk", {"ticket_id": result["ticket"]["id"], "agent": "intake",
                                     "risk": "Ticket text looks like an attempt to bypass rules or move money.",
                                     "severity": "high"})
        audit("suspicious_ticket", ticket_id=result["ticket"]["id"])
    return result


@app.post("/api/tickets/{ticket_id}/run")
async def run_ticket(ticket_id: int):
    """Start the agent team on one ticket. Poll /api/runs/current and /api/events."""
    global _last_run_at
    if _state.running:
        raise HTTPException(409, f"A run is already going on ticket {_state.ticket_id}.")
    wait = RUN_COOLDOWN_SECONDS - (time.monotonic() - _last_run_at)
    if _last_run_at and wait > 0:
        raise HTTPException(429, f"Please wait {int(wait)}s before the next run.")
    ticket = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}.")
    run_id = uuid.uuid4().hex[:8]
    _last_run_at = time.monotonic()
    _state.running, _state.run_id, _state.ticket_id = True, run_id, ticket_id
    _state.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    asyncio.create_task(_run_in_background(ticket_id, run_id))
    return {"run_id": run_id, "ticket_id": ticket_id, "status": "started"}


class ResetRequest(BaseModel):
    confirm: str
    requested_by: str = Field(min_length=2, max_length=40)


@app.post("/api/reset")
async def reset_database(req: ResetRequest):
    """Human only: reset campus_customs_new.db to the original values. Runs the MCP server's own
    reset command (the original campus_customs.db is only read, never written). Refused during a run."""
    if req.confirm != "RESET":
        raise HTTPException(400, 'Type "RESET" in confirm to reset the working database.')
    if _state.running:
        raise HTTPException(409, "A team run is in progress. Wait for it to finish.")
    proc = await asyncio.to_thread(subprocess.run, [sys.executable, str(SERVER_PY), "reset"],
                                   cwd=str(SERVER_PY.parent), capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        audit("reset_error", requested_by=req.requested_by)
        raise HTTPException(500, "The reset command failed.")
    _state.last = None
    audit("reset_via_ui", requested_by=req.requested_by.strip())
    return {"ok": True, "message": proc.stdout.strip(), "cash": await cash()}


@app.get("/api/runs/current", response_model=RunState)
async def current_run():
    return _state


@app.get("/api/board")
async def board():
    return await mcp_call("get_board")


@app.get("/api/cash")
async def cash():
    """The balance from cash_accounts."""
    accounts = await mcp_call("get_cash")
    return {"accounts": accounts, "total": round(sum(a["balance"] for a in accounts), 2)}


# ---- Agent events --------------------------------------------------------

def _said(e: dict) -> str:
    """What the agent said or decided at this step, in plain words."""
    ev = e.get("event")
    if ev == "agent_step":
        return e.get("text") or ""
    if ev in ("delegate", "ask_teammate"):
        return f"Asked {e.get('to')}: {e.get('task', '')}"
    if ev == "agent_end":
        if e.get("said"):
            return e["said"]
        try:
            out = json.loads(e.get("output", "{}"))
        except (json.JSONDecodeError, TypeError):  # older, truncated entries
            raw = str(e.get("output", ""))
            found = re.findall(r'"(?:decision|summary)": "((?:[^"\\]|\\.)*)"', raw)
            return " ".join(found) or raw
        if "summary" in out:
            return out["summary"]
        return " ".join(o.get("decision", "") for o in out.get("outcomes", [])) or ""
    if ev == "token_budget_warning":
        return f"Token use at {e.get('total_tokens'):,} of {e.get('budget'):,}."
    return ""


@app.get("/api/events")
async def events(limit: int = 80, run_id: str | None = None):
    """Recent agent events: who acted, what they said, and which tools they used."""
    try:
        log = json.loads(AUDIT_PATH.read_text("utf-8")) if AUDIT_PATH.exists() else []
    except (json.JSONDecodeError, OSError):
        log = []  # file mid-write; the next poll will catch up
    if run_id:
        log = [e for e in log if e.get("run_id") == run_id]
    out = []
    for e in log[-max(1, min(limit, 500)):]:
        src = e.get("source", "")
        out.append({
            "ts": e.get("ts"), "run_id": e.get("run_id"), "event": e.get("event"),
            "agent": src.split(":", 1)[1] if src.startswith("agent:") else src,
            "tool": e.get("tool") or (", ".join(e["tool_calls"]) if e.get("tool_calls") else None),
            "said": _said(e),
            "to": e.get("to"),
            "detail": e.get("args") or e.get("result") or e.get("reason") or e.get("error") or "",
        })
    return list(reversed(out))


# ---- Human approvals -----------------------------------------------------

class Decision(BaseModel):
    approve: bool
    approver: str = Field(min_length=2, max_length=40)


@app.get("/api/approvals")
async def approvals():
    """Everything waiting for Majid: payments, purchase orders, and promotions."""
    async def fetch():
        async with Client(mcp_config()) as c:
            async def call(tool):
                r = await c.call_tool(tool, {"status": "pending"}, raise_on_error=False)
                o = r.structured_content
                return o["result"] if isinstance(o, dict) and set(o) == {"result"} else o
            return {"payments": await call("list_payment_requests"),
                    "purchase_orders": await call("list_purchase_orders"),
                    "promotions": await call("list_promotions")}
    return await in_mcp_loop(fetch)


@app.post("/api/approvals/{kind}/{item_id}")
async def decide(kind: Literal["payment", "po", "promo"], item_id: int, d: Decision):
    """Majid's decision. Runs the MCP server's human-only command, so the same
    rules apply (approving a payment pays it, and still refuses if cash is short)."""
    verb = "approve" if d.approve else "reject"
    proc = await asyncio.to_thread(
        subprocess.run, [sys.executable, str(SERVER_PY), verb, kind, str(item_id), d.approver.strip()],
        cwd=str(SERVER_PY.parent), capture_output=True, text=True, timeout=60)
    try:
        result: dict[str, Any] = json.loads(proc.stdout)
    except json.JSONDecodeError:
        audit("approval_error", kind=kind, item_id=item_id)
        raise HTTPException(500, "The approval command failed.")
    if not result.get("ok"):
        raise HTTPException(409, result.get("reason", "Not pending."))
    audit("human_decision_via_ui", kind=kind, item_id=item_id, decision=verb, approver=d.approver.strip())
    return result


# --------------------------------------------------------------------------
# Mission history, reports, leaderboard, and the home snapshot.
# All of it is read from the append-only audit trail (output/audit_trail.json).
# --------------------------------------------------------------------------

AGENTS = ("boss", "inventory", "accounting", "facilities", "customer_service")
# Tools that change something in the shop (counted as "actions" when they succeed).
ACTION_TOOLS = {"ship_order", "ship_partial", "receive_stock", "request_payment", "request_purchase_order",
                "propose_promotion", "update_ticket", "draft_message", "record_decision", "flag_risk"}
APPROVAL_TOOLS = {"request_payment", "request_purchase_order", "propose_promotion"}
OPEN_SET = {"open", "in_progress"}
WAITING_SET = {"waiting_for_human", "blocked", "partially_shipped"}
CLOSED_SET = {"shipped", "resolved", "rejected"}


def load_audit() -> list[dict]:
    try:
        log = json.loads(AUDIT_PATH.read_text("utf-8")) if AUDIT_PATH.exists() else []
        return log if isinstance(log, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _agent_of(e: dict) -> str | None:
    src = e.get("source", "")
    return src.split(":", 1)[1] if src.startswith("agent:") else None


def _ok(e: dict) -> bool:
    return '"ok": true' in str(e.get("result", ""))


def _outcomes_from(e: dict) -> list[dict]:
    """The boss's ticket outcomes from its agent_end entry (handles older, truncated entries)."""
    raw = str(e.get("output", ""))
    try:
        return json.loads(raw).get("outcomes", [])
    except (json.JSONDecodeError, AttributeError):
        return [{"ticket_id": int(t), "status": s, "decision": e.get("said", "")}
                for t, s in re.findall(r'"ticket_id": (\d+)[^{}]*?"status": "(\w+)"', raw)]


def _runs(log: list[dict]) -> dict[str, dict]:
    runs: dict[str, dict] = {}
    for e in log:
        rid = e.get("run_id")
        if not rid:
            continue
        r = runs.setdefault(rid, {"run_id": rid, "ticket_ids": [], "started_at": None, "ended_at": None,
                                  "usage": None, "error": None, "manager_alerts": [], "outcomes": [],
                                  "agents": []})
        ev = e.get("event")
        if ev == "run_start":
            r["started_at"] = e["ts"]
            r["ticket_ids"] = e.get("ticket_ids") or [int(x) for x in re.findall(r"#(\d+)", e.get("scope", ""))]
        elif ev == "run_end":
            r["ended_at"], r["usage"] = e["ts"], e.get("usage")
            r["error"], r["manager_alerts"] = e.get("error"), e.get("manager_alerts") or []
        elif ev == "agent_start" and (a := _agent_of(e)) and a not in r["agents"]:
            r["agents"].append(a)
        elif ev == "agent_end" and _agent_of(e) == "boss" and e.get("depth", 0) == 0:
            r["outcomes"] = _outcomes_from(e)
        elif ev == "ticket_resolved":
            r["resolved"] = True
    for r in runs.values():
        r["status"] = ("running" if _state.running and _state.run_id == r["run_id"]
                       else "done" if r["ended_at"] else "interrupted")
    return runs


@app.get("/api/runs")
async def list_runs(ticket_id: int | None = None):
    """Past missions (newest first), optionally only those for one ticket."""
    runs = [r for r in _runs(load_audit()).values() if r["started_at"]]
    if ticket_id is not None:
        runs = [r for r in runs if ticket_id in r["ticket_ids"]]
    return sorted(runs, key=lambda r: r["started_at"], reverse=True)


@app.get("/api/runs/{run_id}/summary")
async def run_summary(run_id: str):
    """Mission report: what each agent did, and the conversation between them."""
    log = [e for e in load_audit() if e.get("run_id") == run_id]
    if not log:
        raise HTTPException(404, f"No run {run_id}.")
    run = _runs(log)[run_id]
    agents: dict[str, dict] = {}
    conversation: list[dict] = []
    asked_by: dict[str, str] = {}
    for e in log:
        a, ev = _agent_of(e), e.get("event")
        if a:
            s = agents.setdefault(a, {"agent": a, "steps": 0, "tool_calls": 0, "tools": {}, "actions": [],
                                      "said": "", "finished": False})
            if ev == "agent_step":
                s["steps"] += 1
            elif ev == "tool_call":
                s["tool_calls"] += 1
                s["tools"][e["tool"]] = s["tools"].get(e["tool"], 0) + 1
            elif ev == "tool_result" and e.get("tool") in ACTION_TOOLS and _ok(e):
                s["actions"].append(e["tool"])
            elif ev == "agent_end":
                s["finished"], s["said"] = True, e.get("said") or _said(e)
                conversation.append({"ts": e["ts"], "from": a, "to": asked_by.get(a, "majid"),
                                     "kind": "reply", "text": s["said"]})
            if ev in ("delegate", "ask_teammate"):
                asked_by[e["to"]] = a
                conversation.append({"ts": e["ts"], "from": a, "to": e["to"], "kind": "ask",
                                     "text": e.get("task", "")})
    return {**run, "agents": [agents[a] for a in AGENTS if a in agents], "conversation": conversation}


@app.get("/api/leaderboard")
async def leaderboard():
    """Each agent's performance across every mission, with XP and level."""
    log = load_audit()
    runs = _runs(log)
    closed_runs = {rid for rid, r in runs.items()
                   if r.get("resolved") or any(o.get("status") in CLOSED_SET for o in r["outcomes"])}
    stats = {a: {"agent": a, "missions": 0, "tasks_done": 0, "actions": 0, "tool_calls": 0,
                 "handoffs_received": 0, "handoffs_made": 0, "drafts": 0, "approvals_requested": 0,
                 "flags": 0, "decisions": 0, "tickets_closed": 0} for a in AGENTS}
    joined: dict[str, set] = {a: set() for a in AGENTS}
    for e in log:
        a, ev = _agent_of(e), e.get("event")
        if ev in ("delegate", "ask_teammate"):
            if e.get("to") in stats:
                stats[e["to"]]["handoffs_received"] += 1
            if a in stats:
                stats[a]["handoffs_made"] += 1
        if a not in stats:
            continue
        s = stats[a]
        if ev == "agent_start":
            joined[a].add(e.get("run_id"))
        elif ev == "tool_call":
            s["tool_calls"] += 1
        elif ev == "tool_result" and _ok(e):
            tool = e.get("tool")
            s["actions"] += tool in ACTION_TOOLS
            s["tasks_done"] += tool == "complete_task"
            s["drafts"] += tool == "draft_message"
            s["approvals_requested"] += tool in APPROVAL_TOOLS
            s["flags"] += tool == "flag_risk"
            s["decisions"] += tool == "record_decision"
    for a, s in stats.items():
        s["missions"] = len(joined[a])
        s["tickets_closed"] = len(joined[a] & closed_runs)
        s["xp"] = (25 * s["tickets_closed"] + 10 * s["tasks_done"] + 5 * s["actions"]
                   + 3 * s["handoffs_received"] + s["tool_calls"])
        s["level"] = 1 + s["xp"] // 100
    board = sorted(stats.values(), key=lambda s: s["xp"], reverse=True)
    for i, s in enumerate(board, 1):
        s["rank"] = i
    return board


@app.get("/api/summary")
async def summary():
    """Home snapshot: ticket counts, cash, decisions waiting, who is working, tokens used."""
    async def fetch():  # one MCP session for everything on the home page
        async with Client(mcp_config()) as c:
            async def call(tool, args=None):
                r = await c.call_tool(tool, args or {}, raise_on_error=False)
                o = r.structured_content
                return o["result"] if isinstance(o, dict) and set(o) == {"result"} else o
            return (await call("list_tickets"), await call("get_cash"),
                    {"payments": await call("list_payment_requests", {"status": "pending"}),
                     "purchase_orders": await call("list_purchase_orders", {"status": "pending"}),
                     "promotions": await call("list_promotions", {"status": "pending"})})
    tickets_rows, cash_rows, pending = await in_mcp_loop(fetch)
    log = load_audit()
    runs = _runs(log)
    active: list[str] = []
    if _state.running and _state.run_id:
        started, ended = set(), set()
        for e in log:
            if e.get("run_id") == _state.run_id and (a := _agent_of(e)):
                (started if e["event"] == "agent_start" else ended if e["event"] == "agent_end" else set()).add(a)
        active = [a for a in AGENTS if a in started and a not in ended]
    done_runs = [r for r in runs.values() if r["ended_at"]]
    last = max(done_runs, key=lambda r: r["ended_at"], default=None)
    counts = {"total": len(tickets_rows),
              "open": sum(t["status"] in OPEN_SET for t in tickets_rows),
              "waiting": sum(t["status"] in WAITING_SET for t in tickets_rows),
              "closed": sum(t["status"] in CLOSED_SET for t in tickets_rows)}
    return {
        "tickets": counts,
        "cash": round(sum(c["balance"] for c in cash_rows), 2),
        "decisions_waiting": sum(len(v) for v in pending.values()),
        "running": _state.running, "run_id": _state.run_id, "ticket_id": _state.ticket_id,
        "active_agents": active,
        "missions": len(done_runs),
        "tokens_used": sum((r["usage"] or {}).get("total_tokens", 0) for r in done_runs),
        "last_run": last,
        # Included so the dashboard can refresh with a single request.
        "ticket_list": tickets_rows,
        "cash_accounts": cash_rows,
        "approvals": pending,
        "run_state": _state.model_dump(),
    }
