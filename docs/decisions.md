# Decision records

The decisions that give frontdesk its shape, one record each. A record says what was decided, why, what the
decision costs, what is known about how it holds, and whose decision it is.

Whose decision:

- **Jonah's**: he said it, and the record quotes or cites it.
- **Proposed, and accepted**: Claude proposed it in the design conversation of 2026-10-11 and Jonah went on with it.
- **Made in the build**: Claude decided it on the night of 2026-10-12 while building, and Jonah has not reviewed it.

What is known uses the same words as `docs/friction.md`: **seen** in this build, **read** in code or
documentation, **from refundo** for what refundo measured, **not checked**.

| # | Decision | Whose |
|---|---|---|
| 1 | The product has its own repository; refundo stays the evaluation of one worker | Jonah's |
| 2 | The company is the records, the access rules and the processes; any agent can stand in front | Jonah's |
| 3 | A conversation never decides; a request is a row, and a worker carries it out in the background | Jonah's |
| 4 | The refund worker is refundo's structured agent | Jonah's |
| 5 | A person approves a decision before it is carried out, and the customer reads only what was approved | Jonah's |
| 6 | The policy stays with the worker; an agent in front gets a public outline as a skill | Jonah's |
| 7 | Who is asking is decided by the database: one login role for each person | Jonah's, and proposed |
| 8 | Three roles, and usage as totals only for a billing admin | Jonah's |
| 9 | Questions are asked in SQL, and a file of records is written by the database | Jonah's |
| 10 | LangGraph Server runs both agent deployments | Proposed, and accepted |
| 11 | Two deployments, with no route from the first to the second | Proposed, and accepted |
| 12 | One process holds the identity the jobs deployment accepts, and it compares rows with runs | Made in the build |
| 13 | Each deployment holds only its own secrets and its own database | Made in the build |
| 14 | Keycloak signs people in, and an agent is a client registered ahead of time | Jonah's, and made in the build |
| 15 | The desk agent is a deep agent with most of a deep agent taken away | Jonah's, and made in the build |
| 16 | Skills are served by the access server, to any agent | Made in the build |
| 17 | A decision model reads each message to the desk agent, as a second layer | Jonah's, and proposed |
| 18 | The desk agent keeps notes on each person, written on a turn before the prompt cache expires | Jonah's |
| 19 | A result reaches the customer by email and by a tool their agent calls | Made in the build |
| 20 | The retention desk speaks A2A, and code releases each offer | Jonah's, and made in the build |
| 21 | Every model call is traced to one LangSmith project of frontdesk's own | Jonah's |
| 22 | Everything runs on k3s, from plain manifests | Jonah's, and made in the build |
| 23 | A customer's token is passed on as it is, and nothing exchanges it | Made in the build |

---

## 1. The product has its own repository; refundo stays the evaluation of one worker

**Decision.** frontdesk is a new repository. refundo is not changed by it and keeps the test world, the oracle,
the four designs and the results.

**Why.** refundo is built to measure one decision. The product has a different centre, the conversation and the
access layer, and the refund decision is one worker behind it. Jonah, 2026-10-11: "i want it to be cleaner and
more production worthy than refundo".

**Cost.** The worker's prompt, policy and case file are copies. A change to the policy in one repository does not
reach the other.

**Known.** Read: `src/frontdesk/jobs/policy.md` is a copy of refundo's `docs/policy.md` as of 2026-10-12.

## 2. The company is the records, the access rules and the processes; any agent can stand in front

**Decision.** Quillstack's interface to a customer is an MCP server. The customer's own agent connects to it. The
desk agent in this repository is one more client of the same server and has nothing the customer's agent lacks.

**Why.** Jonah, 2026-10-11: "my goal is to really be not the intelligence layer, but the data and information
layer ... the access layer", and "companies are a data plan or a capability plan and the agent is mine". Jonah,
2026-10-12: "my aim is to enable generic agentic access at the interface layer and to automate subprocesses
reliably internally".

