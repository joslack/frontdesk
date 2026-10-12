"""Every change to a request after a customer has opened it, in one place.

The workers, the dispatcher and the review page each call these with a connection from frontdesk.db.connect.as_jobs.
A request's row in internal.requests is the record of where it stands; a worker's run on the jobs deployment is how
it moves. Each function here makes one move and writes it to internal.request_log.

A step of a worker can run more than once: the server runs a step again from its start when its worker died part
way. So every function that a worker calls can be called twice with the same arguments and leave one result.
"""

import json

# What a decision can be once a person has approved it. The first four are a refund request's; "answered" is any
# other request's, whose result is the team's answer.
ACTIONS = ("cash_refund", "account_credit", "deny", "no_action", "answered")
SUPPORT = ("agt_desk", "Quillstack Support")  # who a ticket message is from when a reviewer's own name is not on file


async def log(db, request: str, event: str, **detail) -> None:
    await db.execute("INSERT INTO internal.request_log (request_id, event, detail) VALUES ($1, $2, $3)",
                     request, event, json.dumps(detail, default=str))


async def get(db, request: str) -> dict:
    row = await db.fetchrow("SELECT * FROM internal.requests WHERE id = $1", request)
    if row is None:
        raise LookupError(f"There is no request {request}.")
    return dict(row)


def short(request) -> str:
    """The part of a request's id that the ids of its ticket, refund and credit are made from."""
    return str(request).replace("-", "")[:12]


async def file_ticket(db, request: str) -> None:
    """File a request as a support ticket in the customer's workspace, so that it is on their record with its
    answer. Filing twice leaves one ticket."""
    row = await get(db, request)
    ticket = f"tkt_{short(request)}"
    async with db.transaction():
        made = await db.fetchval("INSERT INTO tickets (id, workspace_id, subject, opened_by, opened_at, status) "
                                 "VALUES ($1, $2, $3, $4, $5, 'open') ON CONFLICT (id) DO NOTHING RETURNING id",
                                 ticket, row["workspace_id"], f"{row['kind'].replace('_', ' ').capitalize()}: {row['message'][:70]}",
                                 row["opened_by"], row["opened_at"])
        if made:
            name = await db.fetchval("SELECT name FROM members WHERE id = $1", row["opened_by"])
            await db.execute("INSERT INTO ticket_messages (ticket_id, author_type, author_id, author_name, at, body) "
                             "VALUES ($1, 'customer', $2, $3, $4, $5)", ticket, row["opened_by"], name, row["opened_at"], row["message"])
            await log(db, request, "filed", ticket=ticket)


async def ask(db, request: str, question: str) -> None:
    """Put a reviewer's question to the customer. The request waits until they answer."""
    async with db.transaction():
        changed = await db.fetchval("UPDATE internal.requests SET status = 'needs_information', question = $2, "
                                    "updated_at = now() WHERE id = $1 AND status = 'working' RETURNING opened_by",
                                    request, question)
        if changed:
            await log(db, request, "asked", question=question)
            await notify(db, changed, request, "A question about your request", question)


async def propose(db, request: str, round: int, proposal: dict, reviewed_by_policy: bool) -> None:
    """The worker's decision, for a person to review. With reviewed_by_policy the review setting lets this decision
    through, and it is recorded as approved by 'policy' with no person in between."""
    async with db.transaction():
        made = await db.fetchval("INSERT INTO internal.decisions (request_id, round, proposal) VALUES ($1, $2, $3) "
                                 "ON CONFLICT (request_id, round) DO NOTHING RETURNING id", request, round, json.dumps(proposal))
        if made is None:
            return
        await log(db, request, "proposed", round=round, action=proposal["action"], amount_cents=proposal["amount_cents"])
        if reviewed_by_policy:
            await db.execute("UPDATE internal.decisions SET reviewed_at = now(), reviewer = 'policy', review = 'approve', "
                             "final = $2 WHERE id = $1", made, json.dumps(final_of(proposal)))
        else:
            await db.execute("UPDATE internal.requests SET status = 'in_review', updated_at = now() WHERE id = $1", request)


def final_of(proposal: dict) -> dict:
    """The part of a proposal that is carried out and told to the customer."""
    return {"action": proposal["action"], "amount_cents": proposal["amount_cents"], "invoice_id": proposal.get("invoice_id") or None,
            "note": proposal["reply"]}


async def waiting_for_review(db) -> list[dict]:
    found = await db.fetch(
        "SELECT r.id, r.kind, r.opened_at, r.message, w.name AS workspace, m.name AS opened_by, m.role AS opened_by_role, "
        "d.round, d.proposal, d.proposed_at FROM internal.requests r JOIN workspaces w ON w.id = r.workspace_id "
        "JOIN members m ON m.id = r.opened_by JOIN internal.decisions d ON d.request_id = r.id AND d.review IS NULL "
        "WHERE r.status = 'in_review' ORDER BY d.proposed_at")
    return [dict(r) | {"proposal": json.loads(r["proposal"])} for r in found]


