"""The Campus Customs agent team (PydanticAI + the campus-customs MCP server).

* One model only: gpt-6-luna through Portkey.
* Every shop fact and every shop action goes through the MCP server listed in
  hw5/.mcp.json, which only talks to data/campus_customs_new.db. This file adds
  NO shop tools of its own; the only local tools are for agents talking to each
  other (delegate / ask_teammate).
* Each agent sees only the MCP tools its job needs (ALLOWED_TOOLS). No agent can
  pay, approve, refund, or create tickets.
* Every agent step, tool call, delegation, and token warning is appended to
  output/audit_trail.json.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import Client
from pydantic_ai import Agent, CallToolsNode, ModelRequestNode, RunContext, UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import TextPart, ToolCallPart
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage, UsageLimits

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_server"))
import audit_log  # noqa: E402  (shared safe writer)

from models import (AgentName, BossReport, RunResponse, RunTracker, Specialist, SpecialistReport,
                    TeamDeps, UsageSummary)

BACKEND_DIR = Path(__file__).resolve().parent
HW5_DIR = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
AUDIT_PATH = HW5_DIR / "output" / "audit_trail.json"
MCP_CONFIG_PATH = HW5_DIR / ".mcp.json"

# Secrets: hw5/.env if present, else the course-level keys.env. Values are never logged.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
load_dotenv(HW5_DIR / ".env")
if len(HW5_DIR.parents) > 3:  # course-level keys.env, only when this folder sits inside the course tree
    load_dotenv(HW5_DIR.parents[3] / "keys.env")

ALLOWED_MODEL = "gpt-6-luna"
MODEL_NAME = os.getenv("OPENAI_MODEL", ALLOWED_MODEL)
if MODEL_NAME != ALLOWED_MODEL:
    raise RuntimeError(f"Only {ALLOWED_MODEL} may be used for this project (got {MODEL_NAME}).")
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")

TOKEN_BUDGET = int(os.getenv("TOKEN_BUDGET", "150000"))        # hard stop per team run
TOKEN_WARN_PCT = float(os.getenv("TOKEN_WARN_PCT", "0.6"))     # tell the manager at 60%
REQUEST_LIMIT = int(os.getenv("REQUEST_LIMIT", "60"))          # model calls per team run
MAX_DELEGATIONS = int(os.getenv("MAX_DELEGATIONS", "12"))      # boss -> specialist calls per run

AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")
SPECIALISTS: tuple[Specialist, ...] = ("inventory", "accounting", "facilities", "customer_service")

# --------------------------------------------------------------------------
# Which MCP tools each agent may use (least privilege)
# --------------------------------------------------------------------------

TEAM_TOOLS = {"get_today", "get_ticket", "read_notes", "list_claims", "claim_task", "complete_task",
              "post_note", "flag_risk"}

ALLOWED_TOOLS: dict[AgentName, set[str]] = {
    # The boss coordinates through delegate(); it never claims or completes the work itself.
    "boss": (TEAM_TOOLS - {"claim_task", "complete_task"}) | {"get_board", "list_tickets", "update_ticket", "record_decision", "cash_forecast",
                          "list_drafts", "list_payment_requests", "list_purchase_orders", "list_promotions"},
    "inventory": TEAM_TOOLS | {"check_inventory", "list_vendors", "get_pricing", "can_ship", "ship_order",
                               "ship_partial", "receive_stock", "list_purchase_orders", "list_invoices"},
    "accounting": TEAM_TOOLS | {"get_cash", "cash_forecast", "list_invoices", "list_payments",
                                "list_payment_requests", "request_payment", "get_pricing", "quote_price",
                                "propose_promotion", "list_promotions", "request_purchase_order",
                                "list_purchase_orders", "list_vendors", "list_leases"},
    "facilities": TEAM_TOOLS | {"list_leases", "get_cash", "cash_forecast", "list_payment_requests",
                                "draft_message", "list_drafts"},
    "customer_service": TEAM_TOOLS | {"check_inventory", "get_pricing", "quote_price", "list_promotions",
                                      "list_vendors", "draft_message", "list_drafts"},
}
# Deliberately given to NO agent: pay, create_ticket (and there are no approve/refund tools at all).

# The backend stamps the calling agent's real name onto these arguments.
IDENTITY_ARGS = {"request_payment": "requested_by", "request_purchase_order": "requested_by",
                 "propose_promotion": "requested_by", "draft_message": "author", "claim_task": "agent",
                 "complete_task": "agent", "post_note": "agent", "flag_risk": "agent",
                 "record_decision": "agent"}

# --------------------------------------------------------------------------
# Audit trail (append-only, shared with the MCP server)
# --------------------------------------------------------------------------

_audit_lock = threading.Lock()


def _short(value: Any, limit: int = 400) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def audit(event: str, source: str = "backend", **details: Any) -> None:
    """Append one entry. Locked + atomic, shared safely with the MCP server (see mcp_server/audit_log.py)."""
    with _audit_lock:
        audit_log.append(AUDIT_PATH, {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                      "source": source, "event": event, **details})


# --------------------------------------------------------------------------
# Model and MCP connection
# --------------------------------------------------------------------------

def build_model() -> OpenAIChatModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set (hw5/.env or the course keys.env).")
    # gpt-6-luna rejects function tools unless reasoning effort is "none".
    return OpenAIChatModel(MODEL_NAME, provider=OpenAIProvider(base_url=PORTKEY_BASE_URL, api_key=api_key),
                           settings=OpenAIChatModelSettings(openai_reasoning_effort="none",
                                                            parallel_tool_calls=False))


def mcp_config() -> dict:
    """The same config Claude Code uses (.mcp.json), with the working folder pinned to hw5/."""
    cfg = json.loads(MCP_CONFIG_PATH.read_text("utf-8"))
    for server in cfg["mcpServers"].values():
        server.setdefault("cwd", str(HW5_DIR))
    return cfg


def check_budget(ctx: RunContext[TeamDeps]) -> str | None:
    """Warn the manager once when the run's tokens pass TOKEN_WARN_PCT of the budget."""
    tr = ctx.deps.tracker
    used = ctx.usage.total_tokens
    if not tr.warned and used >= tr.token_budget * tr.warn_at_pct:
        tr.warned = True
        msg = (f"Token use is getting expensive: {used:,} of {tr.token_budget:,} tokens "
               f"({used / tr.token_budget:.0%}) used in run {tr.run_id}. Wrap up with as few calls as possible.")
        tr.manager_alerts.append(msg)
        audit("token_budget_warning", source="backend", run_id=tr.run_id, total_tokens=used,
              budget=tr.token_budget)
        return msg
    return None


