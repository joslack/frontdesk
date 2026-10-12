"""A way to the retention desk for an agent that speaks MCP and not A2A.

The retention desk is an A2A agent with an address of its own. An agent that speaks A2A talks to it there. This
passes one message from any other agent to the desk and returns the desk's answer, so that the tool
ask_retention_desk can offer the same conversation over MCP.

The message goes to the desk with the caller's own token. The access server adds nothing to it and holds nothing
the desk would accept in the caller's place: who is asking is, here as everywhere, what Keycloak signed.
"""

import httpx
from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

from frontdesk import settings
from frontdesk.access.records import Refused


async def say(token: str, message: str, conversation_id: str | None) -> dict:
    """Send one message to the retention desk as the person the token names, and return what the desk answered."""
    try:
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=120) as http:
            card = await A2ACardResolver(http, settings.RETENTION_URL).get_agent_card()
            # The card gives the address customers use. From here the desk is at another address.
            card.supported_interfaces[0].url = settings.RETENTION_URL + "/"
            desk = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)
            sent = new_text_message(message, context_id=conversation_id, role=Role.ROLE_USER)
            task = [answer async for answer in desk.send_message(SendMessageRequest(message=sent))][-1].task
    except httpx.HTTPError as e:
        raise Refused(f"The retention desk cannot be reached right now: {type(e).__name__}.") from e
    outcome = [dict(data) for artifact in task.artifacts if artifact.name == "outcome" for data in get_data_parts(artifact.parts)]
    state = TaskState.Name(task.status.state).removeprefix("TASK_STATE_").lower()
    return {"conversation_id": task.context_id, "desk_says": get_message_text(task.status.message),
            "conversation_is": "open" if state == "input_required" else state,
            "recorded_outcome": outcome[0] if outcome else None}
