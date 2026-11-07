"""Campus Customs MCP server (FastMCP).

Talks ONLY to data/campus_customs_new.db. The original data/campus_customs.db
is never opened by any tool; it is read once, as a file copy source, by the
`--reset` command (run by a human, not exposed to agents).

Shop rules enforced here (see output/harness.md):
  * "Today" is desk.date_today, never the system clock.
  * Vendor lead times come from vendors.lead_days.
  * New product ships only when there are NO open unpaid invoices.
  * Human approval is REQUIRED for every payment, purchase order, and
    promotion. Agents can only *request* them; approving is a human-only
    command that is NOT an MCP tool.
  * The pay tool refuses if cash is insufficient. No negative balances.
  * Cash only goes out. There is no revenue, deposit, or refund tool.
  * No tool emails customers or contacts vendors. Messages are drafts that
    stay on the board.
  * Anti-spam: duplicate tickets are refused and each requester has a cap.

Commands:
  python server.py                                  # start MCP server (stdio)
  python server.py reset                            # human: reset new DB from original
  python server.py approve payment|po|promo ID NAME  # human: approve (payment also pays)
  python server.py reject  payment|po|promo ID NAME  # human: reject
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_log  # noqa: E402  (shared safe writer)

HW5_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = HW5_DIR / "data"
DB_PATH = DATA_DIR / "campus_customs_new.db"          # the ONLY database tools use
ORIGINAL_DB_PATH = DATA_DIR / "campus_customs.db"     # read-only source for --reset
AUDIT_PATH = HW5_DIR / "output" / "audit_trail.json"

assert DB_PATH.name == "campus_customs_new.db" and DB_PATH != ORIGINAL_DB_PATH

MAX_OPEN_TICKETS_PER_REQUESTER = 3   # anti-spam cap
MAX_QTY_PER_TICKET = 200             # anything bigger needs a human


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def _guard_path(path: Path) -> None:
    if path.resolve() == ORIGINAL_DB_PATH.resolve():
        raise RuntimeError("Refusing to open the original campus_customs.db.")


@contextmanager
def db():
    """Connection to campus_customs_new.db. Commits on success, rolls back on error."""
    _guard_path(DB_PATH)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH.name} not found. Run: python server.py --reset")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_tables() -> None:
    """Server-owned table for the human payment-approval gate (idempotent)."""
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('invoice', 'rent')),
                ref_id INTEGER NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                account TEXT NOT NULL,
                reason TEXT,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'paid')),
                decided_by TEXT,
                decided_at TEXT
            )
            """
        )
        # One row per paid reprint invoice that has been received into inventory.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS restocks (
                invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id),
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                qty INTEGER NOT NULL CHECK (qty > 0),
                received_at TEXT NOT NULL
            )
            """
        )
        # One row per shipment, so an order can ship in parts.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shipments (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                qty INTEGER NOT NULL CHECK (qty > 0),
                shipped_at TEXT NOT NULL
            )
            """
        )
        # Team board: notes, escalations, risk flags, and the boss's final decisions.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_notes (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                agent TEXT NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('note', 'escalation', 'flag', 'decision')),
                message TEXT NOT NULL,
                severity TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        # Who is working on what, so two agents never do the same task.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_claims (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                agent TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'claimed' CHECK (status IN ('claimed', 'done')),
                result TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (ticket_id, task)
            )
            """
        )
        # Drafted messages. They stay on the board and are never sent.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                author TEXT NOT NULL,
                audience TEXT NOT NULL CHECK (audience IN ('customer', 'landlord', 'vendor', 'internal')),
                to_name TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status = 'draft'),
                created_at TEXT NOT NULL
            )
            """
        )
        # Purchase orders wait for a human before they become a vendor bill.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                vendor_id INTEGER NOT NULL REFERENCES vendors(id),
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                qty INTEGER NOT NULL CHECK (qty > 0),
                amount REAL NOT NULL,
                eta TEXT NOT NULL,
                reason TEXT,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                invoice_id INTEGER,
                decided_by TEXT,
                decided_at TEXT
            )
            """
        )
        # Discounts and promotions wait for a human before anyone can quote them.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                sku TEXT NOT NULL,
                discount_pct REAL NOT NULL CHECK (discount_pct > 0 AND discount_pct < 100),
                min_qty INTEGER NOT NULL DEFAULT 1,
                reason TEXT,
                requested_by TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                decided_by TEXT,
                decided_at TEXT
            )
            """
        )


def shipped_qty(conn, ticket_id: int) -> int:
    return conn.execute("SELECT COALESCE(SUM(qty), 0) FROM shipments WHERE ticket_id = ?",
                        (ticket_id,)).fetchone()[0]


def parse_reprint(conn, invoice) -> dict | None:
    """Find sku, size, and (if written) qty in a reprint invoice description,
    e.g. 'Rush reprint CC-TEE-WHITE S' or 'Reprint CC-HOOD-NAVY M x12'."""
    desc = invoice["description"] or ""
    for (sku,) in conn.execute("SELECT DISTINCT sku FROM inventory"):
        m = re.search(re.escape(sku) + r"\s+(\S+)(?:\s+x(\d+))?", desc)
        if m:
            return {"sku": sku, "size": m.group(1), "qty": int(m.group(2)) if m.group(2) else None}
    return None


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def today(conn) -> date:
    row = conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()
    return date.fromisoformat(row["date_today"])