async def review(db, request: str, reviewer: str, review: str, final: dict | None = None, note_to_worker: str | None = None,
                 question: str | None = None) -> None:
    """A person's decision on what a worker proposed.

        approve    carry the proposal out as it is. An escalation cannot be approved: it is the worker handing the
                   decision to a person, so the person gives the decision with edit.
        edit       carry out `final` instead: action, amount_cents, invoice_id and the note for the customer
        send_back  decide again, with note_to_worker in front of the worker
        ask        put `question` to the customer, and decide again when they have answered
    """
    async with db.transaction():
        row = await db.fetchrow("SELECT d.id, d.proposal FROM internal.decisions d JOIN internal.requests r ON r.id = d.request_id "
                                "WHERE r.id = $1 AND r.status = 'in_review' AND d.review IS NULL FOR UPDATE OF r", request)
        if row is None:
            raise ValueError(f"Request {request} is not waiting for a review.")
        proposal = json.loads(row["proposal"])
        if review == "approve":
            if proposal["action"] == "escalate":
                raise ValueError("An escalation has no decision to approve. Give the decision with edit.")
            final = final_of(proposal)
        elif review == "edit":
            final = final_of(proposal) | (final or {})
            if final["action"] not in ACTIONS:
                raise ValueError(f"The action must be one of {', '.join(ACTIONS)}.")
            if final["action"] in ("cash_refund", "account_credit") and not final["amount_cents"] > 0:
                raise ValueError("A refund or a credit needs an amount.")
            if final["action"] == "cash_refund" and not final["invoice_id"]:
                raise ValueError("A cash refund needs the invoice it goes back to.")
        elif review == "send_back":
            if not note_to_worker:
                raise ValueError("Say why it goes back, for the worker to read.")
            final = None
        elif review == "ask":
            if not question:
                raise ValueError("Say what to ask the customer.")
            final = None
        else:
            raise ValueError("The review must be approve, edit, send_back or ask.")
        await db.execute("UPDATE internal.decisions SET reviewed_at = now(), reviewer = $2, review = $3, final = $4, "
                         "note_to_worker = $5, question = $6 WHERE id = $1",
                         row["id"], reviewer, review, json.dumps(final), note_to_worker, question)
        await db.execute("UPDATE internal.requests SET status = 'reviewed', resume = $2, updated_at = now() WHERE id = $1",
                         request, json.dumps({"review": review, "final": final, "note_to_worker": note_to_worker, "question": question}))
        await log(db, request, "reviewed", by=reviewer, review=review, final=final, note_to_worker=note_to_worker, question=question)
        await db.execute("SELECT pg_notify('requests', $1)", str(request))


async def carry_out(db, request: str, final: dict, basis: list[str]) -> None:
    """Do what was approved, and close the request: the refund or the credit, the result the customer reads, and a
    notice to the person who asked. All of it is one transaction, and the refund's id is made from the request's, so
    running this twice pays once."""
    async with db.transaction():
        row = await db.fetchrow("SELECT workspace_id, opened_by, kind, status FROM internal.requests WHERE id = $1 FOR UPDATE", request)
        if row["status"] == "done":
            return
        if final["action"] == "cash_refund":
            charge = await db.fetchval("SELECT charge_id FROM invoices WHERE id = $1 AND workspace_id = $2 AND charge_id IS NOT NULL",
                                       final["invoice_id"], row["workspace_id"])
            if charge is None:
                raise ValueError(f"Invoice {final['invoice_id']} is not a paid invoice of this workspace.")
            await db.execute("INSERT INTO refunds (id, workspace_id, charge_id, amount, created, reason, metadata) "
                             "VALUES ($1, $2, $3, $4, now(), 'requested_by_customer', $5) ON CONFLICT (id) DO NOTHING",
                             f"re_{short(request)}", row["workspace_id"], charge, final["amount_cents"],
                             json.dumps({"quillstack_request": str(request), "quillstack_basis": ",".join(basis)}))
        elif final["action"] == "account_credit":
            await db.execute("INSERT INTO credits (id, workspace_id, amount, created, description, metadata) "
                             "VALUES ($1, $2, $3, now(), $4, $5) ON CONFLICT (id) DO NOTHING",
                             f"cbtxn_{short(request)}", row["workspace_id"], -final["amount_cents"], "Credit for a refund request",
                             json.dumps({"quillstack_request": str(request), "quillstack_basis": ",".join(basis)}))
        elif final["action"] == "answered":
            ticket = f"tkt_{short(request)}"
            if not await db.fetchval("SELECT 1 FROM ticket_messages WHERE ticket_id = $1 AND author_type = 'support_agent'", ticket):
                await db.execute("INSERT INTO ticket_messages (ticket_id, author_type, author_id, author_name, at, body) "
                                 "VALUES ($1, 'support_agent', $2, $3, now(), $4)", ticket, *SUPPORT, final["note"])
                await db.execute("UPDATE tickets SET status = 'solved' WHERE id = $1", ticket)
        await db.execute("UPDATE internal.requests SET status = 'done', outcome = $2, amount_cents = $3, note = $4, "
                         "closed_at = now(), question = NULL, resume = NULL, updated_at = now() WHERE id = $1",
                         request, final["action"], final["amount_cents"], final["note"])
        await log(db, request, "done", **final)
        # A refund or a cancellation is decided. Anything else is answered.
        what = row["kind"].replace("_", " ") + ("" if row["kind"] in ("bug_report", "billing_question") else " request")
        subject = f"Quillstack has answered your {what}" if final["action"] == "answered" else f"Your {what} has been decided"
        await notify(db, row["opened_by"], request, subject, final["note"])


async def notify(db, person: str, request: str, subject: str, body: str) -> None:
    await db.execute("INSERT INTO internal.notices (person_id, request_id, subject, body) VALUES ($1, $2, $3, $4)",
                     person, request, subject, body)
    await db.execute("SELECT pg_notify('notices', $1)", person)