async def process_tool_call(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict[str, Any]):
    """Runs around every MCP tool call: stamps identity, audits, and checks the token budget."""
    deps = ctx.deps
    if name in IDENTITY_ARGS:
        args = {**args, IDENTITY_ARGS[name]: deps.agent}
    audit("tool_call", source=f"agent:{deps.agent}", run_id=deps.tracker.run_id, tool=name, args=_short(args))
    result = await call_tool(name, args)
    audit("tool_result", source=f"agent:{deps.agent}", run_id=deps.tracker.run_id, tool=name,
          result=_short(result))
    warning = check_budget(ctx)
    if warning:
        result = {"result": result, "manager_budget_warning": warning}
    return result


def build_mcp_toolset() -> MCPToolset:
    return MCPToolset(Client(mcp_config()), process_tool_call=process_tool_call, max_retries=1)




def toolset_for(mcp: MCPToolset, agent: AgentName):
    allowed = ALLOWED_TOOLS[agent]
    return mcp.filtered(lambda ctx, tool_def: tool_def.name in allowed)


# --------------------------------------------------------------------------
# Agents
# --------------------------------------------------------------------------

def load_prompt(agent: AgentName) -> str:
    return (PROMPTS_DIR / f"{agent}.md").read_text("utf-8")


def _today_instruction(ctx: RunContext[TeamDeps]) -> str:
    d = ctx.deps
    return (f"You are the {d.agent} agent. Run id: {d.tracker.run_id}. "
            + ("You were consulted by a teammate: answer directly; you cannot delegate further."
               if d.depth >= 2 else ""))


MODEL = build_model()

boss_agent: Agent[TeamDeps, BossReport] = Agent(
    MODEL, name="boss", deps_type=TeamDeps, output_type=BossReport,
    instructions=[load_prompt("boss"), _today_instruction], retries=1)

specialist_agents: dict[Specialist, Agent[TeamDeps, SpecialistReport]] = {
    name: Agent(MODEL, name=name, deps_type=TeamDeps, output_type=SpecialistReport,
                instructions=[load_prompt(name), _today_instruction], retries=1)
    for name in SPECIALISTS
}


async def run_logged(agent_name: AgentName, agent: Agent, prompt: str, deps: TeamDeps, usage: RunUsage | None):
    """Run one agent and log each loop step (model request, tool calls planned, text)."""
    tr = deps.tracker
    audit("agent_start", source=f"agent:{agent_name}", run_id=tr.run_id, ticket_id=deps.ticket_id,
          depth=deps.depth, prompt=_short(prompt))
    step = 0
    async with agent.iter(prompt, deps=deps, usage=usage, toolsets=[toolset_for(tr.mcp, agent_name)],
                          usage_limits=UsageLimits(request_limit=REQUEST_LIMIT,
                                                   total_tokens_limit=tr.token_budget)) as run:
        async for node in run:
            if isinstance(node, ModelRequestNode):
                step += 1
            elif isinstance(node, CallToolsNode):
                parts = node.model_response.parts
                audit("agent_step", source=f"agent:{agent_name}", run_id=tr.run_id, step=step,
                      tool_calls=[p.tool_name for p in parts if isinstance(p, ToolCallPart)],
                      text=_short(" ".join(p.content for p in parts if isinstance(p, TextPart)), 300))
    output = run.result.output
    said = (output.summary if isinstance(output, SpecialistReport)
            else " ".join(f"#{o.ticket_id}: {o.decision}" for o in output.outcomes))
    audit("agent_end", source=f"agent:{agent_name}", run_id=tr.run_id, ticket_id=deps.ticket_id,
          steps=step, said=said, output=_short(output.model_dump(), 4000), total_tokens_so_far=run.usage.total_tokens)
    return output


