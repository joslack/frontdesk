"""What a person asks Quillstack to do, and what Quillstack tells them back.

A request is a row the person's own database role writes through a function that checks who they are. From there
the dispatcher hands it to a worker on the jobs deployment, and this module only reads how far it has come: the
view public.requests, which holds the status, a question for the customer if there is one, and the approved result,
and none of the worker's reasoning.
"""

import uuid

import asyncpg

from frontdesk.access.records import Refused
from frontdesk.db.connect import as_person

KINDS = {
    "refund": "money back or account credit for a charge. A person at Quillstack reviews the decision.",
    "cancellation": "end the subscription.",
    "bug_report": "something in the product does not work as it should.",
    "billing_question": "a question about a charge or an invoice that the records do not answer.",
    "support": "any other question for Quillstack's support team.",
}
NEXT = {
    "queued": "Quillstack has the request and has not started on it yet.",
    "working": "Quillstack is working on it.",
    "needs_information": "Quillstack needs an answer to `question` before it can go on. Answer with answer_request.",
    "in_review": "A person at Quillstack is reviewing it.",
    "done": "It is decided. `outcome`, `amount_cents` and `note` are the result, which a person approved.",
    "delayed": "It is taking longer than usual. Quillstack's team has been told.",
}


def shown(row) -> dict:
    out = {k: (str(v) if isinstance(v, uuid.UUID) or hasattr(v, "isoformat") else v) for k, v in dict(row).items() if v is not None}
    return out | {"what_happens_next": NEXT[out["status"]]}


async def open(person: str, kind: str, message: str) -> dict:
    try:
        async with as_person(person) as db:
            made = await db.fetchval("SELECT open_request($1, $2)", kind, message)
            return shown(await db.fetchrow("SELECT * FROM requests WHERE id = $1", made))
    except asyncpg.PostgresError as e:
        raise Refused(str(e)) from e


async def listed(person: str, open_only: bool) -> list[dict]:
    async with as_person(person) as db:
        found = await db.fetch("SELECT * FROM requests WHERE ($1 IS FALSE OR status <> 'done') ORDER BY opened_at DESC LIMIT 50",
                               open_only)
    return [shown(r) for r in found]


async def get(person: str, request: str) -> dict:
    async with as_person(person) as db:
        row = await db.fetchrow("SELECT * FROM requests WHERE id = $1", as_id(request))
    if row is None:
        raise Refused(f"There is no request {request} that you can read.")
    return shown(row)


async def answer(person: str, request: str, text: str) -> dict:
    try:
        async with as_person(person) as db:
            await db.execute("SELECT answer_request($1, $2)", as_id(request), text)
            return shown(await db.fetchrow("SELECT * FROM requests WHERE id = $1", as_id(request)))
    except asyncpg.PostgresError as e:
        raise Refused(str(e)) from e


async def notices(person: str) -> list[dict]:
    """The person's unread notices. Reading them marks them as read."""
    async with as_person(person) as db:
        found = await db.fetch("SELECT * FROM take_notices()")
    return [{"sent_at": str(n["created_at"]), "about_request": str(n["request_id"]) if n["request_id"] else None,
             "subject": n["subject"], "body": n["body"]} for n in found]


def as_id(request: str) -> uuid.UUID:
    try:
        return uuid.UUID(request)
    except ValueError as e:
        raise Refused(f"{request!r} is not a request id.") from e
