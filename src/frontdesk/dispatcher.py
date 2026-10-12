"""The dispatcher: it moves each request between its row in the database and its worker's run on the jobs deployment.

    uv run --env-file .env python -m frontdesk.dispatcher

A customer's role can write a request row and nothing else. This is the one process that turns a row into work: it
holds the service identity that the jobs deployment accepts, and the customer-facing servers do not. It also mails
the notices the workers leave.

A request's thread on the jobs deployment has the request's id. Each second the dispatcher looks at every request
that is not finished and compares its row with its thread:

    the row says            the thread says        the dispatcher
    queued                  no thread              creates the thread and starts the worker's run
    answered or reviewed    waiting for that       resumes the run with the answer or the review
    working                 busy                   leaves it
    working                 failed                 starts a run that goes on from the last finished step, up to
                                                   MAX_ATTEMPTS times, each later than the one before; then marks the
                                                   request failed, which the customer reads as "delayed"
    working                 finished               marks the request failed: a finished run closes its own request

It holds the row's lock while it does this, and writes what it did before it lets go. If the dispatcher stops part
way, the row is as it was and the next pass compares again, so a step is never lost. A step may be made twice: a run
started twice is refused by the server while the first is in flight, and the workers' writes are made to bear it.

The server retries a run whose worker died. It does not retry a run whose step raised an error after the step's own
retries, such as a model provider that stays down. That case is the "failed" row of the table above.
"""

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage

from langgraph_sdk import get_client
from langgraph_sdk.errors import ConflictError, NotFoundError

from frontdesk import settings, signin
from frontdesk.db.connect import as_jobs
from frontdesk.jobs import ledger

log = logging.getLogger("frontdesk.dispatcher")
EVERY = 1.0  # seconds between passes
MAX_ATTEMPTS = 4  # runs one request gets after a failure before a person has to look
BACKOFF = 20  # seconds before the first new run; each later one waits twice as long
GRAPH = {"refund": "refund", "cancellation": "ticket", "bug_report": "ticket", "billing_question": "ticket", "support": "ticket"}
WAITS_FOR = {"answered": "answer", "reviewed": "review"}  # the row's status, and what the paused run must be waiting for
SHOWS = {"answer": "needs_information", "review": "in_review"}  # what a paused run is waiting for, and the status that says so


async def jobs():
    """The jobs deployment, called as the service. The token is renewed when it is near its end."""
    # api_key=None: the SDK would otherwise send this machine's LangSmith key to that server as x-api-key.
    return get_client(url=settings.JOBS_URL, api_key=None, headers={"Authorization": f"Bearer {await signin.as_service()}"})


async def thread_of(client, request: str) -> dict | None:
    try:
        return await client.threads.get(request)
    except NotFoundError:
        return None


def waiting_for(thread: dict) -> str | None:
    """What a paused run waits for: "answer" or "review"."""
    pending = [i for found in (thread.get("interrupts") or {}).values() for i in found]
    return pending[0]["value"].get("waiting_for") if pending else None