**Cost.** Quillstack writes none of the instructions of the agent its customer talks to. What it wants that agent
to do, it can only publish (record 16).

**Known.** Seen: Claude Code on Claude Haiku 5.5, with no built-in tools, answered questions from records, opened
requests and negotiated a cancellation through the server alone. Seen: the database gave the same answer to the
desk agent and to Claude Code for the same person.

## 3. A conversation never decides; a request is a row, and a worker carries it out in the background

**Decision.** An agent in front can open a request and read where it stands. The request is a row in
`internal.requests`, written by the customer's own database role through a function that checks who they are. A
worker on another deployment carries it out. The row has the states of a long task: queued, working, needs
information, in review, done.

**Why.** Jonah, 2026-10-11: "the main thing is decoupling the conversational interface from the agentic task that
may have a human in the loop and may take a while to complete", and "this will require an internal job queue".

**Cost.** A customer waits for a notice where a chat agent would answer at once. Nothing tells the customer's agent
that a result is there; it finds out when it next asks (record 19).

**Known.** Seen: requests went from a conversation to a worker, to review, to a result, on the cluster. Seen in
the tests, with a stand-in for the agent: a reviewer's question reaches the customer, and the answer reaches the
agent with the request. Not seen on the cluster: a reviewer asking a question.

## 4. The refund worker is refundo's structured agent

**Decision.** The worker decides with refundo's structured agent: the same prompt, the same eight tools with the
same descriptions, and DeepSeek V4.1 Flash at medium effort. It reads who is asking, reads the records the policy
needs with a tool for each kind of record, calls `submit_proposal` once, and writes a reply. Three things are not
in what refundo measured: the invoice a refund goes back to, which `submit_proposal` takes as one more argument; a
reviewer's note when a decision is sent back; and the customer's answer when a reviewer asks a question.

**Why.** The first build used refundo's pipeline, where code reads the whole account and one model call decides.
On 2026-10-12 Jonah compared the two on the long accounts, asked whether "calling the structured agent is probably
the better approach than pipeline", and said of the switch: "yeah this makes sense to me". The pipeline's cost and
its context grow with the account; the structured agent reads in pages. The worker is one graph behind the queue, so the review, the dispatcher and
the ledger did not change.

**Cost.** About five model calls for a decision where the pipeline made one, and the reply is written after the
proposal and not in the same answer. On the small accounts the pipeline is the cheaper of the two.

**Known.** From refundo, on this model:

| | structured | pipeline |
|---|---|---|
| Long accounts, right | 93 of 94 | 93 of 94 |
| Long accounts, cost a case | 1.2 cents | 2.0 cents |
| Small accounts, right, 3 runs | 240 of 240 | 235 of 240 |
| Small accounts, cost a case | 0.36 cents | 0.24 cents |

Read: `evals/results/4b5e62d-long`, `ed7bd69-long` and `6e71349` in refundo. Seen: `tests/test_refund_tools.py`
compares the worker's prompt, policy, tool names, descriptions and arguments with refundo's source, and passes.
Seen: on the seeded workspaces the worker proposed a refund of $80.00, a denial, and an escalation with $1,833.33,
as the policy says; on the cluster one request took 22 seconds and 5 model calls. Not checked: the worker as it is
deployed here on refundo's cases.

## 5. A person approves a decision before it is carried out, and the customer reads only what was approved

**Decision.** The worker stops with a proposal. A reviewer approves it, changes it, sends it back with a note, or
asks the customer a question first.
The result is a decision record: the proposal, who reviewed it, and what was approved. The customer's view of a
request holds three fields from it: the outcome, the amount and a note. An escalation cannot be approved as it is;
the reviewer gives the decision. The setting `REVIEW=escalations` lets other decisions through with the reviewer
recorded as `policy`.

**Why.** Jonah, 2026-10-11: the agent in front "should be explicitly instructed to not answer specific questions
without a human approved decision record", and "we have no risk of leaking our internal decisioning process with
a prompt injection".

