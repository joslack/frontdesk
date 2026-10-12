"""The retention desk: Quillstack's agent for a customer who wants to cancel, offered to the customer's agent over A2A.

    uv run --env-file .env python -m frontdesk.retention.server        # http://localhost:18200

A customer's agent reads the agent card, which is public, and sends its messages to the JSON-RPC endpoint. Each
request carries a token that Keycloak signed for one person. Who is asking, and in which role, comes from that
token, and the person's workspace comes from the records. Nothing in a message says who is asking. Only the Owner or
a Billing Admin of a workspace may talk to the desk about cancelling.

One message is one turn of the agent in frontdesk/retention/agent.py. The state of the task says where the
conversation stands:

    input-required  the conversation is open, and the desk waits for the customer's next message
    completed       the conversation has an outcome. The artifact named outcome states it as data:
                    {"outcome": "accepted", "percent_off": 20, "months": 3} or {"outcome": "cancelled"}
    rejected        the caller is not the Owner or a Billing Admin of a workspace
    failed          the turn raised an error. The log has it, and the caller may send the message again.

The outcome is read from the records after the turn. The text of the desk's message is what the model wrote, and it
records nothing.

Tasks are kept in memory and conversations in Postgres. After a restart the server knows no earlier task id. A
message with the same context id and no task id continues the conversation in a new task.

    GET  /.well-known/agent-card.json   the agent card. The address in it is RETENTION_PUBLIC_URL.
    POST /                              JSON-RPC. 401 without a valid token.
    GET  /healthz

RETENTION_PORT is the port the server listens on.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from a2a.auth.user import User
from a2a.helpers import new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import DefaultServerCallContextBuilder, create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (AgentCapabilities, AgentCard, AgentInterface, AgentSkill, OpenIdConnectSecurityScheme, SecurityRequirement,
                       SecurityScheme, StringList)
from a2a.utils import TransportProtocol
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from frontdesk import settings
from frontdesk.db.connect import as_retention
from frontdesk.identity import Caller, NotSignedIn, abearer
from frontdesk.retention import agent, ladder

log = logging.getLogger("frontdesk.retention")
PORT = int(settings.env("RETENTION_PORT", "18200"))
PUBLIC_URL = settings.env("RETENTION_PUBLIC_URL", "http://localhost:18200")
MAY_CANCEL = ("owner", "billing_admin")
NOT_ALLOWED = "A cancellation request must come from the Owner or a Billing Admin of the workspace."

CARD = AgentCard(
    name="Quillstack retention desk", version="0.1.0",
    description="Talks with the Owner or a Billing Admin of a Quillstack workspace who wants to cancel the subscription. "
                "It may offer a discount, and it records the offer the customer accepts or the request to cancel.",
    supported_interfaces=[AgentInterface(url=PUBLIC_URL, protocol_binding=TransportProtocol.JSONRPC, protocol_version="1.0")],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"], default_output_modes=["text/plain", "application/json"],
    skills=[AgentSkill(id="cancel_subscription", name="Cancel a subscription", tags=["subscription", "cancellation", "discount"],
                       description="Send what the customer wants in plain text. The task waits for input while the conversation "
                                   "is open. A completed task has an artifact named outcome, which states as data the offer "
                                   "the customer accepted or that the cancellation is requested.")],
    security_schemes={"keycloak": SecurityScheme(open_id_connect_security_scheme=OpenIdConnectSecurityScheme(
        description=f"A bearer token that Keycloak signed for the person, with the audience {settings.AUDIENCE}.",
        open_id_connect_url=f"{settings.KEYCLOAK_ISSUER}/.well-known/openid-configuration"))},
    security_requirements=[SecurityRequirement(schemes={"keycloak": StringList()})])


class SignedIn:
    """Lets a request through only with a token that Keycloak signed, and puts the caller in the request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        try:
            scope["caller"] = await abearer(Headers(scope=scope).get("authorization"))
        except NotSignedIn as refused:
            response = JSONResponse({"error": str(refused)}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await response(scope, receive, send)
        await self.app(scope, receive, send)


class Person(User):
    """The caller as the A2A server knows a user. It keeps each task under the person's id, so no one reads
    another person's task."""

    def __init__(self, caller: Caller):
        self.caller = caller

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def user_name(self) -> str:
        return self.caller.person_id


class FromToken(DefaultServerCallContextBuilder):
    def build_user(self, request: Request) -> User:
        return Person(request.scope["caller"])


class Desk(AgentExecutor):
    graph = None  # the agent with its checkpointer, which the server opens when it starts

    async def execute(self, context: RequestContext, queue: EventQueue) -> None:
        caller: Caller = context.call_context.user.caller
        if context.current_task is None:
            await queue.enqueue_event(new_task_from_user_message(context.message))
        task = TaskUpdater(queue, context.task_id, context.context_id)

        def says(text: str):
            return task.new_agent_message([new_text_part(text)])

        try:
            turn = await self.turn(caller, context.context_id, context.get_user_input().strip())
        except Exception:  # the model or the database failed. The caller is told that much, and the log has the rest.
            log.exception("a turn failed for %s", caller.person_id)
            return await task.failed(says("The retention desk could not answer. Send your message again."))
        if turn is None:
            return await task.reject(says(NOT_ALLOWED))
        answer, outcome = turn
        if outcome is None:
            return await task.requires_input(says(answer))
        await task.add_artifact([new_data_part(outcome)], name="outcome")
        await task.complete(says(answer))

    async def turn(self, caller: Caller, context_id: str, message: str) -> tuple[str, dict | None] | None:
        """The desk's answer to one message and the outcome if there is one, or None for a caller who may not cancel."""
        if caller.role not in MAY_CANCEL:
            return None
        async with as_retention() as db:
            workspace = await ladder.workspace_of(db, caller.person_id)
        if workspace is None:
            return None
        if not message:
            return "Send your message as text.", None
        return await agent.reply(self.graph, caller.person_id, workspace, context_id, message)

    async def cancel(self, context: RequestContext, queue: EventQueue) -> None:
        """Ends the A2A task. It does not cancel the subscription, which only the agent's tool records."""
        await TaskUpdater(queue, context.task_id, context.context_id).cancel()


desk = Desk()


@asynccontextmanager
async def lifespan(app: Starlette):
    async with agent.open_agent() as desk.graph:
        yield


async def healthz(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


handler = DefaultRequestHandler(agent_executor=desk, task_store=InMemoryTaskStore(), agent_card=CARD)
app = Starlette(lifespan=lifespan, routes=[
    Route("/healthz", healthz),
    *create_agent_card_routes(CARD),
    Mount("/", routes=create_jsonrpc_routes(handler, rpc_url="/", context_builder=FromToken()), middleware=[Middleware(SignedIn)]),
])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
