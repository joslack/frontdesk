"""The refund worker's tools: one for each kind of record, each returning it in the policy's own terms.

These are the tools refundo's structured agent was measured with (refundo, evals/environment/mcp/server.py), with
the same names, the same descriptions and the same results. There the tools were an MCP server over a database
that held one account. Here they are functions over a database that holds every workspace, so each one reads the
workspace of the request it is working on, as of the time the request was made. Which request that is comes from
the run and not from the model: a tool takes it from the Case the worker passes as the run's context.

They state facts: Amount Paid, Usage, and the role a person held at a given time. Which rule applies, and what it
grants, is left to the agent.

tests/test_refund_tools.py compares each tool's name, description and arguments with refundo's, when refundo is
checked out beside this repository.
"""

import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from frontdesk.db.connect import as_jobs

Action = Literal["cash_refund", "account_credit", "deny", "escalate", "no_action"]


@dataclass(frozen=True)
class Case:
    """The request a run of the worker is deciding."""

    workspace_id: str
    requester_id: str  # the person who opened the request
    received_at: str  # when they opened it, which is the policy's Request Time


async def rows(db, query: str, *args) -> list[dict]:
    """Rows as plain JSON values, with every time as text."""
    return json.loads(json.dumps([dict(r) for r in await db.fetch(query, *args)], default=str))


def when(value: str) -> datetime:
    """A timestamp. One with no time zone, such as a bare date, is read as UTC, as every record is."""
    at = datetime.fromisoformat(value)
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def parsed(value) -> dict:
    """A JSON column, which the database driver hands over as text."""
    return json.loads(value) if isinstance(value, str) else (value or {})


def narrowed(records: list[dict], at: str, since: str | None, until: str | None, limit: int) -> tuple[list[dict], dict]:
    """The records dated from `since` to `until`, cut to the newest `limit` of them and kept in the order given,
    with a count of what was left out, so the caller can tell that an account holds more than it was shown."""
    matched = [r for r in records if (since is None or when(r[at]) >= when(since))
               and (until is None or when(r[at]) <= when(until))]
    newest = sorted(matched, key=lambda r: when(r[at]))[-limit:] if limit > 0 else []
    kept = [r for r in matched if any(r is n for n in newest)]
    return kept, {"returned": len(kept), "matched_but_older_than_these": len(matched) - len(kept),
                  "on_the_account_in_all": len(records)}


def bad_range(since: str | None, until: str | None) -> str | None:
    """What to tell the caller if a timestamp cannot be read."""
    try:
        [when(value) for value in (since, until) if value]
    except ValueError:
        return "since and until must be timestamps such as 2026-03-01T00:00:00+00:00."
    return None


def role_then(member: dict | None, changes: list[dict], at: str) -> str | None:
    """The role a person held at a time: the current role, unwound through any later role changes. None if they
    were not a member then."""
    if member is None or when(at) < when(member["joined_at"]):
        return None
    if member["removed_at"] and when(at) >= when(member["removed_at"]):
        return None
    later = sorted((c for c in changes if parsed(c["data"]).get("user") == member["id"] and when(c["at"]) > when(at)
                    and "old_role" in parsed(c["data"])), key=lambda c: when(c["at"]))
    return parsed(later[0]["data"])["old_role"] if later else member["role"]


