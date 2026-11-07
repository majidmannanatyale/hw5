"""Data types for the Campus Customs agent team.

Every fact in these objects comes from campus_customs_new.db via the MCP server.
The agents never read or write the database any other way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
Specialist = Literal["inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "waiting_for_human", "blocked", "partially_shipped",
                       "shipped", "resolved", "rejected"]


# --------------------------------------------------------------------------
# Run-time context shared by every agent in one team run
# --------------------------------------------------------------------------

@dataclass
class RunTracker:
    """Shared state for one team run: token budget, delegation de-duplication, alerts."""
    run_id: str
    token_budget: int
    warn_at_pct: float
    max_delegations: int
    delegations: dict[tuple[str, int, str], "SpecialistReport"] = field(default_factory=dict)
    delegation_count: int = 0
    warned: bool = False
    manager_alerts: list[str] = field(default_factory=list)
    mcp: object | None = None      # this run's own MCP connection (one per run / event loop)


@dataclass
class TeamDeps:
    """Passed to every agent run. `agent` is the true identity the backend stamps onto
    tool calls (requested_by / author / agent), so an agent cannot pose as another."""
    agent: AgentName
    tracker: RunTracker
    depth: int = 0                 # 0 = called by the boss; 1 = consulted by a teammate
    ticket_id: int | None = None


# --------------------------------------------------------------------------
# Agent outputs
# --------------------------------------------------------------------------

class ApprovalRef(BaseModel):
    """Something waiting for a human: a payment, a purchase order, or a promotion."""
    kind: Literal["payment", "po", "promo"]
    id: int
    amount: float | None = None
    what: str = ""


class SpecialistReport(BaseModel):
    """What a specialist did on one ticket, returned to the boss."""
    agent: Specialist
    ticket_id: int
    summary: str = Field(description="One or two plain sentences on what you found and did.")
    actions_taken: list[str] = Field(default_factory=list, description="Tool actions that changed something.")
    approvals_requested: list[ApprovalRef] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list, description="Draft ids saved on the board.")
    blocked_by: list[str] = Field(default_factory=list, description="What stops this ticket moving, if anything.")
    needs_boss_decision: str | None = Field(default=None, description="A tie or judgment call for the boss.")
    risks_flagged: list[str] = Field(default_factory=list)


class TicketOutcome(BaseModel):
    """The boss's final call on one ticket."""
    ticket_id: int
    assigned_to: list[Specialist]
    decision: str = Field(description="The final call, in one or two plain sentences.")
    status: TicketStatus
    waiting_for_human: list[ApprovalRef] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class BossReport(BaseModel):
    """The boss's report for the whole run."""
    outcomes: list[TicketOutcome]
    tie_breaks: list[str] = Field(default_factory=list, description="Disagreements you settled and how.")
    manager_alerts: list[str] = Field(default_factory=list,
                                      description="Anything the human manager must know or approve.")


# --------------------------------------------------------------------------
# API types
# --------------------------------------------------------------------------

class UsageSummary(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    token_budget: int = 0
    pct_of_budget: float = 0.0


class RunRequest(BaseModel):
    ticket_ids: list[int] | None = Field(default=None, description="Omit to work every open ticket.")


class RunResponse(BaseModel):
    run_id: str
    report: BossReport | None = None
    usage: UsageSummary
    manager_alerts: list[str] = Field(default_factory=list)
    error: str | None = None


class TicketIn(BaseModel):
    """A new incoming request. Size limits stop oversized or spammy input."""
    type: Literal["customer_order", "rent_notice", "price_override", "vendor_invoice", "general"]
    requester: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=1000)
    sku: str | None = Field(default=None, max_length=40)
    size: str | None = Field(default=None, max_length=8)
    qty: int | None = Field(default=None, gt=0, le=200)
    lease_id: int | None = None
    invoice_id: int | None = None

    @field_validator("requester", "subject", "notes")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()
