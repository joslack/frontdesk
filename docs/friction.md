# Friction log

Rough edges met while frontdesk was built on 2026-10-12, in LangGraph Server, deepagents, LangChain, FastMCP and
Claude Code. The last section holds the rough edges met in the refund evaluation, which is in
[refundo](https://github.com/joslack/refundo). Each entry says how it is known:

- **seen**: it happened in this build, and the output is quoted or described.
- **read by a subagent**: a research subagent read it in the installed source or the docs, or ran it in process
  with no server. Its notes were in `/tmp/frontdesk-research/` during the build.
- **read in the source** or **read in the docs**: read there when the entry was written, and not run.
- **not checked**: stated for context, and nobody tried it.

Versions: langgraph 1.2.14, langgraph-api 0.16.0, langgraph-cli 0.4.33, langgraph-sdk 0.4.6, deepagents 0.7.24,
langchain 1.4.4, fastmcp 4.1.0, mcp 2.3.0, Claude Code 2.1.296.

## LangGraph Server

**An apostrophe in a graph's description breaks `langgraph build`.** Seen. `langgraph.json` had a description
with the words "a person's review". The generated Dockerfile puts the graphs in
`ENV LANGSERVE_GRAPHS='{...}'`, in single quotes, and the build failed with
`Syntax error - can't find = in "review,". Must be of the form: name=value`. Rewording the description fixed it.

**`langgraph dev` and `langgraph build` name the config flag differently.** Seen. `langgraph build -c file` works.
`langgraph dev -c file` answers `No such option '-c'`; it takes `--config`.

**A blocking call in `@auth.authenticate` turns into a 500 under `langgraph dev`.** Seen. The handler verified a
token with PyJWT's `PyJWKClient`, which fetches the keys with a blocking call. The development server's blocking
detector raised `BlockingError: Blocking call to socket.socket.connect` and the caller got HTTP 500, where a
refused token should be 401 or 403. Running the check with `asyncio.to_thread` fixed it.

**Whether custom auth runs on the self-hosted image without an enterprise licence is stated three ways.**
- Read by a subagent, in the docs: one page says custom auth is for SaaS and Enterprise self-hosted only, another
  says it is supported on all plans.
- Read by a subagent, in GitHub issue langchain-ai/langgraph#5390 (July 2025, langgraph-api 0.2.82): the image
  refused to start with custom auth and no licence key.
- Seen, with the `langchain/langgraph-api:3.12` image at langgraph-api 0.16.0 on k3s, with `LANGSMITH_API_KEY` set
  and no licence key: the server logged `No enterprise license key found, running in lite mode with LangSmith API
  key. For production use, set LANGGRAPH_CLOUD_LICENSE_KEY in environment.`, loaded the custom auth handler, and
  refused and accepted tokens as the handler says.

**A run that stops at `interrupt()` ends as `success`.** Seen in the queue pod's log:
`run_status=success thread_status=interrupted`. To know that a run is waiting for a person, read the thread and not
the run.

**The server retries a run whose worker stopped, and not a run whose step raised an error.** The first half was
seen: a development server reloaded during a run, logged `Background run failed, will retry. Exception:
CancelledError`, and the run finished on its second attempt. The second half was read by a subagent in
`langgraph_api/worker.py`. So a model provider that stays down ends the run as `error`, and starting it again is
the application's job. Here the dispatcher does it.

**A killed worker's run comes back after about three and a half minutes.** Seen, twice, on the cluster. A queue
pod that was asked to stop while a run was in flight finished the run within its grace period, and the request
reached review 9 seconds after the delete. A queue pod that was killed with no grace at 08:14:42 left its run
marked `running`; the replacement pod logged `Dequeued run for background worker attempt=2` for it at 08:18:19, and
the run succeeded at 08:18:49. Nothing in the API says in the meantime that the run has no worker: its status is
`running` and its thread is `busy` for those minutes.

**The split between API pods and queue pods is in the Helm chart and not in the docs for a standalone server.**
Read by a subagent in the chart: API pods get `N_JOBS_PER_WORKER=0`, queue pods run `/storage/queue_entrypoint.sh`.
Seen: both work as written in `deploy/apps/jobs.yaml`.

**The token has to travel inside the user object.** Read by a subagent in the server's source: the
`Authorization` header is never copied into a run's config, so a graph that calls another service as the caller
needs the raw token as an extra field of what `@auth.authenticate` returns. That object is stored with the run, and
it is included in webhook bodies unless `webhooks.allowed_fields` leaves it out. Seen: the extra field reaches the
graph as `config["configurable"]["langgraph_auth_user"]["token"]`. Seen, with tracing on: of the first 110 runs in
the LangSmith project, none held the token in its inputs, outputs or metadata.

**A graph factory that takes 400 ms is logged at error level.** Seen: `[error] Slow graph load. Accessing graph
'desk' took 400.93ms`, for a factory that lists an MCP server's tools once and then returns a cached graph.

**The server runs as an ordinary database owner if the `vector` extension is already there.** Seen. Each
deployment signs in as the owner of its own database, not as a superuser. `frontdesk.db.setup` adds the extension
first, as a superuser, because the server's own migration would need to.

**A copied `.env` sends traces to another project.** Seen, and my own doing: frontdesk's `.env` was copied from
refundo with `LANGSMITH_TRACING=true` and refundo's project name. Two local runs of the refund worker at about
07:33 UTC were traced into the project "Refundo Harbor Evals" before I saw it. Nothing warns that a process is
tracing into a project that some other code base named.

## LangSmith

**`Client.list_runs(limit=200)` is refused.** Seen: `400 Bad Request ... {"detail":"Limit exceeds maximum allowed
value of 100"}`. The client pages by itself when no limit is given, and a limit over 100 is sent to the server as
it is. Seen in the same call: `list_runs() is deprecated and will be removed after Jan 31, 2027. Use
client.runs.query() instead`.

**A run's project is whatever the environment names.** Seen: with `LANGSMITH_PROJECT=frontdesk` in each
deployment, the desk agent's turns, the workers' runs and the retention desk's conversations arrived in a project
of that name, which LangSmith made on the first run. See also the copied `.env` above.

## deepagents and LangChain

**`langchain-mcp-adapters` cannot be imported beside FastMCP 4.** Read by a subagent, which ran the import:
FastMCP 4 needs `mcp>=2`, every release of the adapters needs `mcp` 1.x, and the import fails with
`ImportError: cannot import name 'RequestContext' from 'mcp.shared.context'`. Seen: `langchain.mcp.MCPAdapter`,
which is in beta in langchain 1.4.4, works with a FastMCP 4 client, and the desk agent uses it.

**`MCPAdapter` has no hook for a header on each call.** Read by a subagent. Seen: an `httpx2.Auth` subclass that
reads the running graph's config with `get_config()` signs each call as that run's caller. Listing the tools
happens outside any run and needs a token of its own.

**A deep agent's defaults are for coding.** Read by a subagent, which ran it: the agent gets `ls`, `read_file`,
`write_file`, `edit_file`, `delete`, `glob`, `grep` and `task`, and the default memory prompt is about 5,000
characters with coding and Slack examples. Taking tools away needs a harness profile that is global to the process.
Seen: with the profile in `frontdesk/desk/agent.py` and a replaced memory prompt, the desk agent, asked to list
its tools, named `ls`, `read_file`, `write_file`, `edit_file` and the access server's eight. That is the model's
own account of its tools, not a reading of the request sent to it.

**Memory is loaded once for each thread.** Read by a subagent, which ran it: after the notes file changed, the
same thread still showed the old notes and a new thread showed the new ones.

## FastMCP

**`KeycloakAuthProvider` requires the scope `openid` and checks no audience unless told to.** Read by a subagent,
which ran it. frontdesk passes its own `JWTVerifier` with the audience.

**Skills as MCP resources work out of the box.** Seen: `SkillsDirectoryProvider` served
`skill://refunds/SKILL.md` and the others from the skills folder.

## Claude Code as the customer's agent

**It runs with no built-in tools and one MCP server.** Seen: `claude --tools "" --strict-mcp-config --mcp-config
file --setting-sources ""` on Claude Haiku 5.5 listed exactly the access server's tools, named the four skills as
readable with `read_skill`, and answered a records question.

**`--disable-slash-commands` takes `/mcp` away.** Seen: the flag's help says "Disable all skills". With it, a
session whose server needed a sign-in showed `1 MCP server needs authentication · run /mcp`, and typing `/mcp`
answered `Unknown command: /mcp`.

**A session in a new folder starts with a question whose default is to leave.** Seen: "Is this a project you
created or one you trust?", with "No, exit" selected. A launcher that makes a new folder for each session meets it
every time, so `scripts/their-agent.sh` uses one folder.

**`headersHelper` keeps a token live without a person.** Seen that the helper's token is accepted. Read in the
docs, not tried: Claude Code runs the helper again on reconnect and when a call is refused with 401 or 403.

**Sign-in with a browser works against Keycloak with a client registered ahead of time.** Seen, with Keycloak
26.4.7: `claude mcp add --transport http ... --client-id frontdesk-cli --callback-port 18765`, then
`claude mcp login`. Claude Code found Keycloak from the access server's protected-resource metadata and asked for
a code with PKCE, the redirect `http://localhost:18765/callback` and a `resource` parameter, and no `scope`.
Keycloak signed dana in and redirected; Claude Code printed `Authenticated` and a tool call returned dana. The
sign-in form was filled in by a script over HTTP and not by a person in a browser; the page itself was seen in a
headless browser's screenshot. Seen the same way inside a session: `/mcp`, the server, Authenticate, then
`Authentication successful. Connected to ...`. Not tried: an agent that registers itself with Keycloak when it
first connects.

**A stored sign-in follows the server's name and address.** Seen: a session started with `--mcp-config` and
`--strict-mcp-config` was signed in already when its server had the name and address of one signed in through
`claude mcp login`, and had no tools when the name was new. Seen on reading the stored sign-in: the line
`[mcp-sdk] SEP-2352: stored OAuth credential has no 'issuer' stamp`.

## The refund evaluation, in refundo

These entries are from the evaluation of the refund agent, which ran from 2026-10-04 to 2026-10-07 on Harbor 0.23.0
with harbor-langsmith 0.3.1. The LangChain source was read on 2026-10-12 in the evaluation's image, which holds
langchain 1.4.4 and langchain-anthropic 1.7.5. The paths are refundo's. Each entry ends with a caveat, because none
of them is a plain defect.

**An annotation queue holds runs and threads, and not the cases of a dataset.** Read in the docs, on the page
about annotation queues: "A queue can contain a mix of run items and thread items." What needed a label here was a
case: an account's records against the policy, before any agent had run. So the labels were made on a page of
refundo's own, `world/label_app.py`. Caveat: LangSmith is a platform for traces, and a general tool cannot cover
every way that a team labels.

**A model that LangChain does not know gets 4,096 output tokens, thinking included.** Read in the source:
`ChatAnthropic` takes `max_tokens` from a table of known models and falls back to 4,096, and the table has no entry
for Claude Haiku 5.5. Seen on 2026-10-07, with the `structured` agent on that model at the highest reasoning
effort: each of the first 6 trials ended with no proposal and no error, and the job was stopped. With
`max_tokens` set to 32,000 in `agents/shared.py`, 236 of the 240 trials at that effort made a proposal. Caveat: the
model was new, and Anthropic's API needs a limit on every request. A warning that the fallback is in use would
have shown the cause.

**LangChain's default for a structured answer from an Anthropic model is a forced tool call.** Read in the source:
`with_structured_output` has `method="function_calling"` as its default, which forces the call, and a comment
there says that Anthropic's API refuses a forced tool call when thinking is on. Seen: the `pipeline` agent asks
for its decision as a structured answer, and on Claude Haiku 5.5 its first job was stopped with 9 right of the 24
trials that had finished. With `method="json_schema"` for an Anthropic model, in `agents/pipeline.py`, the same
agent got 234 of 240 right. Caveat: the rule is Anthropic's, and LangChain has the method that works. The default
is what cost the time.

**Harbor's LangSmith plugin counts an agent's tokens twice, and loses the result of a trial that ran again.** The
package is Harbor's and not LangChain's.
- Read in the source of harbor-langsmith 0.3.1: `_emit_usage_run` adds a model run to each trial with the trial's
  token total, for an agent that leaves no trace of its own. `_create_root_run` makes a run's id from the job and
  the trial's name.
- Seen in the model sweep: a run's `prompt_tokens` was exactly twice the tokens of its model calls, and its cost
  about twice. A LangGraph agent's trace already holds every model call, and LangSmith adds the two together.
- Seen in the same sweep: for 20 trials, every run that LangSmith held had ended in an error, and the job folder
  held a later attempt of the same trial with a result. Read from LangSmith alone, 9 experiments scored 1 to 3
  points lower than the result tables.
- `evals/langsmith_plugin.py` is a subclass that leaves out the extra run and gives a trial that runs again a run
  of its own. Caveat: it overrides methods that are not a public interface.

**One flag gives the experiment table.** Seen: with `--plugin langsmith`, Harbor made a dataset and an experiment
for each job, put the agent's trace under each trial, and wrote a score for each key of the grader's result.