def charge_views(invoices: list[dict], lines: list[dict], refunds: list[dict], disputes: list[dict]) -> list[dict]:
    """Every charge, newest first, with its refunds and disputes."""
    out = []
    for inv in sorted(invoices, key=lambda i: when(i["created"]), reverse=True):
        refunded = [r for r in refunds if inv["charge_id"] and r["charge_id"] == inv["charge_id"]]
        out.append({
            "invoice_id": inv["id"], "charge_id": inv["charge_id"], "status": inv["status"],
            "charged_at": inv["created"],
            "kind": {"subscription_create": "first charge of a subscription", "subscription_cycle": "renewal",
                     "subscription_update": "plan change starting a new term", "manual": "manual"}[inv["billing_reason"]],
            "billing_period_start": inv["period_start"], "billing_period_end": inv["period_end"],
            "billing_period_days": (when(inv["period_end"]) - when(inv["period_start"])).days,
            "lines": [{"description": line["description"], "tier": line["tier"], "interval": line["interval"],
                       "seats": line["seats"], "list_price_cents": line["amount"]}
                      for line in lines if line["invoice_id"] == inv["id"]],
            "list_price_cents": inv["subtotal"], "discount_cents": inv["discount"],
            "account_credit_applied_cents": inv["credit_applied"],
            "amount_paid_cents": inv["amount_paid"] - inv["tax"],
            "tax_cents": inv["tax"], "charged_to_card_cents": inv["amount_paid"],
            "refunds": [{"refund_id": r["id"], "amount_cents": r["amount"], "refunded_at": r["created"], "reason": r["reason"],
                         "basis": parsed(r["metadata"]).get("quillstack_basis"),
                         "for_ticket": parsed(r["metadata"]).get("quillstack_ticket")} for r in refunded],
            "refunded_cents": sum(r["amount"] for r in refunded),
            "disputes": [{"dispute_id": d["id"], "status": d["status"], "amount_cents": d["amount"], "opened_at": d["created"],
                          "reason": d["reason"]} for d in disputes if inv["charge_id"] and d["charge_id"] == inv["charge_id"]],
        })
    return out


def usage_view(events: list[dict], since: str, until: str) -> dict:
    """Usage between two times, as the policy defines it: a session with a login followed by a create, edit or export."""
    sessions: dict[str, list[dict]] = {}
    for e in events:
        sessions.setdefault(e["session_id"], []).append(e)
    found, quiet = [], 0
    for session_id, in_session in sessions.items():
        logins = [when(e["at"]) for e in in_session if e["action"] == "login"]
        active = sorted(when(e["at"]) for e in in_session if e["action"] in {"create", "edit", "export"}
                        and logins and when(e["at"]) >= min(logins) and when(since) <= when(e["at"]) <= when(until))
        if active:
            found.append({"session_id": session_id, "user_id": in_session[0]["user_id"], "first_usage_at": str(active[0]),
                          "last_usage_at": str(active[-1])})
        elif any(when(since) <= when(e["at"]) <= when(until) for e in in_session):
            quiet += 1
    with_usage = {s["session_id"] for s in found}
    days = sorted({str(when(e["at"]).date()) for e in events if e["action"] in {"create", "edit", "export"}
                   and when(since) <= when(e["at"]) <= when(until) and e["session_id"] in with_usage})
    return {"since": since, "until": until, "sessions_with_usage": sorted(found, key=lambda s: s["first_usage_at"]),
            "days_with_usage": days, "sessions_without_usage": quiet}


async def people(db, workspace: str) -> tuple[dict[str, dict], list[dict]]:
    """The workspace's members by id, and its log of role changes."""
    members = {m["id"]: m for m in await rows(db, "SELECT * FROM members WHERE workspace_id = $1", workspace)}
    changes = await rows(db, "SELECT * FROM app_events WHERE workspace_id = $1 AND type = 'member_role_changed'", workspace)
    return members, changes


@tool
async def get_request_context(runtime: ToolRuntime[Case]) -> dict:
    """Who is asking, for which workspace, and when. This comes from the platform, not from the message."""
    case = runtime.context
    async with as_jobs() as db:
        member = await rows(db, "SELECT name FROM members WHERE id = $1", case.requester_id)
    return {"workspace_id": case.workspace_id, "requester_user_id": case.requester_id, "received_at": case.received_at,
            "channel": "chat", "requester_name": member[0]["name"] if member else None}


@tool
async def get_requester(runtime: ToolRuntime[Case]) -> dict:
    """The person asking and the role they hold in the workspace at the time of the request."""
    case = runtime.context
    async with as_jobs() as db:
        members, changes = await people(db, case.workspace_id)
    member = members.get(case.requester_id)
    if member is None:
        return {"user_id": case.requester_id, "member_of_workspace": False, "role": None}
    role = role_then(member, changes, case.received_at)
    return {"user_id": member["id"], "name": member["name"], "email": member["email"], "member_of_workspace": role is not None,
            "role": role, "joined_at": member["joined_at"], "removed_at": member["removed_at"]}


