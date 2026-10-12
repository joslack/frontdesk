"""The command line: talk to the desk as a customer, and review as Quillstack.

    uv run --env-file .env frontdesk chat dana                 a conversation with the desk agent, signed in as dana
    uv run --env-file .env frontdesk chat dana "a question"    one turn, then exit
    uv run --env-file .env frontdesk review lena               what waits for a person, oldest first, and decide each one
    uv run --env-file .env frontdesk review lena 3ca5          only the request whose id starts with 3ca5
    uv run --env-file .env frontdesk requests                  every request and where it stands, as Quillstack sees it
    uv run --env-file .env frontdesk token dana                dana's token, for a tool that wants one

Each demo person signs in with the demo password in .env. The people are in frontdesk/people.py.
"""

import argparse
import asyncio
import json
import sys

from langgraph_sdk import get_client

from frontdesk import settings, signin
from frontdesk.db.connect import as_jobs
from frontdesk.jobs import ledger
from frontdesk.models import text
from frontdesk.people import BY_USERNAME, REVIEWERS

DIM, BOLD, OFF = "\033[2m", "\033[1m", "\033[0m"


async def chat(username: str, first: str | None) -> None:
    """A conversation with the desk agent on the conversation deployment. Each tool the agent calls is shown."""
    who = BY_USERNAME[username]

    async def desk():
        return get_client(url=settings.DESK_URL, api_key=None, headers={"Authorization": f"Bearer {await signin.as_person(username)}"})

    thread = await (await desk()).threads.create()
    print(f"{DIM}{who.name}, {who.role} of {who.workspace}. Thread {thread['thread_id']}. Ctrl-D ends.{OFF}")
    while True:
        try:
            said = first or await asyncio.to_thread(input, f"\n{BOLD}{username}>{OFF} ")
        except EOFError:
            return
        if said.strip():
            async for part in (await desk()).runs.stream(thread["thread_id"], "desk", input={"messages": [{"role": "user", "content": said}]},
                                                         stream_mode="updates"):
                if part.event == "error":
                    print(f"error: {part.data}")
                for update in (part.data or {}).values() if part.event == "updates" else []:
                    for message in (update or {}).get("messages", []) if isinstance(update, dict) else []:
                        show(message)
        if first:
            return


def show(message: dict) -> None:
    kind = message.get("type")
    if kind == "ai":
        for call in message.get("tool_calls") or []:
            print(f"{DIM}  -> {call['name']}({json.dumps(call['args'])[:300]}){OFF}")
        if said := text(message.get("content")).strip():
            print(f"\n{said}")
    elif kind == "tool":
        print(f"{DIM}  <- {text(message.get('content')).strip()[:300]}{OFF}")
    elif kind == "human" and "<quillstack_notices>" in text(message.get("content")):
        print(f"{DIM}  (notices from Quillstack were put in front of the agent){OFF}")


async def review(reviewer: str, only: str | None = None) -> None:
    """Show each proposal that waits for a person, and record what the reviewer decides. `only` is the start of
    one request's id."""
    if reviewer not in REVIEWERS:
        sys.exit(f"{reviewer} is not a reviewer. The reviewers are {', '.join(REVIEWERS)}.")
    async with as_jobs() as db:
        waiting = [w for w in await ledger.waiting_for_review(db) if str(w["id"]).startswith(only or "")]
        if not waiting:
            print("Nothing waits for a review." if not only else f"No request that starts with {only} waits for a review.")
        for item in waiting:
            proposal = item["proposal"]
            print(f"\n{BOLD}{item['kind']} request {item['id']}{OFF}  {item['workspace']}, {item['opened_by']} ({item['opened_by_role']})")
            print(f"  The customer wrote: {item['message']}")
            print(f"  Proposed: {BOLD}{proposal['action']}{OFF} ${proposal['amount_cents'] / 100:,.2f}"
                  f"  sections {', '.join(proposal['sections']) or '-'}  invoice {proposal.get('invoice_id') or '-'}")
            print(f"  Why: {proposal['rationale']}")
            print(f"  Reply to the customer: {proposal['reply']}")
            try:
                choice = (await asyncio.to_thread(input, "  [a]pprove, [e]dit, [s]end back, [q]uestion for the customer, or Enter to leave it: ")).strip().lower()
            except EOFError:
                return
            try:
                if choice == "a":
                    await ledger.review(db, item["id"], reviewer, "approve")
                elif choice == "e":
                    action = await asyncio.to_thread(input, f"    action ({', '.join(ledger.ACTIONS)}): ")
                    dollars = await asyncio.to_thread(input, "    amount in dollars: ")
                    invoice = await asyncio.to_thread(input, f"    invoice [{proposal.get('invoice_id') or 'none'}]: ")
                    note = await asyncio.to_thread(input, "    note to the customer: ")
                    await ledger.review(db, item["id"], reviewer, "edit", {
                        "action": action.strip(), "amount_cents": round(float(dollars or 0) * 100),
                        "invoice_id": invoice.strip() or proposal.get("invoice_id") or None, "note": note.strip() or proposal["reply"]})
                elif choice == "s":
                    await ledger.review(db, item["id"], reviewer, "send_back",
                                        note_to_worker=await asyncio.to_thread(input, "    what should the worker look at again: "))
                elif choice == "q":
                    await ledger.review(db, item["id"], reviewer, "ask",
                                        question=await asyncio.to_thread(input, "    what to ask the customer: "))
                else:
                    continue
                print("  Recorded.")
            except ValueError as e:
                print(f"  Not recorded: {e}")


async def requests() -> None:
    async with as_jobs() as db:
        found = await db.fetch("SELECT r.id, r.kind, r.status, r.attempts, r.outcome, r.amount_cents, r.opened_at, m.name, r.last_error "
                               "FROM internal.requests r JOIN members m ON m.id = r.opened_by ORDER BY r.opened_at DESC LIMIT 30")
    for r in found:
        result = f"{r['outcome']} ${(r['amount_cents'] or 0) / 100:,.2f}" if r["outcome"] else ""
        print(f"{r['opened_at']:%m-%d %H:%M}  {str(r['id'])[:8]}  {r['kind']:<16} {r['status']:<18} {r['name']:<16} {result}"
              + (f"  runs: {r['attempts'] + 1}  {r['last_error'][:80]}" if r["last_error"] else ""))


def main() -> None:
    parser = argparse.ArgumentParser(prog="frontdesk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    talk = commands.add_parser("chat")
    talk.add_argument("username", choices=sorted(BY_USERNAME))
    talk.add_argument("message", nargs="?")
    look = commands.add_parser("review")
    look.add_argument("reviewer")
    look.add_argument("request", nargs="?")
    commands.add_parser("requests")
    commands.add_parser("token").add_argument("username")
    args = parser.parse_args()
    if args.command == "chat":
        asyncio.run(chat(args.username, args.message))
    elif args.command == "review":
        asyncio.run(review(args.reviewer, args.request))
    elif args.command == "requests":
        asyncio.run(requests())
    else:
        print(asyncio.run(signin.as_person(args.username)))


if __name__ == "__main__":
    main()
