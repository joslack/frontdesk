"""The refund worker's prompt and tools are the ones refundo measured.

    uv run --env-file .env pytest tests/test_refund_tools.py

refundo's structured agent was evaluated with a prompt and eight tools. The worker here is meant to be that agent,
so each tool has to reach the model with the same name, the same description and the same arguments, with one
argument more on submit_proposal. This reads refundo's source and compares. It needs refundo checked out beside
this repository and is skipped without it. It calls no model and no database.
"""

import ast
from pathlib import Path

import pytest

from frontdesk.jobs import records, refund

REFUNDO = Path(__file__).resolve().parent.parent.parent / "refundo"
pytestmark = pytest.mark.skipif(not (REFUNDO / "agents/structured.py").exists(), reason="refundo is not checked out beside this repository")


def functions(path: Path) -> dict[str, ast.AsyncFunctionDef]:
    return {node.name: node for node in ast.parse(path.read_text()).body if isinstance(node, ast.AsyncFunctionDef)}


def theirs() -> dict[str, ast.AsyncFunctionDef]:
    return functions(REFUNDO / "evals/environment/mcp/server.py")


def arguments(function: ast.AsyncFunctionDef) -> dict[str, object]:
    """Each argument a function takes, with its default; ... for one that has none."""
    args = function.args.args
    defaults = [...] * (len(args) - len(function.args.defaults)) + [ast.literal_eval(d) for d in function.args.defaults]
    return {a.arg: d for a, d in zip(args, defaults, strict=True)}


def test_the_prompt_is_refundo_s():
    module = ast.parse((REFUNDO / "agents/structured.py").read_text())
    prompt = next(ast.literal_eval(node.value) for node in module.body
                  if isinstance(node, ast.Assign) and node.targets[0].id == "PROMPT")
    assert refund.PROMPT == prompt


def test_the_worker_has_the_tools_refundo_s_agent_had():
    module = ast.parse((REFUNDO / "agents/structured.py").read_text())
    named = next(ast.literal_eval(node.value) for node in module.body
                 if isinstance(node, ast.Assign) and node.targets[0].id == "TOOLS")
    assert {tool.name for tool in records.TOOLS} == named


@pytest.mark.parametrize("tool", records.TOOLS, ids=lambda tool: tool.name)
def test_a_tool_reaches_the_model_as_refundo_s_did(tool):
    measured = theirs()[tool.name]
    assert tool.description == ast.get_docstring(measured)
    # What the model may pass: the tool's arguments without the run's own, which the model never sees.
    seen = tool.tool_call_schema.model_json_schema()
    ours = {name: seen["properties"][name].get("default", ...) if name not in seen.get("required", []) else ...
            for name in seen["properties"]}
    expected = arguments(measured)
    if tool.name == "submit_proposal":
        expected = expected | {"invoice_id": ...}
    assert ours == expected


def test_the_policy_is_refundo_s():
    assert refund.POLICY == (REFUNDO / "docs/policy.md").read_text()