def add_months(d: date, n: int = 1) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def open_invoices(conn) -> list[dict]:
    return rows(conn.execute("SELECT * FROM invoices WHERE status != 'paid' ORDER BY due_date"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def audit(event: str, **details) -> None:
    """Append-only audit trail in output/audit_trail.json (locked + atomic, never overwritten)."""
    audit_log.append(AUDIT_PATH, {"ts": now_iso(), "source": "mcp_server", "event": event, **details})


# --------------------------------------------------------------------------
# MCP tools
# --------------------------------------------------------------------------

def build_server():
    from fastmcp import FastMCP  # imported here so --reset/--approve work without it

    mcp = FastMCP(
        "campus-customs",
        instructions=(
            "Campus Customs shop tools. Today is desk.date_today. Every payment, purchase "
            "order, and promotion needs human approval: request it, then wait for a human. "
            "Never email customers or contact vendors; draft_message only saves drafts on "
            "the board. Claim a task before doing it so no work is duplicated."
        ),
    )

    # ---- Read tools -------------------------------------------------------

    @mcp.tool
    def get_today() -> dict:
        """Return the shop's 'today' (desk.date_today) and desk notes."""
        with db() as conn:
            row = dict(conn.execute("SELECT * FROM desk LIMIT 1").fetchone())
        return row

    @mcp.tool
    def list_tickets(status: str | None = None) -> list[dict]:
        """List tickets, optionally filtered by status (e.g. 'open')."""
        with db() as conn:
            if status:
                return rows(conn.execute("SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)))
            return rows(conn.execute("SELECT * FROM tickets ORDER BY id"))

    @mcp.tool
    def get_ticket(ticket_id: int) -> dict:
        """Get one ticket plus its linked invoice or lease, if any."""
        with db() as conn:
            t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not t:
                return {"found": False, "ticket_id": ticket_id}
            out = {"found": True, "ticket": dict(t)}
            if t["invoice_id"]:
                inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (t["invoice_id"],)).fetchone()
                out["invoice"] = dict(inv) if inv else None
            if t["lease_id"]:
                lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
                out["lease"] = dict(lease) if lease else None
        return out

    @mcp.tool
    def check_inventory(sku: str | None = None, size: str | None = None) -> list[dict]:
        """Stock on hand by SKU and size. Omit filters to see everything."""
        sql, args = "SELECT * FROM inventory WHERE 1=1", []
        if sku:
            sql += " AND sku = ?"; args.append(sku)
        if size:
            sql += " AND size = ?"; args.append(size)
        with db() as conn:
            return rows(conn.execute(sql + " ORDER BY sku, size", args))

    @mcp.tool
    def get_pricing(sku: str | None = None) -> list[dict]:
        """Unit cost and list price per SKU."""
        with db() as conn:
            if sku:
                return rows(conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)))
            return rows(conn.execute("SELECT * FROM pricing ORDER BY sku"))

    @mcp.tool
    def quote_price(sku: str, qty: int, discount_pct: float = 0.0) -> dict:
        """Price a quote. Refuses any discount that would sell below unit cost."""
        if qty <= 0 or not (0 <= discount_pct < 100):
            return {"ok": False, "reason": "qty must be > 0 and discount_pct in [0, 100)."}
        with db() as conn:
            p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if not p:
            return {"ok": False, "reason": f"Unknown SKU {sku}."}
        unit = round(p["list_price"] * (1 - discount_pct / 100), 2)
        max_disc = round((1 - p["unit_cost"] / p["list_price"]) * 100, 2)
        if unit < p["unit_cost"]:
            return {"ok": False, "reason": "Below unit cost.", "unit_cost": p["unit_cost"],
                    "max_discount_pct_at_cost": max_disc}
        return {"ok": True, "sku": sku, "qty": qty, "list_price": p["list_price"],
                "discount_pct": discount_pct, "unit_price": unit, "total": round(unit * qty, 2),
                "unit_margin": round(unit - p["unit_cost"], 2), "max_discount_pct_at_cost": max_disc}

    @mcp.tool
    def list_vendors() -> list[dict]:
        """Vendors with specialty and lead_days (the only source of lead times)."""
        with db() as conn:
            return rows(conn.execute("SELECT * FROM vendors ORDER BY id"))

    @mcp.tool
    def list_invoices(status: str | None = None) -> list[dict]:
        """Invoices with days_overdue computed against desk.date_today."""
        with db() as conn:
            t = today(conn)
            data = rows(conn.execute(
                "SELECT * FROM invoices" + (" WHERE status = ?" if status else "") + " ORDER BY due_date",
                (status,) if status else ()))
        for inv in data:
            days = (t - date.fromisoformat(inv["due_date"])).days
            inv["overdue"] = inv["status"] != "paid" and days > 0
            inv["days_overdue"] = max(days, 0) if inv["status"] != "paid" else 0
        return data

    @mcp.tool
    def list_leases() -> list[dict]:
        """Leases with days_until_due computed against desk.date_today."""
        with db() as conn:
            t = today(conn)
            data = rows(conn.execute("SELECT * FROM leases ORDER BY id"))
        for lease in data:
            lease["days_until_due"] = (date.fromisoformat(lease["next_due"]) - t).days
        return data

    @mcp.tool
    def get_cash() -> list[dict]:
        """Cash account balances. Cash only goes out; there is no deposit tool."""
        with db() as conn:
            return rows(conn.execute("SELECT * FROM cash_accounts"))

    @mcp.tool
    def list_payments() -> list[dict]:
        """Ledger of completed payments (each with its human approver)."""
        with db() as conn:
            return rows(conn.execute("SELECT * FROM payments ORDER BY id"))

    @mcp.tool
    def list_payment_requests(status: str | None = None) -> list[dict]:
        """Payment requests and their human-approval status."""
        with db() as conn:
            if status:
                return rows(conn.execute("SELECT * FROM payment_requests WHERE status = ? ORDER BY id", (status,)))
            return rows(conn.execute("SELECT * FROM payment_requests ORDER BY id"))

    @mcp.tool
    def can_ship(sku: str, size: str, qty: int) -> dict:
        """Check whether an order can ship: enough stock AND no open unpaid invoices."""
        with db() as conn:
            inv = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
            blocking = open_invoices(conn)
        on_hand = inv["qty"] if inv else 0
        reasons = []
        if not inv:
            reasons.append(f"No inventory row for {sku} size {size}.")
        elif on_hand < qty:
            reasons.append(f"Only {on_hand} on hand, need {qty} (short {qty - on_hand}).")
        if blocking:
            reasons.append("Open unpaid invoices block shipping: "
                           + ", ".join(f"#{i['id']} (${i['amount']:.2f})" for i in blocking))
        return {"can_ship": not reasons, "on_hand": on_hand, "requested": qty,
                "blocking_invoices": [i["id"] for i in blocking], "reasons": reasons}

    # ---- Write tools ------------------------------------------------------

    def _prepare_shipment(conn, ticket_id: int):
        """Shared checks for ship_order / ship_partial. Returns (ticket, owed, on_hand) or an error dict."""
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not t or not t["sku"] or not t["qty"]:
            return {"ok": False, "reason": "Ticket not found or has no sku/qty."}
        owed = t["qty"] - shipped_qty(conn, ticket_id)
        if owed <= 0:
            return {"ok": False, "reason": "Nothing left to ship on this ticket."}
        blocking = open_invoices(conn)
        if blocking:
            return {"ok": False, "reason": "Open unpaid invoices block shipping.",
                    "blocking_invoices": [i["id"] for i in blocking]}
        inv = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?",
                           (t["sku"], t["size"])).fetchone()
        return t, owed, (inv["qty"] if inv else 0)

    def _record_shipment(conn, t, qty: int, owed: int) -> dict:
        d = today(conn).isoformat()
        conn.execute("UPDATE inventory SET qty = qty - ? WHERE sku = ? AND size = ?", (qty, t["sku"], t["size"]))
        conn.execute("INSERT INTO shipments (ticket_id, sku, size, qty, shipped_at) VALUES (?, ?, ?, ?, ?)",
                     (t["id"], t["sku"], t["size"], qty, d))
        still_owed = owed - qty
        status = "shipped" if still_owed == 0 else "partially_shipped"
        note = (f"\n[{d}] Shipped {qty} x {t['sku']} {t['size']}."
                + (f" {still_owed} still owed." if still_owed else " Order complete."))
        conn.execute("UPDATE tickets SET status = ?, notes = COALESCE(notes, '') || ? WHERE id = ?",
                     (status, note, t["id"]))
        return {"shipped_now": qty, "still_owed": still_owed, "status": status}

    @mcp.tool
    def ship_order(ticket_id: int) -> dict:
        """Ship everything still owed on an order ticket. Refuses if stock is short
        (use ship_partial instead) or any invoice is open and unpaid."""
        with db() as conn:
            prep = _prepare_shipment(conn, ticket_id)
            if isinstance(prep, dict):
                return prep
            t, owed, on_hand = prep
            if on_hand < owed:
                return {"ok": False, "reason": f"Only {on_hand} on hand, {owed} owed. Use ship_partial."}
            result = _record_shipment(conn, t, owed, owed)
        audit("ship_order", ticket_id=ticket_id, sku=t["sku"], size=t["size"], qty=owed)
        return {"ok": True, "ticket_id": ticket_id, **result}

    @mcp.tool
    def ship_partial(ticket_id: int) -> dict:
        """Ship what is on hand now and record the rest as still owed (e.g. 8 of 20).
        Same rules as ship_order: refuses while any invoice is open and unpaid.
        Returns a customer notice DRAFT saying the order ships in two parts; it is
        never sent."""
        with db() as conn:
            prep = _prepare_shipment(conn, ticket_id)
            if isinstance(prep, dict):
                return prep
            t, owed, on_hand = prep
            if on_hand <= 0:
                return {"ok": False, "reason": "Nothing on hand to ship. Reprint first."}
            if on_hand >= owed:
                return {"ok": False, "reason": f"Enough stock to ship all {owed}. Use ship_order."}
            result = _record_shipment(conn, t, on_hand, owed)
        audit("ship_partial", ticket_id=ticket_id, sku=t["sku"], size=t["size"],
              qty=on_hand, still_owed=result["still_owed"])
        notice = (f"Hi {t['requester']}, your order of {t['qty']} x {t['sku']} size {t['size']} "
                  f"will ship in two parts: {on_hand} now and the remaining {result['still_owed']} "
                  "once they are restocked.")
        return {"ok": True, "ticket_id": ticket_id, **result,
                "customer_notice_draft": {"to": t["requester"], "body": notice, "sent": False}}

    @mcp.tool
    def receive_stock(invoice_id: int, qty: int | None = None) -> dict:
        """Add reprinted items to inventory once their reprint invoice is PAID.
        Reads the sku and size from the invoice description. Quantity comes from
        the description (e.g. 'x12'), else the qty argument, else the total qty of
        tickets linked to the invoice. Each invoice can only be received once."""
        with db() as conn:
            inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
            if not inv:
                return {"ok": False, "reason": f"No invoice {invoice_id}."}
            if inv["status"] != "paid":
                return {"ok": False, "reason": "Refused: invoice is not paid yet. Request payment first."}
            if conn.execute("SELECT 1 FROM restocks WHERE invoice_id = ?", (invoice_id,)).fetchone():
                return {"ok": False, "reason": "This invoice was already received into inventory."}
            item = parse_reprint(conn, inv)
            if not item:
                return {"ok": False, "reason": "Invoice is not a reprint of a known SKU and size."}
            n = item["qty"] or qty or conn.execute(
                "SELECT COALESCE(SUM(qty), 0) FROM tickets WHERE invoice_id = ?", (invoice_id,)).fetchone()[0]
            if not n or n <= 0:
                return {"ok": False, "reason": "Quantity unknown. Pass qty."}
            cur = conn.execute("UPDATE inventory SET qty = qty + ? WHERE sku = ? AND size = ?",
                               (n, item["sku"], item["size"]))
            if cur.rowcount == 0:
                return {"ok": False, "reason": f"No inventory row for {item['sku']} size {item['size']}."}
            conn.execute("INSERT INTO restocks (invoice_id, sku, size, qty, received_at) VALUES (?, ?, ?, ?, ?)",
                         (invoice_id, item["sku"], item["size"], n, today(conn).isoformat()))
            new_qty = conn.execute("SELECT qty FROM inventory WHERE sku = ? AND size = ?",
                                   (item["sku"], item["size"])).fetchone()["qty"]
        audit("receive_stock", invoice_id=invoice_id, sku=item["sku"], size=item["size"], qty=n)
        return {"ok": True, "invoice_id": invoice_id, "sku": item["sku"], "size": item["size"],
                "received": n, "on_hand_now": new_qty}

    @mcp.tool
    def cash_forecast(within_days: int = 30) -> dict:
        """Read-only: list unpaid bills (open invoices, including overdue, and rent
        due within `within_days` of desk.date_today) in due-date order, with the cash
        left after each one. Flags the first bill the shop could not afford. Pays nothing."""
        with db() as conn:
            t = today(conn)
            cash = conn.execute("SELECT COALESCE(SUM(balance), 0) FROM cash_accounts").fetchone()[0]
            horizon = (t + timedelta(days=within_days)).isoformat()
            bills = [{"kind": "invoice", "ref_id": i["id"], "amount": i["amount"], "due": i["due_date"],
                      "what": i["description"]}
                     for i in open_invoices(conn) if i["due_date"] <= horizon]
            bills += [{"kind": "rent", "ref_id": l["id"], "amount": l["monthly_rent"], "due": l["next_due"],
                       "what": f"Rent: {l['space_name']}"}
                      for l in rows(conn.execute("SELECT * FROM leases WHERE next_due <= ?", (horizon,)))]
        bills.sort(key=lambda b: b["due"])
        left, shortfall_at = cash, None
        for b in bills:
            b["overdue"] = b["due"] < t.isoformat()
            left = round(left - b["amount"], 2)
            b["cash_left_after"] = left
            if left < 0 and shortfall_at is None:
                shortfall_at = b
        total = round(sum(b["amount"] for b in bills), 2)
        with db() as conn:
            pending_pos = rows(conn.execute(
                "SELECT id, sku, size, qty, amount FROM purchase_orders WHERE status = 'pending'"))
        return {"today": t.isoformat(), "cash_now": cash, "bills": bills, "total_due": total,
                "pending_purchase_orders": pending_pos,
                "cash_left_if_pending_pos_approved": round(cash - total - sum(p["amount"] for p in pending_pos), 2),
                "cash_left_after_all": round(cash - total, 2), "can_cover_all": cash >= total,
                "first_unaffordable_bill": shortfall_at,
                "note": "Forecast only. Every payment still needs human approval."}

    # ---- Purchasing (needs a human) ----------------------------------------

    @mcp.tool
    def request_purchase_order(sku: str, size: str, qty: int, vendor_id: int,
                               requested_by: str, reason: str = "", ticket_id: int | None = None) -> dict:
        """Prepare a reprint purchase order (qty x unit_cost, ETA from vendors.lead_days)
        for HUMAN approval. Nothing is ordered and no vendor is contacted. When a human
        approves it, it becomes an open vendor invoice (which blocks shipping until paid)."""
        if qty <= 0:
            return {"ok": False, "reason": "qty must be > 0."}
        with db() as conn:
            v = conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
            p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
            if not v or not p:
                return {"ok": False, "reason": "Unknown vendor or SKU."}
            if not conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone():
                return {"ok": False, "reason": f"No inventory row for {sku} size {size}."}
            dup = conn.execute("SELECT id FROM purchase_orders WHERE sku = ? AND size = ? AND status = 'pending'",
                               (sku, size)).fetchone()
            if dup:
                return {"ok": False, "reason": f"Purchase order #{dup['id']} for {sku} {size} is already waiting for approval."}
            eta = (today(conn) + timedelta(days=v["lead_days"])).isoformat()
            amount = round(p["unit_cost"] * qty, 2)
            cur = conn.execute(
                "INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, amount, eta, reason, requested_by, requested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ticket_id, vendor_id, sku, size, qty, amount, eta, reason, requested_by, now_iso()))
            po_id = cur.lastrowid
        audit("request_purchase_order", po_id=po_id, sku=sku, size=size, qty=qty, vendor_id=vendor_id,
              amount=amount, requested_by=requested_by)
        return {"ok": True, "po_id": po_id, "status": "pending", "amount": amount, "vendor": v["name"],
                "lead_days": v["lead_days"], "eta_if_approved_today": eta,
                "note": "Waiting for human approval. Nothing ordered, no vendor contacted."}

    @mcp.tool
    def list_purchase_orders(status: str | None = None) -> list[dict]:
        """Purchase orders and their human-approval status."""
        with db() as conn:
            if status:
                return rows(conn.execute("SELECT * FROM purchase_orders WHERE status = ? ORDER BY id", (status,)))
            return rows(conn.execute("SELECT * FROM purchase_orders ORDER BY id"))

    # ---- Discounts and promotions (needs a human) --------------------------

    @mcp.tool
    def propose_promotion(sku: str, discount_pct: float, requested_by: str, reason: str = "",
                          min_qty: int = 1, ticket_id: int | None = None) -> dict:
        """Propose a discount on a SKU (optionally only for orders of min_qty or more)
        for HUMAN approval. Refuses any discount that would sell below unit cost."""
        if not (0 < discount_pct < 100) or min_qty < 1:
            return {"ok": False, "reason": "discount_pct must be between 0 and 100, min_qty >= 1."}
        with db() as conn:
            p = conn.execute("SELECT * FROM pricing WHERE sku = ?", (sku,)).fetchone()
            if not p:
                return {"ok": False, "reason": f"Unknown SKU {sku}."}
            unit = round(p["list_price"] * (1 - discount_pct / 100), 2)
            if unit < p["unit_cost"]:
                return {"ok": False, "reason": "Refused: below unit cost.", "unit_cost": p["unit_cost"],
                        "max_discount_pct_at_cost": round((1 - p["unit_cost"] / p["list_price"]) * 100, 2)}
            dup = conn.execute("SELECT id FROM promotions WHERE sku = ? AND status = 'pending' AND "
                               "COALESCE(ticket_id, -1) = COALESCE(?, -1)", (sku, ticket_id)).fetchone()
            if dup:
                return {"ok": False, "reason": f"Promotion #{dup['id']} is already waiting for approval."}
            cur = conn.execute(
                "INSERT INTO promotions (ticket_id, sku, discount_pct, min_qty, reason, requested_by, requested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ticket_id, sku, discount_pct, min_qty, reason, requested_by, now_iso()))
            promo_id = cur.lastrowid
        audit("propose_promotion", promo_id=promo_id, sku=sku, discount_pct=discount_pct, min_qty=min_qty,
              requested_by=requested_by)
        return {"ok": True, "promo_id": promo_id, "status": "pending", "unit_price_if_approved": unit,
                "unit_margin_if_approved": round(unit - p["unit_cost"], 2),
                "note": "Waiting for human approval. Do not promise this discount to anyone yet."}

    @mcp.tool
    def list_promotions(status: str | None = None, sku: str | None = None) -> list[dict]:
        """Promotions and their human-approval status. Only 'approved' ones may be quoted."""
        sql, args = "SELECT * FROM promotions WHERE 1=1", []
        if status:
            sql += " AND status = ?"; args.append(status)
        if sku:
            sql += " AND sku = ?"; args.append(sku)
        with db() as conn:
            return rows(conn.execute(sql + " ORDER BY id", args))

    # ---- Tickets -------------------------------------------------------------

    @mcp.tool
    def update_ticket(ticket_id: int, status: str | None = None, note: str | None = None) -> dict:
        """Change a ticket's status and/or append a dated note."""
        with db() as conn:
            tk = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            if not tk:
                return {"ok": False, "reason": "Ticket not found."}
            # A ticket can only say it shipped if a shipment is actually recorded.
            sent = shipped_qty(conn, ticket_id)
            if status in ("shipped", "partially_shipped") and sent == 0:
                return {"ok": False, "reason": "Refused: nothing has shipped on this ticket yet. "
                                               "Ask inventory to ship (ship_order / ship_partial) first."}
            if status == "shipped" and tk["qty"] and sent < tk["qty"]:
                return {"ok": False, "reason": f"Refused: only {sent} of {tk['qty']} shipped. Use partially_shipped "
                                               "or resolved (if the rest will not be supplied)."}
            if status:
                conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
            if note:
                conn.execute("UPDATE tickets SET notes = COALESCE(notes, '') || ? WHERE id = ?",
                             (f"\n[{today(conn).isoformat()}] {note}", ticket_id))
            t = dict(conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone())
        audit("update_ticket", ticket_id=ticket_id, status=status, note=note)
        return {"ok": True, "ticket": t}

    @mcp.tool
    def create_ticket(type: str, requester: str, subject: str, notes: str = "",
                      sku: str | None = None, size: str | None = None, qty: int | None = None,
                      lease_id: int | None = None, invoice_id: int | None = None) -> dict:
        """Log a new incoming request (customer order, rent notice, price request,
        etc.) as an open ticket. Anti-spam: refuses an exact duplicate of an open
        ticket, and caps each requester at MAX_OPEN_TICKETS_PER_REQUESTER open tickets."""
        if qty is not None and qty <= 0:
            return {"ok": False, "reason": "qty must be > 0."}
        if qty is not None and qty > MAX_QTY_PER_TICKET:
            return {"ok": False, "reason": f"qty over {MAX_QTY_PER_TICKET} needs a human; flag it instead."}
        with db() as conn:
            if sku and not conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND (? IS NULL OR size = ?)",
                                        (sku, size, size)).fetchone():
                return {"ok": False, "reason": f"Unknown sku/size {sku} {size}."}
            if lease_id and not conn.execute("SELECT 1 FROM leases WHERE id = ?", (lease_id,)).fetchone():
                return {"ok": False, "reason": f"No lease {lease_id}."}
            if invoice_id and not conn.execute("SELECT 1 FROM invoices WHERE id = ?", (invoice_id,)).fetchone():
                return {"ok": False, "reason": f"No invoice {invoice_id}."}
            dup = conn.execute(
                "SELECT id FROM tickets WHERE status NOT IN ('resolved', 'shipped', 'closed', 'rejected') "
                "AND requester = ? AND subject = ? AND COALESCE(sku,'') = COALESCE(?,'') "
                "AND COALESCE(size,'') = COALESCE(?,'') AND COALESCE(qty,0) = COALESCE(?,0)",
                (requester, subject, sku, size, qty)).fetchone()
            if dup:
                audit("spam_blocked", reason="duplicate", requester=requester, duplicate_of=dup["id"])
                return {"ok": False, "reason": f"Duplicate of open ticket #{dup['id']}."}
            n_open = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE requester = ? AND status NOT IN "
                "('resolved', 'shipped', 'closed', 'rejected')", (requester,)).fetchone()[0]
            if n_open >= MAX_OPEN_TICKETS_PER_REQUESTER:
                audit("spam_blocked", reason="too_many_open", requester=requester, open=n_open)
                return {"ok": False, "reason": f"{requester} already has {n_open} open tickets."}
            created = f"{today(conn).isoformat()}T00:00:00-04:00"
            cur = conn.execute(
                "INSERT INTO tickets (type, requester, subject, sku, size, qty, lease_id, invoice_id, status, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)",
                (type, requester, subject, sku, size, qty, lease_id, invoice_id, notes, created))
            t = dict(conn.execute("SELECT * FROM tickets WHERE id = ?", (cur.lastrowid,)).fetchone())
        audit("create_ticket", ticket_id=t["id"], type=type, requester=requester)
        return {"ok": True, "ticket": t}

    # ---- Payments (needs a human) -----------------------------------------

    @mcp.tool
    def request_payment(kind: str, ref_id: int, amount: float, requested_by: str,
                        reason: str = "", account: str = "checking") -> dict:
        """Ask a HUMAN to approve a payment (kind 'invoice' or 'rent'; ref_id is the
        invoice id or lease id). This does NOT pay anything. Agents cannot approve."""
        if kind not in ("invoice", "rent") or amount <= 0:
            return {"ok": False, "reason": "kind must be 'invoice' or 'rent' and amount > 0."}
        with db() as conn:
            table = "invoices" if kind == "invoice" else "leases"
            ref = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (ref_id,)).fetchone()
            if not ref:
                return {"ok": False, "reason": f"No {kind} with id {ref_id}."}
            if kind == "invoice" and ref["status"] == "paid":
                return {"ok": False, "reason": "Invoice already paid."}
            owed = ref["amount"] if kind == "invoice" else ref["monthly_rent"]
            if round(amount, 2) != round(owed, 2):
                return {"ok": False, "reason": f"Amount must equal the amount owed (${owed:.2f})."}
            dup = conn.execute(
                "SELECT id FROM payment_requests WHERE kind = ? AND ref_id = ? AND status IN ('pending','approved')",
                (kind, ref_id)).fetchone()
            if dup:
                return {"ok": False, "reason": f"Request #{dup['id']} already open for this {kind}."}
            bal = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
            cur = conn.execute(
                "INSERT INTO payment_requests (kind, ref_id, amount, account, reason, requested_by, requested_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, ref_id, round(amount, 2), account, reason, requested_by, now_iso()))
            rid = cur.lastrowid
        audit("request_payment", request_id=rid, kind=kind, ref_id=ref_id, amount=amount, requested_by=requested_by)
        out = {"ok": True, "request_id": rid, "status": "pending",
               "note": "Waiting for human approval. Do not tell anyone this is paid."}
        if bal is not None and bal["balance"] < amount:
            out["warning"] = f"Cash ({bal['balance']:.2f}) is below this amount; it will be refused unless cash changes."
        return out

    @mcp.tool
    def pay(request_id: int) -> dict:
        """Execute a payment that a HUMAN has already approved. Refuses if not
        approved, already paid, or if cash is insufficient (no negative balances).
        Not given to any agent; human approval runs the same check."""
        return execute_payment(request_id)

    # ---- Drafts (never sent) -----------------------------------------------

    @mcp.tool
    def draft_message(to: str, subject: str, body: str, author: str,
                      audience: str = "customer", ticket_id: int | None = None) -> dict:
        """Save a DRAFT message on the board (audience: customer, landlord, vendor,
        internal). It is NEVER sent; no email or call is made. Drafts stay on the board."""
        if audience not in ("customer", "landlord", "vendor", "internal"):
            return {"ok": False, "reason": "audience must be customer, landlord, vendor, or internal."}
        if audience == "customer" and author != "customer_service":
            return {"ok": False, "reason": "Only customer_service drafts messages to customers."}
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO drafts (ticket_id, author, audience, to_name, subject, body, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (ticket_id, author, audience, to, subject, body, now_iso()))
            draft_id = cur.lastrowid
        audit("draft_message", draft_id=draft_id, ticket_id=ticket_id, author=author, audience=audience, to=to,
              subject=subject)
        return {"ok": True, "draft_id": draft_id, "sent": False,
                "note": "Saved on the board as a draft. Nothing was sent."}

    @mcp.tool
    def list_drafts(ticket_id: int | None = None) -> list[dict]:
        """Drafted messages on the board (none are ever sent)."""
        with db() as conn:
            if ticket_id is not None:
                return rows(conn.execute("SELECT * FROM drafts WHERE ticket_id = ? ORDER BY id", (ticket_id,)))
            return rows(conn.execute("SELECT * FROM drafts ORDER BY id"))

    # ---- Team coordination ---------------------------------------------------

    @mcp.tool
    def claim_task(ticket_id: int, task: str, agent: str) -> dict:
        """Claim a task on a ticket before doing it (e.g. 'request_payment:invoice:501',
        'draft_customer_reply'). Refuses if another agent already claimed it, so no
        work is duplicated. If you already claimed it, tells you so."""
        task = task.strip().lower()
        with db() as conn:
            row = conn.execute("SELECT * FROM task_claims WHERE ticket_id = ? AND task = ?",
                               (ticket_id, task)).fetchone()
            if row and row["agent"] == "boss" and agent != "boss":
                # The boss coordinates; it doesn't do the work. A specialist takes the task over.
                conn.execute("UPDATE task_claims SET agent = ?, status = 'claimed', result = NULL WHERE id = ?",
                             (agent, row["id"]))
                audit("claim_task_takeover", ticket_id=ticket_id, task=task, agent=agent, from_agent="boss")
                return {"ok": True, "claimed": task, "agent": agent, "note": "Taken over from the boss."}
            if row:
                mine = row["agent"] == agent
                return {"ok": mine, "already_claimed_by": row["agent"], "status": row["status"],
                        "result": row["result"],
                        "note": "You already own this task." if mine else "Another agent owns this task. Do not redo it."}
            conn.execute("INSERT INTO task_claims (ticket_id, task, agent, created_at) VALUES (?, ?, ?, ?)",
                         (ticket_id, task, agent, now_iso()))
        audit("claim_task", ticket_id=ticket_id, task=task, agent=agent)
        return {"ok": True, "claimed": task, "agent": agent}

    @mcp.tool
    def complete_task(ticket_id: int, task: str, agent: str, result: str) -> dict:
        """Mark a task you claimed as done, with a one-line result for the team."""
        task = task.strip().lower()
        with db() as conn:
            row = conn.execute("SELECT * FROM task_claims WHERE ticket_id = ? AND task = ?",
                               (ticket_id, task)).fetchone()
            if not row:
                return {"ok": False, "reason": "Task was never claimed."}
            if row["agent"] != agent:
                return {"ok": False, "reason": f"Task belongs to {row['agent']}."}
            conn.execute("UPDATE task_claims SET status = 'done', result = ? WHERE id = ?", (result, row["id"]))
        audit("complete_task", ticket_id=ticket_id, task=task, agent=agent, result=result)
        return {"ok": True}

    @mcp.tool
    def list_claims(ticket_id: int | None = None) -> list[dict]:
        """Who has claimed which tasks (check this before starting work)."""
        with db() as conn:
            if ticket_id is not None:
                return rows(conn.execute("SELECT * FROM task_claims WHERE ticket_id = ? ORDER BY id", (ticket_id,)))
            return rows(conn.execute("SELECT * FROM task_claims ORDER BY id"))

    @mcp.tool
    def post_note(ticket_id: int | None, agent: str, message: str, kind: str = "note") -> dict:
        """Post a note for the team on the board. kind 'note' shares info;
        kind 'escalation' asks the boss to break a tie or make a call."""
        if kind not in ("note", "escalation"):
            return {"ok": False, "reason": "kind must be 'note' or 'escalation'."}
        with db() as conn:
            cur = conn.execute("INSERT INTO team_notes (ticket_id, agent, kind, message, created_at) "
                               "VALUES (?, ?, ?, ?, ?)", (ticket_id, agent, kind, message, now_iso()))
        audit("post_note", note_id=cur.lastrowid, ticket_id=ticket_id, agent=agent, kind=kind)
        return {"ok": True, "note_id": cur.lastrowid}

    @mcp.tool
    def read_notes(ticket_id: int | None = None, kind: str | None = None) -> list[dict]:
        """Read team notes, escalations, flags, and decisions (optionally for one ticket)."""
        sql, args = "SELECT * FROM team_notes WHERE 1=1", []
        if ticket_id is not None:
            sql += " AND ticket_id = ?"; args.append(ticket_id)
        if kind:
            sql += " AND kind = ?"; args.append(kind)
        with db() as conn:
            return rows(conn.execute(sql + " ORDER BY id", args))

    @mcp.tool
    def flag_risk(ticket_id: int | None, agent: str, risk: str, severity: str = "medium") -> dict:
        """Flag anything that could harm the business (fraud, suspicious requests,
        selling below cost, cash running out, legal or safety issues) for a human."""
        if severity not in ("low", "medium", "high"):
            severity = "medium"
        with db() as conn:
            cur = conn.execute("INSERT INTO team_notes (ticket_id, agent, kind, message, severity, created_at) "
                               "VALUES (?, ?, 'flag', ?, ?, ?)", (ticket_id, agent, risk, severity, now_iso()))
        audit("flag_risk", note_id=cur.lastrowid, ticket_id=ticket_id, agent=agent, severity=severity, risk=risk)
        return {"ok": True, "flag_id": cur.lastrowid, "note": "Flagged for a human."}

    @mcp.tool
    def record_decision(ticket_id: int, agent: str, decision: str, rationale: str) -> dict:
        """BOSS ONLY: record the final call on a ticket (including tie-breaks)."""
        if agent != "boss":
            return {"ok": False, "reason": "Only the boss records final decisions."}
        with db() as conn:
            cur = conn.execute("INSERT INTO team_notes (ticket_id, agent, kind, message, created_at) "
                               "VALUES (?, 'boss', 'decision', ?, ?)",
                               (ticket_id, f"{decision} | Why: {rationale}", now_iso()))
        audit("record_decision", ticket_id=ticket_id, decision=decision, rationale=rationale)
        return {"ok": True, "decision_id": cur.lastrowid}

    @mcp.tool
    def get_board() -> dict:
        """One-call snapshot of the shop: today, cash, open tickets with their claims,
        notes and drafts, and everything waiting for a human."""
        with db() as conn:
            t = today(conn).isoformat()
            tickets = rows(conn.execute("SELECT * FROM tickets ORDER BY id"))
            for tk in tickets:
                tk["claims"] = rows(conn.execute("SELECT task, agent, status, result FROM task_claims "
                                                 "WHERE ticket_id = ?", (tk["id"],)))
                tk["notes"] = rows(conn.execute("SELECT agent, kind, message, severity FROM team_notes "
                                                "WHERE ticket_id = ? ORDER BY id", (tk["id"],)))
                tk["drafts"] = rows(conn.execute("SELECT id, author, audience, to_name, subject, body FROM drafts "
                                                 "WHERE ticket_id = ? ORDER BY id", (tk["id"],)))
                tk["shipped_so_far"] = shipped_qty(conn, tk["id"])
            return {
                "today": t,
                "cash": rows(conn.execute("SELECT * FROM cash_accounts")),
                "tickets": tickets,
                "waiting_for_human": {
                    "payments": rows(conn.execute("SELECT * FROM payment_requests WHERE status = 'pending'")),
                    "purchase_orders": rows(conn.execute("SELECT * FROM purchase_orders WHERE status = 'pending'")),
                    "promotions": rows(conn.execute("SELECT * FROM promotions WHERE status = 'pending'")),
                    "flags": rows(conn.execute("SELECT * FROM team_notes WHERE kind = 'flag'")),
                    "escalations": rows(conn.execute("SELECT * FROM team_notes WHERE kind = 'escalation'")),
                },
            }

    return mcp


# --------------------------------------------------------------------------
# Shared payment logic (used by the `pay` tool and by human approval)
# --------------------------------------------------------------------------

def execute_payment(request_id: int) -> dict:
    with db() as conn:
        r = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if not r:
            return {"ok": False, "reason": "No such payment request."}
        if r["status"] != "approved" or not r["decided_by"]:
            return {"ok": False, "reason": f"Refused: request is '{r['status']}'. Human approval is required."}
        acct = conn.execute("SELECT * FROM cash_accounts WHERE name = ?", (r["account"],)).fetchone()
        if not acct:
            return {"ok": False, "reason": f"Unknown account {r['account']}."}
        if acct["balance"] < r["amount"]:
            audit("pay_refused_insufficient_cash", request_id=request_id,
                  amount=r["amount"], balance=acct["balance"])
            return {"ok": False, "reason": "Refused: insufficient cash.",
                    "balance": acct["balance"], "amount": r["amount"]}
        d = today(conn)
        conn.execute("UPDATE cash_accounts SET balance = balance - ?, date = ? WHERE name = ?",
                     (r["amount"], d.isoformat(), r["account"]))
        cur = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, ?, ?, ?)",
            (r["kind"], r["ref_id"], r["amount"], r["account"], d.isoformat(), r["decided_by"]))
        if r["kind"] == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (r["ref_id"],))
        else:
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (r["ref_id"],)).fetchone()
            nxt = add_months(date.fromisoformat(lease["next_due"])).isoformat()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (nxt, r["ref_id"]))
        conn.execute("UPDATE payment_requests SET status = 'paid' WHERE id = ?", (request_id,))
        new_bal = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (r["account"],)).fetchone()["balance"]
        payment_id = cur.lastrowid
    audit("pay", request_id=request_id, payment_id=payment_id, kind=r["kind"], ref_id=r["ref_id"],
          amount=r["amount"], approved_by=r["decided_by"], new_balance=new_bal)
    return {"ok": True, "payment_id": payment_id, "amount": r["amount"],
            "approved_by": r["decided_by"], "new_balance": new_bal}