async def _consult(ctx: RunContext[TeamDeps], agent: Specialist, ticket_id: int, task: str,
                   kind: str) -> SpecialistReport | str:
    """Shared delegation logic: de-duplicates repeated asks and caps the number of hand-offs."""
    tr = ctx.deps.tracker
    key = (agent, ticket_id, " ".join(task.lower().split()))
    if key in tr.delegations:
        audit("delegation_deduplicated", source=f"agent:{ctx.deps.agent}", run_id=tr.run_id, to=agent,
              ticket_id=ticket_id)
        return tr.delegations[key]
    if agent == ctx.deps.agent:
        return "You cannot delegate to yourself. Do the work with your own tools."
    if tr.delegation_count >= tr.max_delegations:
        return "Delegation limit reached for this run. Finish with what you have and report it."
    tr.delegation_count += 1
    audit(kind, source=f"agent:{ctx.deps.agent}", run_id=tr.run_id, to=agent, ticket_id=ticket_id,
          task=_short(task))
    report = await run_logged(agent, specialist_agents[agent],
                              f"Ticket #{ticket_id}. Requested by {ctx.deps.agent}: {task}",
                              TeamDeps(agent=agent, tracker=tr, depth=ctx.deps.depth + 1, ticket_id=ticket_id),
                              usage=ctx.usage)
    tr.delegations[key] = report
    return report


@boss_agent.tool
async def delegate(ctx: RunContext[TeamDeps], agent: Specialist, ticket_id: int, task: str) -> SpecialistReport | str:
    """Hand one specific task on one ticket to a specialist and get their report back.
    Be specific (what to check, what to prepare). Asking the same thing twice returns
    the earlier report instead of redoing the work."""
    return await _consult(ctx, agent, ticket_id, task, "delegate")


for _name, _agent in specialist_agents.items():
    @_agent.tool
    async def ask_teammate(ctx: RunContext[TeamDeps], agent: Specialist, ticket_id: int,
                           question: str) -> SpecialistReport | str:
        """Ask another specialist for something only they can do or know (for example,
        accounting asks inventory for the shortfall). Not available when you were
        yourself consulted. For ties or judgment calls, post_note(kind='escalation') instead."""
        if ctx.deps.depth >= 2:
            return "You were consulted by a teammate, so you cannot consult further. Post a note instead."
        return await _consult(ctx, agent, ticket_id, question, "ask_teammate")


# --------------------------------------------------------------------------
# One team run
# --------------------------------------------------------------------------

async def run_team(ticket_ids: list[int] | None = None, run_id: str | None = None) -> RunResponse:
    tracker = RunTracker(run_id=run_id or uuid.uuid4().hex[:8], token_budget=TOKEN_BUDGET, warn_at_pct=TOKEN_WARN_PCT,
                         max_delegations=MAX_DELEGATIONS)
    scope = (f"tickets {', '.join(f'#{t}' for t in ticket_ids)}" if ticket_ids else "every open ticket")
    prompt = (f"Work {scope} on the board. Read the board once, decide who handles each ticket, "
              "delegate specific tasks, settle any ties, record your decision on each ticket, and report.")
    audit("run_start", run_id=tracker.run_id, model=MODEL_NAME, scope=scope, ticket_ids=ticket_ids or [],
          token_budget=TOKEN_BUDGET)
    usage = RunUsage()
    report, error = None, None
    try:
        tracker.mcp = build_mcp_toolset()  # fresh connection on this run's event loop
        async with tracker.mcp:
            report = await run_logged("boss", boss_agent, prompt,
                                      TeamDeps(agent="boss", tracker=tracker), usage=usage)
    except UsageLimitExceeded as exc:
        error = "Stopped: the run hit its token or request limit before finishing."
        tracker.manager_alerts.append(f"{error} ({exc})")
        audit("run_stopped_usage_limit", run_id=tracker.run_id, detail=str(exc))
    except Exception as exc:  # never leak internals to the caller
        error = "The team run failed. See the audit trail for details."
        audit("run_error", run_id=tracker.run_id, error_type=type(exc).__name__, detail=_short(str(exc)))
    summary = UsageSummary(requests=usage.requests, input_tokens=usage.input_tokens,
                           output_tokens=usage.output_tokens, total_tokens=usage.total_tokens,
                           token_budget=TOKEN_BUDGET,
                           pct_of_budget=round(usage.total_tokens / TOKEN_BUDGET * 100, 1))
    alerts = tracker.manager_alerts + (report.manager_alerts if report else [])
    audit("run_end", run_id=tracker.run_id, usage=summary.model_dump(), delegations=tracker.delegation_count,
          manager_alerts=alerts, error=error)
    return RunResponse(run_id=tracker.run_id, report=report, usage=summary, manager_alerts=alerts, error=error)