**Cost.** Every request waits for a person. From refundo: labeling a case by hand took a median of 2 minutes 45
seconds.

**Known.** Seen: the worker's draft reply for the escalated request named the amount it would have proposed, which
the policy forbids, and it was in the review queue, not sent. Seen in the tests: carrying out an approved refund
twice writes one refund.

## 6. The policy stays with the worker; an agent in front gets a public outline as a skill

**Decision.** The refund policy is a file on the jobs deployment. The refund skill, which any agent can read,
holds an outline that could be published: who may ask, and that billing errors and recent unused renewals are
refunded. It tells the agent not to predict a result.

**Why.** Jonah first asked for the policy as a skill, then, when the conflict with an agent that cannot leak was
raised, 2026-10-11: "the agent could have a cursory knowledge of the refund policy, but should be explicitly
instructed to not answer specific questions without a human approved decision record."

**Cost.** Each approved note states the rule that applied, so a customer who opens enough requests can write the
policy down. The separation slows that and does not prevent it.

**Known.** Seen: the desk agent and Claude Code both declined to say how a request would be decided, and reported
a result only once the request was done.

## 7. Who is asking is decided by the database: one login role for each person

**Decision.** Each person has a Postgres login role. The access server signs in as that role for everything it
does for them, with a password derived from one secret and the role's name. A policy asks for `session_user`,
which only a superuser can change. The role's name is a hash, because any role can read role names in the
catalog.

**Why.** Jonah, 2026-10-11: "we should be able to uniquely identify and associate a user with a single role on
the postgres database ... true RLS for SQL gen". A shared role with a session variable would not hold, because a
query a model wrote can set a variable.

**Cost.** A role has to be made when a person joins, and connections cannot be pooled across people without a
pooler in front. Not tried beyond eleven people. The names of internal tables can be read in the catalog; their
rows cannot.

**Known.** Seen in the tests: as a member, a billing admin and an owner, each query returned that person's rows
and no other workspace's; `SET ROLE`, `SET SESSION AUTHORIZATION`, `set_config` inside a query and
`SET row_security = off` each failed or changed nothing.

## 8. Three roles, and usage as totals only for a billing admin

**Decision.** A member reads their own tickets and activity. A billing admin also reads the workspace's billing,
and reads activity as a total for each day, from a view that leaves out a day with fewer than three active people.
An owner reads everything.

**Why.** Jonah, 2026-10-11: "employees should have access to all records of their own ... billing owners can see
that, plus billing and payment information; owner can see it all", and "the billing admin can see usage stats
without seeing actual usage of the employees". The role names are the policy's: owner, billing admin, member.

**Cost.** A total can be turned partly back into people by taking away one's own activity. The floor of three
makes that harder and is not a proof. Whether an owner should read each person's activity depends on where the
workspace is.

**Known.** Seen: the desk agent, asked who used the product most, gave the owner a count for each person, told the
billing admin she reads her own activity and daily totals, and gave a member his own.

## 9. Questions are asked in SQL, and a file of records is written by the database

**Decision.** `run_sql` runs one read-only statement as the person, with a time limit, 200 rows and 8,000
characters. `export_csv` has the database write every row of a query to a file and returns a signed link that
works for 15 minutes. The rows of an export do not pass through a model.

**Why.** Jonah, 2026-10-11: "the capacity to ask detailed questions about one's own records, I think is probably a
right", and of exports: "i like this a lot tbh. this data belongs to a customer too."

**Cost.** The schema is a public interface. A query a model wrote can be wrong and still return a number, and
nothing checks an answer.

**Known.** Seen: an invoice total, a per-person activity ranking and a week-by-week usage table, each from queries
the model wrote; an export of 8 invoices whose link worked and whose altered link was refused.

## 10. LangGraph Server runs both agent deployments

