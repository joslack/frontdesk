"""The memory turn: when a conversation has gone quiet, the agent is asked once what is worth remembering about
the person, while the provider still holds the conversation in its prompt cache.

A model call costs far less when its beginning is one the provider has just processed. A provider keeps that for
a few minutes after the last call. So the question is asked a little before that time is up: the whole
conversation is then read from the cache, and only the question and the answer are new.

    Remember  a hook on the desk agent. When a turn ends it schedules a run of the graph below, CACHE_SECONDS minus
              MARGIN from now.
    remember  the graph. When its run starts it reads the conversation's thread. If the person has written again in
              the meantime it stops, because that later turn scheduled a run of its own. Otherwise it runs the desk
              agent on the conversation with one more message, written here and marked as not the person's.

The person never sees that message or the answer: the run works on a copy of the conversation's messages and saves
none of them. What it may change is the person's notes file, /memories/notes.md, which the next conversation
starts with.

For the conversation to be read from the cache, the call has to begin exactly as the conversation's calls did: the
same tools, the same system prompt, the same messages. That is why the question is put to the desk agent itself and
why the agent's file tools, which write the notes, are among its tools on every turn. The run's result records how
many tokens the provider read from its cache, which is how to tell that this held.

What is worth remembering is in memory_criteria.md, for whoever runs the desk to change.
"""

import logging
import os
from pathlib import Path
from typing import Any, TypedDict

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph_sdk import get_client

from frontdesk.desk.gate import own_turn
from frontdesk.models import text

log = logging.getLogger("frontdesk.memory")
CRITERIA = (Path(__file__).parent / "memory_criteria.md").read_text()
# How long each provider keeps a prompt's beginning after the last call that used it, in seconds. Anthropic's is
# its default of five minutes, which is what deepagents asks for.
CACHE_SECONDS = {"anthropic": 300, "openai": 300}
MARGIN = 60


def wait_for(model: str) -> int:
    """Seconds from the end of a turn to the memory turn, for a model named as provider:model."""
    return int(os.environ.get("REMEMBER_AFTER_SECONDS", CACHE_SECONDS.get(model.split(":")[0], 300) - MARGIN))


QUESTION = f"""<from_the_desk_software>
This message is not from the person. Quillstack's desk software wrote it, and the person will not see your answer.
The conversation above has gone quiet.

Decide whether it showed anything worth keeping in your notes about this person, /memories/notes.md.

{CRITERIA}
If there is something to keep, read /memories/notes.md if it exists, then write the whole file again with write_file,
with the new note in it. If there is nothing, change nothing. Then answer with one word: saved, or nothing.
</from_the_desk_software>"""


class Remember(AgentMiddleware):
    """Schedules the memory turn each time a turn of the conversation ends."""

    def __init__(self, model: str):
        self.wait = wait_for(model)

    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        last = state["messages"][-1]
        if own_turn.get() or (isinstance(last, AIMessage) and "gate" in last.response_metadata):
            return None
        try:
            # No URL: the call goes to the server this run is on, as the person the run belongs to. A run with no
            # thread keeps nothing once it ends.
            await get_client().runs.create(None, "remember", after_seconds=self.wait,
                                           input={"thread_id": runtime.execution_info.thread_id, "turn": len(state["messages"])})
        except Exception:  # outside a server, or the server refused: the conversation is not held up for this
            log.exception("could not schedule the memory turn")
        return None


class Asked(TypedDict, total=False):
    thread_id: str
    turn: int  # how many messages the conversation had when this was scheduled
    result: str
    cache_read_tokens: int
    input_tokens: int


async def reflect(state: Asked) -> dict:
    from frontdesk.desk.agent import make_graph

    # The server lets a person read their own threads only, and this run is theirs.
    thread = await get_client().threads.get_state(state["thread_id"])
    messages = thread["values"].get("messages", [])
    if len(messages) != state["turn"]:
        return {"result": "superseded"}
    marked = own_turn.set(True)
    try:
        answer = await (await make_graph()).ainvoke({"messages": [*messages, HumanMessage(QUESTION)]})
    finally:
        own_turn.reset(marked)
    calls = [m for m in answer["messages"][len(messages):] if isinstance(m, AIMessage) and m.usage_metadata]
    read = sum((m.usage_metadata.get("input_token_details") or {}).get("cache_read", 0) for m in calls[:1])
    log.info("memory turn on %s: %s tokens read from the cache of %s", state["thread_id"], read,
             calls[0].usage_metadata["input_tokens"] if calls else 0)
    return {"result": text(answer["messages"][-1].content).strip()[:40], "cache_read_tokens": read,
            "input_tokens": calls[0].usage_metadata["input_tokens"] if calls else 0}


builder = StateGraph(Asked)
builder.add_node("reflect", reflect)
builder.add_edge(START, "reflect")
builder.add_edge("reflect", END)
graph = builder.compile()
