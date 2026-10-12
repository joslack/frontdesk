"""The refund worker's steps around the agent: review, a question for the customer, sending back, carrying out.

    uv run --env-file .env pytest tests/test_refund_worker.py

The agent that decides is replaced by one that always proposes the same refund, so no model is called. What is
tested is everything else: that a run stops for a person, that each of the reviewer's four choices leads where it
should, and what the customer and the records hold at the end. The test plays the dispatcher's part by hand: it
marks the request as working and resumes the run with what the row holds. It needs the cluster's Postgres and a
seed.
"""

import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from frontdesk.db.connect import as_admin, as_jobs, as_person
from frontdesk.jobs import ledger, refund

DECISION = {"action": "cash_refund", "amount_cents": 8000, "sections": ["5"], "rationale": "Within 7 days and unused.",
            "invoice_id": "in_acme_008"}


class AlwaysRefunds:
    """Stands in for the structured agent: it records what it was told and proposes the same refund each time."""

    def __init__(self):
        self.heard = []

    async def ainvoke(self, given, context):
        self.heard.append(([m.content for m in given["messages"]], context))
        return {"messages": [*given["messages"],
                             AIMessage("", tool_calls=[{"name": "submit_proposal", "args": DECISION, "id": "call_1"}]),
                             ToolMessage("Recorded.", tool_call_id="call_1"),
                             AIMessage("We have refunded the renewal in full.")]}


@pytest.fixture
async def run(monkeypatch):
    """A request on hold, the worker's graph, and a function that resumes the run as the dispatcher would."""
    agent = AlwaysRefunds()
    monkeypatch.setattr(refund, "_agent", agent)
    async with as_jobs() as db:
        request = str(await db.fetchval(
            "INSERT INTO internal.requests (workspace_id, kind, opened_by, message, status, on_hold) "
            "VALUES ('ws_acme', 'refund', 'usr_priya', 'Please refund the last renewal.', 'working', true) RETURNING id"))
    graph = refund.builder.compile(checkpointer=InMemorySaver())
    thread = {"configurable": {"thread_id": request}}

    async def resume():
        async with as_jobs() as db:
            row = await ledger.get(db, request)
            await db.execute("UPDATE internal.requests SET status = 'working', resume = NULL WHERE id = $1", request)
        return await graph.ainvoke(Command(resume=json.loads(row["resume"])), thread)

    yield request, agent, await graph.ainvoke({"request_id": request}, thread), resume
    async with as_admin() as db:
        for table in ("internal.notices", "internal.request_log", "internal.decisions"):
            await db.execute(f"DELETE FROM {table} WHERE request_id = $1", request)
        await db.execute("DELETE FROM refunds WHERE metadata->>'quillstack_request' = $1", request)
        await db.execute("DELETE FROM internal.requests WHERE id = $1", request)


def waiting_for(state) -> str:
    return state["__interrupt__"][0].value["waiting_for"]


async def test_the_agent_is_told_who_is_asking_by_the_run_and_the_run_stops_for_a_person(run):
    request, agent, state, _ = run
    said, case = agent.heard[0]
    assert said == ["Please refund the last renewal."]
    assert (case.workspace_id, case.requester_id) == ("ws_acme", "usr_priya")
    assert waiting_for(state) == "review"
    assert state["__interrupt__"][0].value["proposal"] == DECISION | {"reply": "We have refunded the renewal in full."}
    async with as_jobs() as db:
        assert (await ledger.get(db, request))["status"] == "in_review"
        assert await db.fetchval("SELECT count(*) FROM refunds WHERE metadata->>'quillstack_request' = $1", request) == 0


async def test_an_approval_issues_the_refund_and_tells_the_customer(run):
    request, _, _, resume = run
    async with as_jobs() as db:
        await ledger.review(db, request, "lena", "approve")
    await resume()
    async with as_person("usr_priya") as db:
        seen = await db.fetchrow("SELECT status, outcome, amount_cents, note FROM requests WHERE id = $1", request)
        refund_row = await db.fetchrow("SELECT amount, charge_id FROM refunds WHERE metadata->>'quillstack_request' = $1", request)
    assert tuple(seen) == ("done", "cash_refund", 8000, "We have refunded the renewal in full.")
    assert tuple(refund_row) == (8000, "ch_acme_008")


async def test_a_reviewer_s_change_is_what_is_carried_out(run):
    request, _, _, resume = run
    async with as_jobs() as db:
        await ledger.review(db, request, "lena", "edit", {"action": "deny", "amount_cents": 0, "note": "We cannot refund this charge."})
    await resume()
    async with as_jobs() as db:
        row = await ledger.get(db, request)
        assert (row["status"], row["outcome"], row["note"]) == ("done", "deny", "We cannot refund this charge.")
        assert await db.fetchval("SELECT count(*) FROM refunds WHERE metadata->>'quillstack_request' = $1", request) == 0


async def test_a_decision_sent_back_is_decided_again_with_the_reviewer_s_note(run):
    request, agent, _, resume = run
    async with as_jobs() as db:
        await ledger.review(db, request, "lena", "send_back", note_to_worker="Check the usage again.")
    state = await resume()
    assert waiting_for(state) == "review"
    assert "Check the usage again." in agent.heard[1][0][1]
    async with as_jobs() as db:
        assert [r["round"] for r in await db.fetch("SELECT round FROM internal.decisions WHERE request_id = $1 ORDER BY round", request)] == [0, 1]


async def test_a_reviewer_s_question_goes_to_the_customer_and_the_answer_comes_back_to_the_agent(run):
    request, agent, _, resume = run
    async with as_jobs() as db:
        await ledger.review(db, request, "lena", "ask", question="Which charge do you mean?")
    assert waiting_for(await resume()) == "answer"
    async with as_person("usr_priya") as db:
        seen = await db.fetchrow("SELECT status, question FROM requests WHERE id = $1", request)
        assert tuple(seen) == ("needs_information", "Which charge do you mean?")
        await db.execute("SELECT answer_request($1, 'The renewal on the 9th.')", request)
    assert waiting_for(await resume()) == "review"
    assert agent.heard[1][0] == ["Please refund the last renewal.\n\n[Asked: Which charge do you mean?]\nThe renewal on the 9th."]