@tool
async def list_charges(runtime: ToolRuntime[Case], since: str | None = None, until: str | None = None, limit: int = 36) -> dict | str:
    """Charges on the account, newest first, each with the refunds and disputes against it.

    With no arguments this returns the 36 newest. An account can hold years of charges: the counts beside the
    charges say how many more there are. since and until are timestamps such as 2026-03-01T00:00:00+00:00 and
    select by the time of the charge; limit is how many to return, the newest of those selected.

    amount_paid_cents is the policy's Amount Paid: what was charged after discounts and applied account credit,
    before tax. charged_to_card_cents includes tax. All amounts are in cents.
    """
    if problem := bad_range(since, until):
        return problem
    workspace = runtime.context.workspace_id
    async with as_jobs() as db:
        every = charge_views(await rows(db, "SELECT * FROM invoices WHERE workspace_id = $1", workspace),
                             await rows(db, "SELECT * FROM invoice_lines WHERE workspace_id = $1", workspace),
                             await rows(db, "SELECT * FROM refunds WHERE workspace_id = $1", workspace),
                             await rows(db, "SELECT * FROM disputes WHERE workspace_id = $1", workspace))
    charges, counts = narrowed(every, "charged_at", since, until, limit)
    return {"charges": charges} | counts


@tool
async def get_subscription(runtime: ToolRuntime[Case]) -> dict:
    """The workspace, its plan over time, the payment processor's subscription record, and the app's log of
    cancellations, plan changes, seat changes and suspensions.

    A cancellation can be recorded in two places: the app's event log and the processor's `canceled_at`. Each
    event that a person caused carries the role that person held at that moment.
    """
    workspace_id = runtime.context.workspace_id
    async with as_jobs() as db:
        workspace = (await rows(db, "SELECT * FROM workspaces WHERE id = $1", workspace_id))[0]
        members, changes = await people(db, workspace_id)
        events = await rows(db, "SELECT * FROM app_events WHERE workspace_id = $1 ORDER BY at", workspace_id)
        subscription = await rows(db, "SELECT * FROM subscriptions WHERE workspace_id = $1", workspace_id)
        plans = await rows(db, 'SELECT tier, "interval", seats, effective_at FROM plan_history WHERE workspace_id = $1 '
                               "ORDER BY effective_at", workspace_id)
    return {
        "workspace": {k: workspace[k] for k in ("id", "name", "status", "suspension_reason", "created_at")},
        "plan_history": plans,
        "processor_subscription": {k: subscription[0][k] for k in ("status", "current_period_start", "current_period_end",
                                                                   "canceled_at")} if subscription else None,
        "app_events": [{"event_id": e["id"], "type": e["type"], "at": e["at"], "by_user_id": e["actor_user_id"],
                        "by_role_then": role_then(members.get(e["actor_user_id"]), changes, e["at"]),
                        "details": parsed(e["data"])} for e in events if e["type"] != "member_role_changed"],
    }


@tool
async def get_usage(since: str, runtime: ToolRuntime[Case], until: str | None = None) -> dict | str:
    """Usage between two times, as the policy defines it: a session with a login followed by at least one create,
    edit or export. Views alone are not Usage.

    since and until are timestamps such as 2026-03-01T00:00:00+00:00. until defaults to the time of the request.
    days_with_usage lists each calendar day that had Usage.
    """
    until = until or runtime.context.received_at
    try:
        when(since), when(until)
    except ValueError:
        return "since and until must be timestamps such as 2026-03-01T00:00:00+00:00."
    async with as_jobs() as db:
        events = await rows(db, "SELECT * FROM session_events WHERE workspace_id = $1", runtime.context.workspace_id)
    return usage_view(events, since, until)


