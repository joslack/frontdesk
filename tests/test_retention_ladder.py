"""What the retention ladder releases and records, checked against the seeded database.

    uv run --env-file .env pytest tests/test_retention_ladder.py

These need the cluster's Postgres and a seed (python -m frontdesk.db.seed). Each test runs one conversation of its
own through frontdesk.retention.ladder, with no server and no model, and the rows it wrote are deleted afterwards.
The role the ladder writes with cannot delete from app_events, so the deleting is done as the admin.
"""

import json
from uuid import uuid4

import pytest

from frontdesk.db.connect import as_admin, as_retention
from frontdesk.retention import ladder
from frontdesk.retention.ladder import Offer

MONTHLY, ANNUAL, OWNER = "ws_cobalt", "ws_birch", "usr_kenji"  # kenji is the owner of cobalt
EVENTS = ("retention_offer_accepted", "cancellation_requested")


@pytest.fixture
async def conversation():
    name = f"test-{uuid4()}"
    yield name
    async with as_admin() as db:
        await db.execute("DELETE FROM internal.retention_offers WHERE conversation = $1", name)
        await db.execute("DELETE FROM app_events WHERE id = ANY($1)", [ladder.event_id(type, name) for type in EVENTS])


async def released(db, conversation: str) -> list[tuple]:
    return [tuple(r) for r in await db.fetch("SELECT step, turn, percent_off, months FROM internal.retention_offers "
                                             "WHERE conversation = $1 ORDER BY step", conversation)]


async def events(db, conversation: str) -> list[dict]:
    return [dict(r) for r in await db.fetch("SELECT workspace_id, type, actor_user_id, data FROM app_events WHERE id = ANY($1)",
                                            [ladder.event_id(type, conversation) for type in EVENTS])]


def test_an_annual_plan_has_one_offer_fewer_than_a_monthly_plan():
    assert ladder.ladder({"interval": "month"}) == [Offer(10, 3), Offer(20, 3), Offer(30, 6)]
    assert ladder.ladder({"interval": "year"}) == [Offer(10, 3), Offer(20, 3)]


async def test_the_offers_come_out_in_order_one_for_each_turn(conversation):
    async with as_retention() as db:
        offers = [await ladder.next_offer(db, MONTHLY, conversation, turn) for turn in (1, 2, 3)]
        assert offers == ladder.ladder(await ladder.plan_of(db, MONTHLY)) == [Offer(10, 3), Offer(20, 3), Offer(30, 6)]
        assert await released(db, conversation) == [(1, 1, 10, 3), (2, 2, 20, 3), (3, 3, 30, 6)]


async def test_a_turn_releases_one_offer(conversation):
    async with as_retention() as db:
        first = await ladder.next_offer(db, MONTHLY, conversation, 1)
        assert await ladder.next_offer(db, MONTHLY, conversation, 1) == first
        assert await released(db, conversation) == [(1, 1, 10, 3)]
        # A turn that released nothing leaves a later turn with one offer and no more.
        assert await ladder.next_offer(db, MONTHLY, conversation, 4) == Offer(20, 3)
        assert await ladder.next_offer(db, MONTHLY, conversation, 4) == Offer(20, 3)
        assert await released(db, conversation) == [(1, 1, 10, 3), (2, 4, 20, 3)]


@pytest.mark.parametrize("workspace, length", [(MONTHLY, 3), (ANNUAL, 2)])
async def test_nothing_is_released_beyond_the_last_offer(conversation, workspace, length):
    async with as_retention() as db:
        offers = [await ladder.next_offer(db, workspace, conversation, turn) for turn in range(1, length + 4)]
        assert offers[length:] == [None, None, None] and None not in offers[:length]
        assert len(await released(db, conversation)) == length


async def test_accept_records_the_latest_offer_and_an_event(conversation):
    async with as_retention() as db:
        await ladder.next_offer(db, MONTHLY, conversation, 1)
        await ladder.next_offer(db, MONTHLY, conversation, 2)
        assert await ladder.outcome(db, MONTHLY, conversation) is None
        assert await ladder.accept(db, MONTHLY, conversation, OWNER) == Offer(20, 3)
        accepted = await db.fetch("SELECT step FROM internal.retention_offers WHERE conversation = $1 "
                                  "AND accepted_at IS NOT NULL", conversation)
        assert [r["step"] for r in accepted] == [2]
        (event,) = await events(db, conversation)
        assert (event["workspace_id"], event["type"], event["actor_user_id"]) == (MONTHLY, "retention_offer_accepted", OWNER)
        assert json.loads(event["data"]) == {"percent_off": 20, "months": 3}
        assert await ladder.outcome(db, MONTHLY, conversation) == {"outcome": "accepted", "percent_off": 20, "months": 3}


async def test_a_second_accept_fails_and_nothing_more_is_released(conversation):
    async with as_retention() as db:
        with pytest.raises(ladder.Refused, match="No offer"):
            await ladder.accept(db, MONTHLY, conversation, OWNER)
        await ladder.next_offer(db, MONTHLY, conversation, 1)
        await ladder.accept(db, MONTHLY, conversation, OWNER)
        with pytest.raises(ladder.Refused, match="already been accepted"):
            await ladder.accept(db, MONTHLY, conversation, OWNER)
        with pytest.raises(ladder.Refused, match="already been accepted"):
            await ladder.cancel(db, MONTHLY, conversation, OWNER)
        assert await ladder.next_offer(db, MONTHLY, conversation, 2) is None
        assert len(await released(db, conversation)) == len(await events(db, conversation)) == 1


async def test_cancel_records_the_request_and_leaves_the_subscription_as_it_is(conversation):
    async with as_retention() as db:
        before = await db.fetchrow("SELECT * FROM subscriptions WHERE workspace_id = $1", MONTHLY)
        await ladder.next_offer(db, MONTHLY, conversation, 1)
        assert await ladder.cancel(db, MONTHLY, conversation, OWNER) == before["current_period_end"]
        await ladder.cancel(db, MONTHLY, conversation, OWNER)
        (event,) = await events(db, conversation)
        assert (event["workspace_id"], event["type"], event["actor_user_id"]) == (MONTHLY, "cancellation_requested", OWNER)
        assert json.loads(event["data"]) == {"subscription_id": before["id"],
                                             "effective_at": before["current_period_end"].isoformat()}
        assert await db.fetchrow("SELECT * FROM subscriptions WHERE workspace_id = $1", MONTHLY) == before
        assert await ladder.outcome(db, MONTHLY, conversation) == {"outcome": "cancelled"}
        with pytest.raises(ladder.Refused, match="already been requested"):
            await ladder.accept(db, MONTHLY, conversation, OWNER)
        assert await ladder.next_offer(db, MONTHLY, conversation, 2) is None
