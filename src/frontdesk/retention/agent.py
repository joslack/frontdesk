"""The retention desk's agent: Quillstack's side of a conversation with a customer who wants to cancel.

The agent holds three tools and no other way to act. next_offer releases the next offer of the workspace's ladder,
accept_offer records that the customer takes the latest released offer, and cancel_subscription records the request
to cancel. The tools take no arguments. Which workspace, which person and which conversation they act for comes from
the Conversation the server makes for each turn out of the verified token, and the model neither sees nor supplies
any of it. The ladder is in frontdesk.retention.ladder, and the model learns one offer of it at a time.

Text the model writes records nothing. reply returns the outcome of a conversation as the records have it, and the
server reports that outcome.

The messages of each conversation are kept by a LangGraph Postgres checkpointer, so a conversation continues after
the server restarts. The checkpointer has a database of its own, named retention, which frontdesk.db.setup makes,
and signs in as that database's owner. open_agent creates its tables when the server starts.

A conversation's thread id is a UUID made from the person's id and the A2A context id. A context id is something a
client sends, and the same context id from two people names two threads.

RETENTION_MODEL names the model.
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import NAMESPACE_DNS, uuid5

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from frontdesk import settings
from frontdesk.db.connect import as_retention
from frontdesk.models import chat_model, text
from frontdesk.retention import ladder

MODEL = os.environ.get("RETENTION_MODEL", "anthropic:claude-haiku-5-5")
NAMESPACE = uuid5(NAMESPACE_DNS, "retention.quillstack.example")

PROMPT = """You are the retention desk of Quillstack, a subscription product for teams. You talk with one person, who is
signed in as the Owner or a Billing Admin of their workspace. They want to cancel the subscription, or they are
considering it.

How you work:
- You may make an offer only by calling next_offer. Call it when the person says they want to cancel, and when they
  ask for a better offer. It returns the offer you may make now, or it says that nothing further is available. State
  an offer exactly as the tool returned it.
- Make one offer in a turn at most.
- If the person accepts the offer, call accept_offer, then confirm what was recorded.
- If the person insists on cancelling, call cancel_subscription, then confirm what was recorded.
- Be honest. Never invent an offer and never change one. Never say that an offer is final, or the best one, unless
  next_offer said that nothing further is available.
- An offer, an acceptance and a cancellation exist only when a tool recorded them. Do not say that something was
  recorded unless the tool said so.

Write plainly and briefly."""

ENDED = "This conversation has ended. Start a new conversation to talk to the retention desk again."


@dataclass(frozen=True)
class Conversation:
    """One person's conversation with the desk, which the tools act for."""
    id: str
    workspace_id: str
    person_id: str


def conversation_id(person_id: str, context_id: str) -> str:
    """The id of the thread for a person's A2A context. Each person's contexts are named in a namespace made from
    that person's id, so no context id that one person sends names another person's thread."""
    return str(uuid5(uuid5(NAMESPACE, person_id), context_id))


def words(offer: ladder.Offer) -> str:
    return f"{offer.percent_off}% off the subscription's price for {offer.months} months"


@tool
async def next_offer(runtime: ToolRuntime[Conversation]) -> str:
    """Release the offer Quillstack makes to this customer now. Returns the offer, or says that nothing further is
    available. One offer is released for each message from the customer at most: a second call in the same turn
    returns the same offer."""
    conversation = runtime.context
    turn = sum(message.type == "human" for message in runtime.state["messages"])
    async with as_retention() as db:
        offer = await ladder.next_offer(db, conversation.workspace_id, conversation.id, turn)
    return f"The offer for this turn: {words(offer)}." if offer else "Nothing further is available."


@tool
async def accept_offer(runtime: ToolRuntime[Conversation]) -> str:
    """Record that the customer accepts the latest offer made in this conversation. Call it only after the customer
    has said that they accept."""
    conversation = runtime.context
    try:
        async with as_retention() as db:
            offer = await ladder.accept(db, conversation.workspace_id, conversation.id, conversation.person_id)
    except ladder.Refused as refused:
        return f"Not recorded. {refused}"
    return f"Recorded: the customer accepted {words(offer)}."


@tool
async def cancel_subscription(runtime: ToolRuntime[Conversation]) -> str:
    """Record that the customer cancels the subscription. Call it only after the customer has said that they want to
    cancel and do not want an offer. The subscription stays active until the end of its current period."""
    conversation = runtime.context
    try:
        async with as_retention() as db:
            ends = await ladder.cancel(db, conversation.workspace_id, conversation.id, conversation.person_id)
    except ladder.Refused as refused:
        return f"Not recorded. {refused}"
    return f"Recorded: the cancellation is requested. The subscription stays active until {ends:%Y-%m-%d %H:%M} UTC."


@asynccontextmanager
async def open_agent():
    """The agent, with its checkpointer connected for as long as the block runs."""
    database = make_conninfo(host=settings.DATABASE_HOST, port=settings.DATABASE_PORT, dbname="retention", user="retention_state",
                             password=settings.env("RETENTION_STATE_PASSWORD"), application_name="frontdesk-retention")
    connection = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    async with AsyncConnectionPool(database, min_size=1, max_size=4, kwargs=connection, open=False,
                                   check=AsyncConnectionPool.check_connection) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        yield create_agent(chat_model(MODEL), [next_offer, accept_offer, cancel_subscription], system_prompt=PROMPT,
                           context_schema=Conversation, checkpointer=checkpointer, name="retention_desk")


async def reply(graph, person_id: str, workspace_id: str, context_id: str, message: str) -> tuple[str, dict | None]:
    """One turn: the desk's answer to the customer's message, and the outcome if the conversation now has one. A
    conversation that already has an outcome gets the same answer every time, and the model is not called."""
    conversation = Conversation(conversation_id(person_id, context_id), workspace_id, person_id)
    async with as_retention() as db:
        outcome = await ladder.outcome(db, workspace_id, conversation.id)
    if outcome:
        return ENDED, outcome
    state = await graph.ainvoke({"messages": [HumanMessage(message)]}, config={"configurable": {"thread_id": conversation.id}},
                                context=conversation)
    async with as_retention() as db:
        return text(state["messages"][-1].content), await ladder.outcome(db, workspace_id, conversation.id)