@tool
async def list_tickets(runtime: ToolRuntime[Case], since: str | None = None, until: str | None = None, search: str | None = None,
                       limit: int = 10) -> dict | str:
    """Support tickets with their messages, oldest first. A message from a customer carries the role its author
    held in the workspace when they wrote it.

    With no arguments this returns the 10 newest. An account can hold years of tickets: the counts beside the
    tickets say how many more there are. since and until are timestamps such as 2026-03-01T00:00:00+00:00 and
    select by when the ticket was opened. search keeps the tickets whose subject or messages contain that text,
    in any letter case. limit is how many to return, the newest of those selected.
    """
    if problem := bad_range(since, until):
        return problem
    workspace = runtime.context.workspace_id
    async with as_jobs() as db:
        members, changes = await people(db, workspace)
        messages = await rows(db, "SELECT m.* FROM ticket_messages m JOIN tickets t ON t.id = m.ticket_id "
                                  "WHERE t.workspace_id = $1 ORDER BY m.at", workspace)
        tickets = await rows(db, "SELECT * FROM tickets WHERE workspace_id = $1 ORDER BY opened_at", workspace)
    found = [{"ticket_id": t["id"], "subject": t["subject"], "opened_by_user_id": t["opened_by"], "opened_at": t["opened_at"],
              "status": t["status"],
              "messages": [{"from": m["author_type"], "author_id": m["author_id"], "author_name": m["author_name"],
                            "author_role_then": role_then(members.get(m["author_id"]), changes, m["at"])
                            if m["author_type"] == "customer" else None,
                            "at": m["at"], "body": m["body"]} for m in messages if m["ticket_id"] == t["id"]]}
             for t in tickets]
    if search:
        found = [t for t in found if search.lower() in " ".join([t["subject"], *(m["body"] for m in t["messages"])]).lower()]
    kept, counts = narrowed(found, "opened_at", since, until, limit)
    return {"tickets": kept} | counts


@tool
async def list_account_credits(runtime: ToolRuntime[Case], since: str | None = None, until: str | None = None,
                               limit: int = 24) -> dict | str:
    """Changes to the customer's account credit balance, oldest first. A negative amount is credit given to the
    customer.

    With no arguments this returns the 24 newest; the counts beside them say how many more there are. since and
    until are timestamps such as 2026-03-01T00:00:00+00:00; limit is how many to return, the newest of those
    selected.
    """
    if problem := bad_range(since, until):
        return problem
    async with as_jobs() as db:
        found = await rows(db, "SELECT * FROM credits WHERE workspace_id = $1 ORDER BY created", runtime.context.workspace_id)
    every = [{"credit_id": c["id"], "amount_cents": c["amount"], "at": c["created"], "description": c["description"],
              "details": parsed(c["metadata"])} for c in found]
    credits, counts = narrowed(every, "at", since, until, limit)
    return {"account_credits": credits} | counts


class Proposal(BaseModel):
    action: Action
    amount_cents: int
    sections: list[str]
    rationale: str
    # The one argument refundo's tool does not have. A refund goes back to a charge, so the worker has to name it.
    invoice_id: str = Field(description="The invoice the amount is for, as invoice_id in the records. Empty when there is "
                                        "no amount.")


@tool(args_schema=Proposal)
async def submit_proposal(action: Action, amount_cents: int, sections: list[str], rationale: str, invoice_id: str) -> str:
    """Record your decision. Call this once, when you have decided.

    action:
      cash_refund     money back to the original payment method, in full or in part
      account_credit  credit on the account
      deny            the requester may ask, and no section of the policy grants a refund or credit
      escalate        a mandatory escalation condition holds
      no_action       the requester is not the Owner or a Billing Admin
    amount_cents is before tax. For an escalation it is the amount you would have proposed, or 0 if you would have
    proposed none.
    sections are the policy sections the decision rests on, such as ["5"] or ["4.2", "11"].
    """
    # The worker reads the decision from this call and puts it in front of a reviewer. Nothing is written here.
    return "Recorded."


TOOLS = [get_request_context, get_requester, list_charges, get_subscription, get_usage, list_tickets, list_account_credits,
         submit_proposal]
# refundo's MCP server gave the model each description with the source's indentation taken off, so these do too.
for _tool in TOOLS:
    _tool.description = inspect.cleandoc(_tool.description)
