"""What each role reads, checked against the seeded database by signing in as the person.

    uv run --env-file .env pytest tests/test_access_rules.py

These need the cluster's Postgres and a seed (python -m frontdesk.db.seed). Each test asks the database a question
as one person and checks the answer; nothing here goes through the access server or a model.
"""

import asyncpg
import pytest

from frontdesk.db.connect import as_person
from frontdesk.people import db_role

BILLING_TABLES = ["subscriptions", "invoices", "invoice_lines", "refunds", "credits", "disputes", "app_events"]


async def ask(person: str, query: str, *args):
    async with as_person(f"usr_{person}") as db:
        async with db.transaction(readonly=True):
            return await db.fetch(query, *args)


async def value(person: str, query: str, *args):
    return (await ask(person, query, *args))[0][0]


async def test_a_person_is_who_signed_in():
    me = (await ask("priya", "SELECT * FROM me"))[0]
    assert (me["person_id"], me["role"], me["workspace_id"]) == ("usr_priya", "billing_admin", "ws_acme")


@pytest.mark.parametrize("person", ["dana", "priya", "marcus"])
async def test_no_one_reads_another_workspace(person):
    assert await value(person, "SELECT count(*) FROM members WHERE workspace_id <> 'ws_acme'") == 0
    assert await value(person, "SELECT count(*) FROM session_events WHERE workspace_id <> 'ws_acme'") == 0
    assert await value(person, "SELECT count(*) FROM tickets WHERE workspace_id <> 'ws_acme'") == 0
    assert await value(person, "SELECT count(*) FROM workspaces") == 1


@pytest.mark.parametrize("table", BILLING_TABLES)
async def test_a_member_reads_no_billing_table(table):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await ask("marcus", f"SELECT count(*) FROM {table}")


@pytest.mark.parametrize("person", ["dana", "priya"])
async def test_owner_and_billing_admin_read_their_workspace_s_invoices(person):
    assert await value(person, "SELECT count(*) FROM invoices") == 8
    assert await value(person, "SELECT sum(amount_paid) FROM invoices") == 8 * 8000
    assert await value(person, "SELECT count(*) FROM invoices WHERE workspace_id <> 'ws_acme'") == 0


async def test_a_member_reads_their_own_tickets_and_activity_only():
    assert {r[0] for r in await ask("marcus", "SELECT DISTINCT opened_by FROM tickets")} == {"usr_marcus"}
    assert {r[0] for r in await ask("marcus", "SELECT DISTINCT user_id FROM session_events")} == {"usr_marcus"}
    # His tickets' messages are his own and support's, and no other customer's.
    assert {r[0] for r in await ask("marcus", "SELECT DISTINCT author_id FROM ticket_messages WHERE author_type = 'customer'")} == {"usr_marcus"}


async def test_a_billing_admin_reads_their_own_tickets_and_activity_only():
    assert {r[0] for r in await ask("priya", "SELECT DISTINCT opened_by FROM tickets")} == {"usr_priya"}
    assert {r[0] for r in await ask("priya", "SELECT DISTINCT user_id FROM session_events")} == {"usr_priya"}


async def test_the_owner_reads_everyone_s_tickets_and_activity():
    assert await value("dana", "SELECT count(DISTINCT opened_by) FROM tickets") == 3
    assert await value("dana", "SELECT count(DISTINCT user_id) FROM session_events") == 4


async def test_usage_totals_are_for_billing_admin_and_owner_and_leave_out_days_with_few_people():
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await ask("marcus", "SELECT * FROM usage_daily")
    days = await ask("priya", "SELECT * FROM usage_daily")
    assert days and all(d["people_active"] >= 3 for d in days)
    # The owner counts the same days from the rows themselves, and some days had fewer than three people.
    every_day = await value("dana", "SELECT count(DISTINCT (at AT TIME ZONE 'UTC')::date) FROM session_events")
    assert len(days) < every_day
    assert len(days) == len(await ask("dana", "SELECT * FROM usage_daily"))