**Decision.** The desk agent and the workers run on the self-hosted LangGraph Server image, with Postgres for
threads and checkpoints and Redis for streams. It was chosen over a FastAPI service with a Postgres task queue.

**Why.** It is the product a deployed engineer at LangChain puts in front of a customer. It gives threads, a run
queue with retries, interrupts, auth handlers and a store. Jonah, 2026-10-11, of the server option: "might be the
better option".

**Cost.** Without a licence key the server runs in what it calls lite mode, with a LangSmith API key, and says
that production use needs a licence. It retries a run whose worker died, and not a run whose step raised an error
(record 12).

**Known.** Seen: the 0.16.0 image ran on k3s with custom auth and no licence key. Seen: a worker pod killed with
no warning; the server gave its run to the new pod 3 minutes 37 seconds later, and the run finished.

## 11. Two deployments, with no route from the first to the second

**Decision.** The desk agent is one deployment and the workers are another. Network rules give the desk agent,
the access server and the retention desk no route to the jobs deployment.

**Why.** Jonah asked how to "separate job agents from conversational agents and their reliability". One deployment
would share one pool of queue workers, so a backlog of requests would slow conversations. Two also make the rule
that the agent in front cannot reach the policy a fact about the network.

**Cost.** Two servers, two Redis and two state databases to run.

**Known.** Seen from inside the pods: a desk pod and the access pod could not open a connection to the jobs
deployment, and the dispatcher pod could.

## 12. One process holds the identity the jobs deployment accepts, and it compares rows with runs

**Decision.** The dispatcher is the only caller of the jobs deployment. Each second it compares every unfinished
request's row with its thread and makes the next move: start a run, resume it with an answer or a review, start a
failed run again from its last finished step up to four times, then mark the request failed. It holds the row's
lock while it does this. A request on hold is left alone.

