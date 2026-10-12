"""The offers Quillstack makes to a workspace that wants to cancel, and the record of each one.

The offers for a workspace are a ladder: a short list in a fixed order, each offer a discount for some months, each
one worth more to the customer than the one before it. This module works the ladder out from the workspace's plan.
The retention desk's model never reads the ladder. It asks for the next offer, and it is given that offer or told
that there is none. The model does not know how many offers there are or what the last one is, so no message can
make it name them, and it cannot give more than the last one.

    monthly plan   10% off for 3 months, then 20% off for 3 months, then 30% off for 6 months
    annual plan    the first two of those. A year is charged as ten months.

An offer is released when next_offer returns it, and each released offer is a row of internal.retention_offers. Its
step is its place in the ladder, from 1. A conversation is open until it has an outcome: the customer accepts the
latest released offer, or asks to cancel. Each outcome is one row of app_events, with the person as the actor, and
its id is made from the conversation, so writing it twice leaves one row.

Every function takes a connection from frontdesk.db.connect.as_retention. `conversation` is any text that names one
person's conversation; the agent passes the id of its thread. Each function that writes holds a lock on the
conversation for its transaction, so two calls for one conversation run one after the other.

cancel records the request and writes nothing else. The subscriptions table is the payment processor's record: the
subscription is active until its current period ends, and the event says when that is.
"""

import json
from datetime import datetime
from hashlib import sha256
from typing import NamedTuple


class Offer(NamedTuple):
    percent_off: int  # of the subscription's price
    months: int  # how long the discount applies


class Refused(Exception):
    """The conversation does not allow what was asked. The text says why, in words the customer can be told."""


MONTHLY = (Offer(10, 3), Offer(20, 3), Offer(30, 6))
ENDED = {"accepted": "An offer has already been accepted in this conversation.",
         "cancelled": "The cancellation has already been requested in this conversation."}


def ladder(plan) -> list[Offer]:
    """The offers for a plan, in the order they are released. `plan` is a row of plan_history."""
    return list(MONTHLY if plan["interval"] == "month" else MONTHLY[:-1])


def event_id(type: str, conversation: str) -> str:
    """The id of the one event of this type that a conversation can write."""
    return "evt_" + sha256(f"{type}:{conversation}".encode()).hexdigest()[:16]


async def workspace_of(db, person_id: str) -> str | None:
    """The workspace a person belongs to, or None for someone who is not a member of one."""
    return await db.fetchval("SELECT workspace_id FROM members WHERE id = $1 AND removed_at IS NULL", person_id)


async def plan_of(db, workspace_id: str) -> dict:
    row = await db.fetchrow('SELECT tier, "interval", seats FROM plan_history WHERE workspace_id = $1 '
                            "ORDER BY effective_at DESC LIMIT 1", workspace_id)
    if row is None:
        raise LookupError(f"Workspace {workspace_id} has no plan.")
    return dict(row)


async def outcome(db, workspace_id: str, conversation: str) -> dict | None:
    """How the conversation ended, as the records have it, or None while it is open."""
    accepted = await db.fetchrow("SELECT percent_off, months FROM internal.retention_offers WHERE workspace_id = $1 "
                                 "AND conversation = $2 AND accepted_at IS NOT NULL", workspace_id, conversation)
    if accepted:
        return {"outcome": "accepted"} | dict(accepted)
    if await db.fetchval("SELECT 1 FROM app_events WHERE id = $1 AND workspace_id = $2",
                         event_id("cancellation_requested", conversation), workspace_id):
        return {"outcome": "cancelled"}
    return None


async def next_offer(db, workspace_id: str, conversation: str, turn: int) -> Offer | None:
    """Release the next offer of the workspace's ladder in this conversation. None means there is no further offer.

    `turn` is the number of messages the customer has sent in the conversation, and the caller passes it. A turn
    releases one offer at most: a second call in the same turn returns the offer the first call released. A
    conversation that has an outcome releases nothing.
    """
    async with db.transaction():
        await _lock(db, conversation)
        if await outcome(db, workspace_id, conversation):
            return None
        latest = await db.fetchrow("SELECT step, turn, percent_off, months FROM internal.retention_offers WHERE workspace_id = $1 "
                                   "AND conversation = $2 ORDER BY step DESC LIMIT 1", workspace_id, conversation)
        if latest and latest["turn"] >= turn:
            return Offer(latest["percent_off"], latest["months"])
        offers = ladder(await plan_of(db, workspace_id))
        step = latest["step"] + 1 if latest else 1
        if step > len(offers):
            return None
        offer = offers[step - 1]
        await db.execute("INSERT INTO internal.retention_offers (workspace_id, conversation, step, turn, percent_off, months) "
                         "VALUES ($1, $2, $3, $4, $5, $6)", workspace_id, conversation, step, turn, *offer)
        return offer


async def accept(db, workspace_id: str, conversation: str, person_id: str) -> Offer:
    """The customer takes the latest offer released in this conversation. Refused when no offer was released, and
    when the conversation already has an outcome."""
    async with db.transaction():
        await _lock(db, conversation)
        if ended := await outcome(db, workspace_id, conversation):
            raise Refused(ENDED[ended["outcome"]])
        row = await db.fetchrow("UPDATE internal.retention_offers SET accepted_at = now() WHERE id = ("
                                "SELECT id FROM internal.retention_offers WHERE workspace_id = $1 AND conversation = $2 "
                                "ORDER BY step DESC LIMIT 1) RETURNING percent_off, months", workspace_id, conversation)
        if row is None:
            raise Refused("No offer has been made in this conversation.")
        offer = Offer(*row)
        await _event(db, workspace_id, conversation, "retention_offer_accepted", person_id, offer._asdict())
        return offer


async def cancel(db, workspace_id: str, conversation: str, person_id: str) -> datetime:
    """The customer asks to cancel. Returns when the current period ends, which is when the subscription ends. A
    second call in the conversation changes nothing. Refused when an offer was accepted in the conversation."""
    async with db.transaction():
        await _lock(db, conversation)
        if (await outcome(db, workspace_id, conversation) or {}).get("outcome") == "accepted":
            raise Refused(ENDED["accepted"])
        subscription = await db.fetchrow("SELECT id, current_period_end FROM subscriptions WHERE workspace_id = $1 "
                                         "AND status = 'active' ORDER BY current_period_end DESC LIMIT 1", workspace_id)
        if subscription is None:
            raise Refused("The workspace has no active subscription.")
        await _event(db, workspace_id, conversation, "cancellation_requested", person_id,
                     {"subscription_id": subscription["id"], "effective_at": subscription["current_period_end"].isoformat()})
        return subscription["current_period_end"]


async def _lock(db, conversation: str) -> None:
    await db.execute("SELECT pg_advisory_xact_lock(hashtext($1))", conversation)


async def _event(db, workspace_id: str, conversation: str, type: str, person_id: str, data: dict) -> None:
    await db.execute("INSERT INTO app_events (id, workspace_id, at, type, actor_user_id, data) VALUES ($1, $2, now(), $3, $4, $5) "
                     "ON CONFLICT (id) DO NOTHING", event_id(type, conversation), workspace_id, type, person_id, json.dumps(data))