async def move(db, client, row: dict) -> None:
    """Compare one request's row with its thread and make the next move. The caller holds the row's lock."""
    request, graph = str(row["id"]), GRAPH[row["kind"]]
    thread = await thread_of(client, request)

    async def set_status(status: str, **more) -> None:
        columns = {"status": status, **more}
        await db.execute(f"UPDATE internal.requests SET {', '.join(f'{c} = ${i + 2}' for i, c in enumerate(columns))}, "
                         "updated_at = now() WHERE id = $1", row["id"], *columns.values())

    try:
        if thread is None:
            await client.threads.create(thread_id=request, if_exists="do_nothing", metadata={"request": request, "kind": row["kind"]})
            run = await client.runs.create(request, graph, input={"request_id": request}, multitask_strategy="reject")
            await set_status("working", run_id=run["run_id"])
            await ledger.log(db, request, "started", run=run["run_id"])
        elif thread["status"] == "busy":
            if row["status"] != "working":
                await set_status("working")
        elif thread["status"] == "interrupted":
            waits = waiting_for(thread)
            if WAITS_FOR.get(row["status"]) == waits:
                run = await client.runs.create(request, graph, command={"resume": json.loads(row["resume"])}, multitask_strategy="reject")
                await set_status("working", run_id=run["run_id"], resume=None)
                await ledger.log(db, request, "resumed", run=run["run_id"], with_the=waits)
            elif row["status"] != SHOWS.get(waits):
                # The run went on to its next stop and this row did not follow, which a dispatcher that stopped
                # between resuming a run and writing so leaves behind. The run is the one to believe.
                await set_status(SHOWS[waits], resume=None)
        elif thread["status"] == "error":
            error = json.dumps(thread.get("error"))[:1000] if thread.get("error") else "The run failed."
            if row["attempts"] + 1 >= MAX_ATTEMPTS:
                await set_status("failed", last_error=error)
                await ledger.log(db, request, "failed", error=error, attempts=row["attempts"] + 1)
                log.error("request %s failed after %s runs: %s", request, row["attempts"] + 1, error)
            elif row["last_error"] is None or row["try_again_at"] is None:
                wait = BACKOFF * 2 ** row["attempts"]
                await db.execute("UPDATE internal.requests SET last_error = $2, try_again_at = now() + make_interval(secs => $3), "
                                 "updated_at = now() WHERE id = $1", row["id"], error, float(wait))
                await ledger.log(db, request, "run_failed", error=error, next_run_in_seconds=wait)
            elif await db.fetchval("SELECT try_again_at <= now() FROM internal.requests WHERE id = $1", row["id"]):
                # input=None: the new run goes on from the last step that finished, not from the start.
                run = await client.runs.create(request, graph, input=None, multitask_strategy="reject")
                await set_status("working", run_id=run["run_id"], attempts=row["attempts"] + 1, try_again_at=None)
                await ledger.log(db, request, "started_again", run=run["run_id"], attempt=row["attempts"] + 2)
        elif thread["status"] == "idle" and row["status"] == "working" and row["run_id"]:
            run = await client.runs.get(request, row["run_id"])
            if run["status"] == "success":
                await set_status("failed", last_error="The run finished and did not close the request.")
            # A run that is still pending leaves its thread idle: nothing to do yet.
    except ConflictError:
        pass  # a run is already in flight on this thread; the next pass sees it


async def dispatch_once() -> int:
    """One pass over every request that is not finished. Returns how many it looked at."""
    client = await jobs()
    seen = 0
    async with as_jobs() as db:
        ids = await db.fetch("SELECT id FROM internal.requests WHERE status IN ('queued', 'answered', 'reviewed', 'working') "
                             "AND NOT on_hold ORDER BY updated_at")
        for found in ids:
            async with db.transaction():
                row = await db.fetchrow("SELECT * FROM internal.requests WHERE id = $1 AND NOT on_hold AND status IN "
                                        "('queued', 'answered', 'reviewed', 'working') FOR UPDATE SKIP LOCKED", found["id"])
                if row is not None:
                    await move(db, client, dict(row))
                    seen += 1
    return seen


def send(to: str, name: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = "Quillstack <desk@quillstack.example>", f"{name} <{to}>", subject
    message.set_content(f"Hello {name.split()[0]},\n\n{body}\n\nQuillstack\n")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        smtp.send_message(message)


async def mail_once() -> int:
    """Mail every notice that has not been mailed. A notice is marked as mailed in the transaction that sends it, so
    a failed send leaves it for the next pass."""
    sent = 0
    async with as_jobs() as db:
        while True:
            async with db.transaction():
                notice = await db.fetchrow("SELECT n.id, n.subject, n.body, m.email, m.name FROM internal.notices n "
                                           "JOIN members m ON m.id = n.person_id WHERE n.mailed_at IS NULL "
                                           "ORDER BY n.id LIMIT 1 FOR UPDATE OF n SKIP LOCKED")
                if notice is None:
                    return sent
                await asyncio.to_thread(send, notice["email"], notice["name"], notice["subject"], notice["body"])
                await db.execute("UPDATE internal.notices SET mailed_at = now() WHERE id = $1", notice["id"])
                sent += 1


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    log.info("dispatching to %s", settings.JOBS_URL)
    while True:
        for step in (dispatch_once, mail_once):
            try:
                await step()
            except Exception:  # the database or a server is away; the next pass tries again
                log.exception("%s failed", step.__name__)
        await asyncio.sleep(EVERY)


if __name__ == "__main__":
    asyncio.run(main())