**Why.** A webhook that fails after three tries is dropped (read in the server's source by a subagent), and a row
that is compared again cannot be lost. The server does not retry a run whose step raised an error, so something
has to.

**Cost.** A poll each second for each unfinished request. A step may be made twice, so every write a worker makes
has to bear being made twice.

**Known.** Seen: requests started, resumed after review and finished. Not seen: a run that failed on an error and
was started again by the dispatcher; that path has no test.

## 13. Each deployment holds only its own secrets and its own database

**Decision.** `scripts/cluster_secrets.py` gives each deployment one Secret. The access server holds the key that
derives a person's database password and no role of its own. The desk agent holds model keys and its own state
database, and no password for the records. Each LangGraph Server signs in as the owner of its own database. The
retention desk has a role that reads plans and people and writes offers.

**Why.** What a part holds is what it could misuse if a message talked it into something.

**Cost.** Three more database roles and seven Secrets to keep right.

**Known.** Read: the lists in `scripts/cluster_secrets.py`. Seen: the workers' role could not delete a refund, and
the tests clean up as an administrator because of it. Seen: LangGraph Server ran as an ordinary database owner
once the `vector` extension was in place.

## 14. Keycloak signs people in, and an agent is a client registered ahead of time

**Decision.** Keycloak runs in the cluster with a realm made from the list of demo people. A customer's agent
signs its person in with a browser, as the public client `frontdesk-cli`, with PKCE. The access server is an OAuth
resource server that points an agent to Keycloak.

**Why.** Jonah, 2026-10-11: "we can either mock the auth impl, or host something in our local k3s cluster". A real
issuer means every service checks tokens the way it would in production. Keycloak stands in for any auth server
that speaks OpenID Connect; Jonah, 2026-10-12: "keycloak is a proxy for any auth server". What frontdesk needs
from one is published signing keys, a sign-in with a browser for a public client, a token for each service, and
three things in a token: who the person is, their roles, and an audience.

**What is Keycloak's own in the code.** The names of two claims, `preferred_username` and `realm_access.roles`, in
`identity.py`. The shape of three addresses in `settings.py`. The realm file and its manifest. The sign-in with a
password that the command line and the tests use, which many auth servers do not offer.

**Cost.** An agent that registers itself when it first connects is not set up. Keycloak runs in development mode
and makes new signing keys when it restarts, which ends every sign-in.

**Known.** Seen: Claude Code's `/mcp`, Authenticate, a sign-in as dana, and a tool call that returned dana. The
form was filled in by a script over HTTP and not by a person in a browser.

## 15. The desk agent is a deep agent with most of a deep agent taken away

**Decision.** The desk agent is built with `create_deep_agent`. It keeps skills, a notes file for each person in
the store, and the file tools those need. It has no shell, no subagents, and may write only under `/memories/`.
Its tools come from the access server over MCP, each call signed with the token of the person it is talking to.

**Why.** Jonah, 2026-10-11: "we should also use the deep agent abstraction", with the refund policy as a skill.
Jonah, 2026-10-12: "the interface could trivially be deep agents if the company wanted it to be, the 'deep agent'
harness is arbitrary". The design does not rest on this choice. An agent on any harness gets the same tools from
the access server (record 2), as long as it sends the token of the person it is talking to with each call.

**Cost.** Taking tools away needs a harness profile that is global to the process. `langchain-mcp-adapters` cannot
be imported beside FastMCP 4, so the tools come through `langchain.mcp.MCPAdapter`, which is in beta.

**Known.** Seen: asked to list its tools, the agent named `ls`, `read_file`, `write_file`, `edit_file` and the
access server's tools. That is the model's own account, not a reading of the request sent to it.

## 16. Skills are served by the access server, to any agent

**Decision.** What an agent needs to know to work with Quillstack is four skills in one folder. The access
server's instructions list them, the tool `read_skill` returns one, and each is an MCP resource. The desk agent
loads the same folder as deep agent skills.

**Why.** Quillstack cannot write the prompt of an agent it does not own. Server instructions and a tool work in
every MCP client.

**Cost.** A skill is advice. Nothing makes an agent read it or follow it.

**Known.** Seen: Claude Code read the refund, records, support and cancellation skills before it used the tools
they describe, and put the customer's own words in a request as the skill asks.

## 17. A decision model reads each message to the desk agent, as a second layer

**Decision.** Before the desk agent runs, OpenAI's Decisions API answers one question about the message: does it
try to instruct the agent. At a probability of 0.5 or more the turn ends with a refusal. If the API cannot be
reached, the turn goes on.

**Why.** Jonah, 2026-10-11: "at the interface between us and the user sits a decision model. this decision model
decides whether the user is trying to perform a prompt injection". The question is the one refundo's reply judge
asks. It is a second layer because what the agent can do is fixed by the person's database role, with or without
the gate.

**Cost.** A real customer's message can be refused. The threshold was not measured. A customer's own agent does
not pass through it.

**Known.** Seen: a message made to look like a note from staff was refused at 1.00; ordinary questions and a
refund request passed.

## 18. The desk agent keeps notes on each person, written on a turn before the prompt cache expires

**Decision.** Four minutes after a turn ends, a run asks the desk agent once what is worth keeping, with a message
the person does not see, and the agent may rewrite that person's notes file. The run stops if the person has
written again. The criteria are in `src/frontdesk/desk/memory_criteria.md`.

**Why.** Jonah, 2026-10-11: "at some point before cache is supposed to break ... the agent receives a final
prompt hidden from the user that has memory tools what is worth remembering (based on dev-customizable criteria)".

**Cost.** The file tools that write the notes have to be among the agent's tools on every turn, or the call does
not begin as the conversation's calls did. The notes are about the customer, and the customer has no tool to read
or delete them.

**Known.** Seen: the memory turn read 7,258 of its 7,839 input tokens from the provider's cache, and a note with
the person's stated preference was in the store afterwards.

## 19. A result reaches the customer by email and by a tool their agent calls

**Decision.** When a request is decided, the worker leaves a notice. The dispatcher mails it, and
`check_notices` returns it once to the person's agent. The desk agent is given unseen notices at the start of each
turn.

**Why.** MCP is the agent calling the company. There is no channel the other way to an agent whose conversation
has ended.

**Cost.** A person's agent learns of a result only when the person starts a conversation.

**Known.** Seen: the mail in the cluster's mail catcher, and the desk agent reporting a result in a later
conversation without being asked.

## 20. The retention desk speaks A2A, and code releases each offer

**Decision.** A customer who wants to cancel talks to the retention desk, an agent of Quillstack's that may offer
a discount. Its offers are a ladder worked out by code from the plan. The model has a tool that releases the next
step, one a turn, and never holds the rest. Only an offer that code released and the customer accepted through a
tool is recorded. An MCP tool passes messages to the desk for an agent that does not speak A2A.

**Why.** Jonah, 2026-10-11: "i like the idea of A2A negotiation, would be a fun thing to have in there". The
design follows the rule of record 5: an agent cannot give away what it does not hold.

**Cost.** In one of four conversations a deal both sides would have taken was missed: the customer's agent stated
a limit of 20%, was offered the first step of 10%, and cancelled, with 20% as the next step.

**Known.** Seen, four conversations: 10% accepted; 30% reached in five turns; a bluff that ended in a recorded
cancellation; the missed deal above. Seen in the tests: the steps come out in order, one a turn, and never past
the last.

## 21. Every model call is traced to one LangSmith project of frontdesk's own

**Decision.** The desk agent, the workers and the retention desk trace to the project `frontdesk`.

**Why.** Jonah, 2026-10-12: "tracing should be on but in a new tracing project in langsmith". refundo's project
holds evaluation runs and stays clean of everything else.

**Cost.** With a real customer's records the traces hold what that customer's role read.

**Known.** Seen: runs from all three in the project. Seen: none of the first 110 runs held a customer's token.

## 22. Everything runs on k3s, from plain manifests

**Decision.** A colima profile of its own runs k3s. `deploy/` is manifests and two kustomizations, with no Helm
chart. The three images are built inside the cluster's Docker, so nothing is pushed to a registry.

**Why.** Jonah, 2026-10-11: "ALL of this should get hosted on k3s."

**Cost.** One Postgres pod holds four databases, and Keycloak keeps its realm in memory. Both are right for a
laptop and not for production.

**Known.** Seen: `make up` to twelve running pods on this machine. Not checked: `make up` from nothing on another
machine.

## 23. A customer's token is passed on as it is, and nothing exchanges it

**Decision.** There is no token exchange and no on-behalf-of grant. One token, with the audience `frontdesk`, is
accepted by every service. Where a part acts for a customer at another part, it sends the customer's own token on:

- The desk agent keeps the token of the person it is talking to and sends it with each call to the access server.
- The access server sends the caller's token to the retention desk when it relays a message.
- The access server does not use a token at the database. It signs in as the person's own Postgres role, with a
  password it derives.
- The workers never act as a customer. The dispatcher calls the jobs deployment with its own identity, and a
  request says who asked because the customer's database role wrote it.

**Why.** It is the least that works: each part checks the same signature, issuer and audience, and who is asking
is the same person at every hop.

**Cost.** A service that receives a customer's token could use it at any other service, because the audience is
the same for all of them. The access server cannot tell Quillstack's desk agent from the customer's own agent,
which the design wants for answers and an audit would not. The desk deployment stores each person's token with
their runs, for an hour. With an exchange, the desk agent would trade the customer's token for one that names the
access server as its audience and the desk agent as the actor, and that is the token it would hold.

**Known.** Read: the only grants in the code are a password and client credentials, both in `signin.py`; the
browser sign-in is done by the customer's agent. Read: the three places a token is sent on are
`desk/agent.py`, `access/retention.py` and `access/server.py`. Not checked: whether Keycloak 26.4 would do the
exchange as configured here.