# --------------------------------------------------------------------------
# Human-only commands (NOT MCP tools)
# --------------------------------------------------------------------------

def reset_db() -> None:
    """Copy the original DB over the new DB. The original is only read."""
    shutil.copyfile(ORIGINAL_DB_PATH, DB_PATH)
    ensure_tables()
    audit("reset_db", source=ORIGINAL_DB_PATH.name, target=DB_PATH.name)
    print(f"Reset {DB_PATH.name} from {ORIGINAL_DB_PATH.name}.")


APPROVAL_TABLES = {"payment": "payment_requests", "po": "purchase_orders", "promo": "promotions"}


def decide(kind: str, item_id: int, approver: str, approve: bool) -> dict:
    """Human approval. Approving a payment also executes it (cash check applies);
    approving a purchase order turns it into an open vendor invoice."""
    ensure_tables()
    table = APPROVAL_TABLES[kind]
    with db() as conn:
        r = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
        if not r or r["status"] != "pending":
            return {"ok": False, "reason": f"{kind} #{item_id} is not pending."}
        conn.execute(f"UPDATE {table} SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                     ("approved" if approve else "rejected", approver, now_iso(), item_id))
        out = {"ok": True, "kind": kind, "id": item_id, "status": "approved" if approve else "rejected",
               "decided_by": approver}
        if approve and kind == "po":
            cur = conn.execute(
                "INSERT INTO invoices (vendor_id, amount, due_date, status, description) VALUES (?, ?, ?, 'open', ?)",
                (r["vendor_id"], r["amount"], (today(conn) + timedelta(days=conn.execute(
                    "SELECT lead_days FROM vendors WHERE id = ?", (r["vendor_id"],)).fetchone()[0])).isoformat(),
                 f"Reprint {r['sku']} {r['size']} x{r['qty']}. PO #{item_id}"))
            conn.execute("UPDATE purchase_orders SET invoice_id = ? WHERE id = ?", (cur.lastrowid, item_id))
            out["invoice_id"] = cur.lastrowid
    audit(f"{kind}_{out['status']}", item_id=item_id, approver=approver, source_detail="human")
    if approve and kind == "payment":
        out["payment"] = execute_payment(item_id)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Campus Customs MCP server")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("reset", help="Human: reset the new DB from the original")
    for verb in ("approve", "reject"):
        p = sub.add_parser(verb, help=f"Human: {verb} a pending payment, purchase order, or promotion")
        p.add_argument("kind", choices=sorted(APPROVAL_TABLES))
        p.add_argument("id", type=int)
        p.add_argument("approver")
    a = ap.parse_args()
    if a.cmd == "reset":
        reset_db()
    elif a.cmd in ("approve", "reject"):
        print(json.dumps(decide(a.kind, a.id, a.approver, a.cmd == "approve"), indent=2))
    else:
        ensure_tables()
        build_server().run(show_banner=False)


if __name__ == "__main__":
    sys.exit(main())
