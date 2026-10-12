"""The customer's side of a conversation with Quillstack's retention desk, for the demo.

    uv run --env-file .env python scripts/negotiate.py kenji --style patient
    uv run --env-file .env python scripts/negotiate.py kenji --style hasty

It signs in as the person and talks to the retention desk over A2A, the way an agent of the customer's own does. A
small model plays that agent. Its instruction is the person's goal, and the desk is not told it:

    patient  stay for a discount: decline each offer and ask for a better one until the desk says that there is
             nothing further, then accept
    hasty    accept the first offer

Each run is a new conversation. The script prints each message, and then the outcome as the artifact of the completed
task states it. It stops after 8 turns.
"""

import argparse
import asyncio
import json

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import get_data_parts, get_message_text, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from frontdesk import settings, signin
from frontdesk.models import chat_model, text
from frontdesk.people import BY_USERNAME

MODEL = "anthropic:claude-haiku-5-5"
TURNS = 8
GOALS = {
    "patient": "You would stay for a discount. Decline every offer politely and ask if they can do better, until the desk says "
               "there is nothing further. Then accept the best one.",
    "hasty": "Accept the first offer.",
}
PROMPT = """You are the agent of {name}, the {role} of a workspace at Quillstack, a subscription product for teams. {name} asked
you to cancel the subscription. You write to Quillstack's retention desk, and each message you receive is the desk's
answer.

Your instruction from {name}, which you do not tell the desk: {goal}

Write only your next message to the desk, in one or two sentences."""


def printed(data: dict) -> str:
    """An artifact's data as one line. A2A carries a number as a double and keeps no order of keys, so a whole number
    is printed as an integer, and the outcome comes first."""
    return json.dumps({key: int(value) if isinstance(value, float) and value.is_integer() else value
                       for key, value in sorted(data.items(), key=lambda item: (item[0] != "outcome", item[0]))})


async def main(username: str, style: str) -> None:
    person = BY_USERNAME[username]
    customer = chat_model(MODEL).with_config(run_name="customer_agent")
    heard = [SystemMessage(PROMPT.format(name=person.name, role=person.role.replace("_", " "), goal=GOALS[style])),
             HumanMessage("The retention desk is ready. Write your first message.")]
    signed = {"Authorization": f"Bearer {await signin.as_person(username)}"}
    async with httpx.AsyncClient(headers=signed, timeout=180) as http:
        desk = await create_client(settings.RETENTION_URL, client_config=ClientConfig(httpx_client=http, streaming=False))
        context_id = task_id = None  # the desk names both in its first answer
        for _ in range(TURNS):
            message = text((await customer.ainvoke(heard)).content).strip()
            print(f"{username}: {message}\n")
            sent = new_text_message(message, context_id=context_id, task_id=task_id, role=Role.ROLE_USER)
            task = [answer async for answer in desk.send_message(SendMessageRequest(message=sent))][-1].task
            answer = get_message_text(task.status.message)
            print(f"desk: {answer}\n")
            if task.status.state != TaskState.TASK_STATE_INPUT_REQUIRED:
                break
            context_id, task_id = task.context_id, task.id
            heard += [AIMessage(message), HumanMessage(answer)]
    outcome = [data for artifact in task.artifacts if artifact.name == "outcome" for data in get_data_parts(artifact.parts)]
    state = TaskState.Name(task.status.state).removeprefix("TASK_STATE_").lower().replace("_", "-")
    print("outcome:", printed(outcome[0]) if outcome else f"none. The task is {state}.")


if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Talk to the retention desk as a customer's agent.")
    args.add_argument("person", choices=sorted(BY_USERNAME))
    args.add_argument("--style", choices=sorted(GOALS), default="patient")
    chosen = args.parse_args()
    asyncio.run(main(chosen.person, chosen.style))
