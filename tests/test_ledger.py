"""How a request moves once it is open: what a reviewer may record, and that a step done twice leaves one result.

    uv run --env-file .env pytest tests/test_ledger.py

These need the cluster's Postgres and a seed. They call the ledger as a worker and a reviewer would, with no
worker run and no model. Each test opens its own request and removes it afterwards.
"""

import json

import pytest

from frontdesk.db.connect import as_admin, as_jobs, as_person
from frontdesk.jobs import ledger

PROPOSAL = {"action": "cash_refund", "amount_cents": 8000, "sections": ["5"], "rationale": "Within 7 days and unused.",
            "invoice_id": "in_acme_008", "reply": "We have refunded the renewal in full."}


@pytest.fixture
async def request_id():
    # The cluster's dispatcher is running and would hand a new request to a worker. The request is made with
    # the hold already on, as the workers' role, so that only this test moves it.
    async with as_jobs() as db:
        made = str(await db.fetchval("INSERT INTO internal.requests (workspace_id, kind, opened_by, message, status, on_hold) "
                                     "VALUES ('ws_acme', 'refund', 'usr_priya', 'Please refund the last renewal.', 'working', true) "
                                     "RETURNING id"))
    yield made
    async with as_admin() as db:  # the workers' role can add a refund and cannot take one away
        for table in ("internal.notices", "internal.request_log", "internal.decisions"):
            await db.execute(f"DELETE FROM {table} WHERE request_id = $1", made)
        await db.execute("DELETE FROM refunds WHERE metadata->>'quillstack_request' = $1", made)
        await db.execute("DELETE FROM credits WHERE metadata->>'quillstack_request' = $1", made)
        await db.execute("DELETE FROM internal.requests WHERE id = $1", made)


async def status(db, request: str) -> str:
    return (await ledger.get(db, request))["status"]


async def test_a_proposal_waits_for_a_person_and_proposing_twice_makes_one(request_id):
    async with as_jobs() as db:
        await ledger.propose(db, request_id, 0, PROPOSAL, reviewed_by_policy=False)
        await ledger.propose(db, request_id, 0, PROPOSAL, reviewed_by_policy=False)
        assert await status(db, request_id) == "in_review"
        assert await db.fetchval("SELECT count(*) FROM internal.decisions WHERE request_id = $1", request_id) == 1
        assert [str(w["id"]) for w in await ledger.waiting_for_review(db)].count(request_id) == 1


async def test_an_approval_is_handed_to_the_worker_and_cannot_be_given_twice(request_id):
    async with as_jobs() as db:
        await ledger.propose(db, request_id, 0, PROPOSAL, reviewed_by_policy=False)
        await ledger.review(db, request_id, "lena", "approve")
        row = await ledger.get(db, request_id)
        assert row["status"] == "reviewed"
        assert json.loads(row["resume"])["final"] == ledger.final_of(PROPOSAL)
        with pytest.raises(ValueError, match="not waiting for a review"):
            await ledger.review(db, request_id, "omar", "approve")


async def test_an_escalation_cannot_be_approved_and_an_edit_has_to_be_complete(request_id):
    async with as_jobs() as db:
        await ledger.propose(db, request_id, 0, PROPOSAL | {"action": "escalate"}, reviewed_by_policy=False)
        with pytest.raises(ValueError, match="no decision to approve"):
            await ledger.review(db, request_id, "lena", "approve")
        with pytest.raises(ValueError, match="needs an amount"):
            await ledger.review(db, request_id, "lena", "edit", {"action": "account_credit", "amount_cents": 0})
        with pytest.raises(ValueError, match="must be one of"):
            await ledger.review(db, request_id, "lena", "edit", {"action": "escalate"})
        with pytest.raises(ValueError, match="Say why"):
            await ledger.review(db, request_id, "lena", "send_back")
        assert await status(db, request_id) == "in_review"
        await ledger.review(db, request_id, "lena", "edit", {"action": "deny", "amount_cents": 0, "note": "We cannot refund this charge."})
        assert json.loads((await ledger.get(db, request_id))["resume"])["final"]["action"] == "deny"


async def test_a_reviewer_s_question_is_handed_to_the_worker(request_id):
    async with as_jobs() as db:
        await ledger.propose(db, request_id, 0, PROPOSAL, reviewed_by_policy=False)
        with pytest.raises(ValueError, match="what to ask"):
            await ledger.review(db, request_id, "lena", "ask")
        await ledger.review(db, request_id, "lena", "ask", question="Which charge do you mean?")
        row = await ledger.get(db, request_id)
        assert row["status"] == "reviewed"
        assert json.loads(row["resume"]) == {"review": "ask", "final": None, "note_to_worker": None,
                                             "question": "Which charge do you mean?"}


async def test_carrying_out_a_refund_twice_pays_once(request_id):
    final = ledger.final_of(PROPOSAL)
    async with as_jobs() as db:
        await ledger.carry_out(db, request_id, final, ["5"])
        await ledger.carry_out(db, request_id, final, ["5"])
        paid = await db.fetch("SELECT amount, charge_id FROM refunds WHERE metadata->>'quillstack_request' = $1", request_id)
        assert [(r["amount"], r["charge_id"]) for r in paid] == [(8000, "ch_acme_008")]
        assert await db.fetchval("SELECT count(*) FROM internal.notices WHERE request_id = $1", request_id) == 1
    # The customer reads the result and the note, and nothing of the reasoning.
    async with as_person("usr_priya") as db:
        seen = dict(await db.fetchrow("SELECT * FROM requests WHERE id = $1", request_id))
    assert (seen["status"], seen["outcome"], seen["amount_cents"], seen["note"]) == ("done", "cash_refund", 8000, PROPOSAL["reply"])
    assert "rationale" not in seen and "sections" not in seen


async def test_a_refund_cannot_go_to_another_workspace_s_invoice(request_id):
    async with as_jobs() as db:
        with pytest.raises(ValueError, match="not a paid invoice of this workspace"):
            await ledger.carry_out(db, request_id, ledger.final_of(PROPOSAL | {"invoice_id": "in_cobalt_003"}), ["5"])
        assert await status(db, request_id) == "working"


async def test_a_question_reaches_the_customer_and_their_answer_reaches_the_worker(request_id):
    async with as_jobs() as db:
        await ledger.ask(db, request_id, "Which charge do you mean?")
    async with as_person("usr_priya") as db:
        seen = await db.fetchrow("SELECT status, question FROM requests WHERE id = $1", request_id)
        assert (seen["status"], seen["question"]) == ("needs_information", "Which charge do you mean?")
        await db.execute("SELECT answer_request($1, 'The renewal on the 9th.')", request_id)
        assert await db.fetchval("SELECT status FROM requests WHERE id = $1", request_id) == "working"
    async with as_jobs() as db:
        row = await ledger.get(db, request_id)
        assert row["status"] == "answered" and json.loads(row["resume"])["answer"] == "The renewal on the 9th."