async def test_a_member_does_not_read_the_workspace_s_billing_columns():
    assert (await ask("marcus", "SELECT name, status FROM workspaces"))[0]["name"] == "Acme Design"
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await ask("marcus", "SELECT stripe_customer_id FROM workspaces")


async def test_internal_is_closed_to_customers():
    for query in ["SELECT * FROM internal.principals", "SELECT * FROM internal.requests", "SELECT * FROM internal.decisions"]:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await ask("dana", query)


async def test_sql_cannot_become_someone_else():
    """Each of these is what a query would try in order to read as another person or as no one in particular."""
    other = db_role("usr_elena")  # the owner of another workspace
    for attempt in [f"SET ROLE {other}", "SET ROLE fd_jobs", "SET ROLE postgres", f"SET SESSION AUTHORIZATION {other}",
                    "SET row_security = off; SELECT count(*) FROM invoices"]:
        async with as_person("usr_marcus") as db:
            with pytest.raises(asyncpg.PostgresError):
                await db.execute(attempt)
                await db.fetch("SELECT count(*) FROM invoices")
    # Changing the role inside a query changes current_user at most, and the policies ask for session_user.
    with pytest.raises(asyncpg.PostgresError):
        await ask("marcus", f"SELECT set_config('role', '{other}', true), (SELECT count(*) FROM invoices)")
    with pytest.raises(asyncpg.PostgresError):
        await ask("marcus", f"SELECT set_config('session_authorization', '{other}', true)")
    # An owner has the grant on invoices, so for her the policy alone stands between a query and another workspace.
    for attempt in ["SET row_security = off", f"SET ROLE {other}", "SET ROLE fd_jobs"]:
        async with as_person("usr_dana") as db:
            with pytest.raises(asyncpg.PostgresError):
                await db.execute(attempt)
                await db.fetch("SELECT count(*) FROM invoices")
            # With row security switched off, Postgres refuses the query; it does not run it without the policy.
            await db.execute("RESET row_security")
            assert await db.fetchval("SELECT count(*) FROM invoices WHERE workspace_id <> 'ws_acme'") == 0


async def test_a_read_only_query_cannot_write():
    for query in ["SELECT open_request('support', 'hello')", "CREATE TEMP TABLE t (x int)",
                  "SELECT set_config('transaction_read_only', 'off', true), open_request('support', 'hello')"]:
        with pytest.raises(asyncpg.PostgresError):
            await ask("dana", query)


async def test_only_owner_and_billing_admin_open_a_refund_request():
    async with as_person("usr_marcus") as db:
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="Owner or a Billing Admin"):
            await db.fetchval("SELECT open_request('refund', 'Please refund the last charge.')")


async def test_a_request_is_read_by_its_opener_the_owner_and_for_refunds_the_billing_admin():
    # The requests are made on hold, as the workers' role: the cluster's dispatcher would hand any other to a worker.
    from frontdesk.db.connect import as_jobs
    async with as_jobs() as db:
        bug, refund = [await db.fetchval(
            "INSERT INTO internal.requests (workspace_id, kind, opened_by, message, on_hold) VALUES ('ws_acme', $1, $2, 'A test.', true) "
            "RETURNING id", kind, by) for kind, by in (("bug_report", "usr_marcus"), ("refund", "usr_priya"))]
    try:
        seen = {who: {r["id"] for r in await ask(who, "SELECT id FROM requests")} for who in ("marcus", "tom", "priya", "dana")}
        assert bug in seen["marcus"] and refund not in seen["marcus"]
        assert not {bug, refund} & seen["tom"]
        assert refund in seen["priya"] and bug not in seen["priya"]
        assert {bug, refund} <= seen["dana"]
        assert not {bug, refund} & {r["id"] for r in await ask("elena", "SELECT id FROM requests")}
        # What a customer reads of a request has no column for the worker's reasoning.
        assert "proposal" not in (await ask("dana", "SELECT * FROM requests LIMIT 1"))[0].keys()
    finally:
        async with as_jobs() as db:
            await db.execute("DELETE FROM internal.request_log WHERE request_id = ANY($1)", [bug, refund])
            await db.execute("DELETE FROM internal.requests WHERE id = ANY($1)", [bug, refund])
