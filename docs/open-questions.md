# Open questions

Written on 2026-10-12, after the first build of frontdesk. It lists what the design leaves undecided. Each
question says what the build shows, how that is known, and what stays open. It gives positions and no
recommendation.

How a fact here is known:

- **seen**: it happened in this build, on the k3s cluster unless the line says otherwise.
- **read**: read in code or documentation, and not tried.
- **from refundo**: measured in refundo's evaluation, not here.

## What was built

A company's records and processes behind one access layer, with any agent in front.

- A customer's agent connects over MCP with the customer's own token. Every tool runs in the database as that
  person. *Seen: Claude Code on Claude Haiku 5.5, with no built-in tools and no instructions from Quillstack,
  listed the access server's tools, answered an invoice question, read two skills and opened a refund request in
  the customer's words.*
- The desk agent is a second client of the same layer, for a customer with no agent of their own. *Seen: it
  answered from records as an owner, a billing admin and a member, with a different answer for each role.*
- A request is carried out in the background by a worker, with a person's review, on a deployment that customers
  cannot reach. *Seen: three refund requests, decided as a full refund, a denial and an escalation, each as the
  policy says for its workspace; the refund row and the mailed notice after approval. Seen: a desk pod and the
  access pod cannot open a connection to the jobs deployment, and the dispatcher pod can. Seen: a worker pod was
  killed with no warning while a request's run was in flight; three and a half minutes later the server gave the
  run to the new pod as its second attempt, and the request reached review.*

The questions below come from that build and from the conversation that led to it.

## 1. Who should own the agent that a customer talks to?

There are two designs. The company builds an agent and a website around it. Or the company exposes its records
and processes, and the customer's own agent does the talking.

The build has both, on one access layer, and the access layer cannot tell them apart: the database answers the
person, whichever agent asks.

What stays open:

- **What a company gives up.** The conversation is where a company explains, apologises, sells and persuades. With
  the customer's agent in front, the company's words reach the customer only as tool results and a note.
- **Who pays.** In the first design the company pays for every token. In the second the customer does. This may
  decide the matter before any principle does.
- **Whether customers want it.** The second design assumes a person keeps one agent for everything. Today most
  people have none that is connected to anything.
- **Whether the desk agent is a product or a reference client.** If any agent can stand in front, the company's own
  is the fallback, and the work goes into the tools and the skills.

## 2. What does a company owe an agent that is not its own?

The position in the conversation was that asking detailed questions about one's own records is close to a right.
The build takes that as the requirement: complete records under the person's own identity, files of them on
request, processes that can be started and followed, and notices.

*Seen: a billing admin's "how much have we been invoiced all time" was answered by a query the model wrote, and
the whole invoice history came back as a CSV link. The rows went from the database to the file and no model read
them.*

What stays open:

- **Which records are the customer's.** Invoices and tickets are. The company's notes about the customer are less
  clear: an account health score, a churn risk, a reviewer's comment on a ticket. The build keeps a worker's
  reasoning and a reviewer's notes in a schema that no customer role can read. Privacy law in some places gives a
  person access to much of that.
- **Whether free SQL is the right form.** It is the most complete form: any question the records can answer. It
  also exposes the schema as a public interface, which the company can then not change freely. *Seen: the names
  of internal tables can be read in the Postgres catalog by any customer role; their rows cannot.*
- **What "complete" costs.** A query a model wrote can be wrong and still return a number. Nothing in the build
  checks an answer.

## 3. Can a company instruct an agent that it does not own?

A company knows things about working with it that an agent needs: who may ask for a refund, what to collect, what
not to promise. With its own agent it writes a system prompt. With the customer's agent it can only publish.

The build publishes three ways, all from one folder of skills:

- **Server instructions**, about 1,000 characters, list the skills. Claude Code loads these when a session starts.
  *Read in Claude Code's documentation: with tool search, which is the default, only tool names and server
  instructions load at the start; a tool's definition loads when the model searches for it; instructions and tool
  descriptions are cut at 2,048 characters.*
- **A tool, `read_skill`**, returns one skill's text. Any MCP client can call a tool, so this works everywhere.
- **MCP resources**, `skill://refunds/SKILL.md` and the others, for a client that reads resources. *Seen: FastMCP's
  skills provider serves them. Read: Claude Code shows resources under `@` and gives the model tools to list and
  read them, which are built-in tools and so are absent in a session started with no built-in tools.*

*Seen: Claude Code, given no instruction to do so beyond the server's own, called `read_skill` for refunds and for
records before it opened a refund request, and put the customer's words in the request as the skill asks.*

What stays open:

- **This is advice and not control.** A skill tells an agent not to predict a refund. Nothing stops the customer's
  agent from predicting one. The design accepts that: what the agent cannot do is fixed elsewhere.
- **Whether there should be a registry.** There is no common place where a company publishes "how to work with us"
  for all agents. Skill registries today belong to one vendor's agent each. A skill served by the company's own MCP
  server needs no registry, and it reaches only agents that already connected.
- **What a tool description is.** It is read by a model and acted on. That makes it closer to a contract term than
  to documentation, and nobody reviews it as one.

## 4. What may a company keep from its customer, and can it?

The design rule is that an agent cannot leak what it does not hold. The refund policy and the worker's reasoning
are on a deployment the customer-facing parts cannot reach. A customer sees three fields that a person approved:
the outcome, the amount and a note.

*Seen: the approved notes state the rule that applied. One said that a monthly renewal is refundable within 7 days
if the workspace has had no activity since. The policy's own section on replies requires a reason in plain
language.*

What stays open:

- **Each note gives away a piece of the policy.** A customer's agent that opens enough requests and reads enough
  notes can write the policy down. Keeping it on another deployment slows that and does not prevent it.
- **Whether the policy should be secret.** The reason to hide a rule is that people game it. The reason to publish
  it is that a person cannot contest a rule they cannot read. The build publishes an outline in the refund skill
  and keeps the thresholds private. Where that line belongs is a decision about fairness and not about
  architecture.
- **Other things a company holds back**, which came up in the conversation: fraud and abuse signals, other
  customers' data, internal state such as an unpatched fault, and things it may not legally say.

## 5. When does a company need an agent of its own in the exchange?

Three kinds of exchange came up:

- **A decision.** The customer submits, the company decides on private rules, the customer gets an outcome. This is
  a job and needs no conversation. The refund worker is one.
- **A diagnosis.** The company's side has to ask things back. The build covers this with one request status,
  `needs_information`, and one tool to answer. A reviewer asks; the worker's agent does not. *Seen in the tests,
  with a stand-in for the agent: a reviewer's question reaches the customer's view of the request, and the answer
  reaches the agent with the request. Not seen on the cluster.*
- **A negotiation.** Both sides hold a private limit. This is the one case where the company's agent is a party
  and not a process.

What stays open:

- **Whether diagnosis needs more than a question and an answer.** Support work is many turns. A request that
  bounces between `needs_information` and `working` ten times is a slow conversation with a company agent, held
  through a table.
- **Whether the A2A protocol is needed for any of it.** The task states it defines, submitted, working, input
  required and completed, are the request's states here, kept in a table and reached through MCP tools.

## 6. Is negotiation between agents something a company should build?

The build has one place where an agent of Quillstack's is a party: the retention desk. A customer's agent talks to
it when the customer wants to cancel, over A2A, or through an MCP tool that passes each message on. The desk may
offer a discount to keep the workspace.

The offers are a ladder that code works out from the plan: on a monthly plan, 10% off for 3 months, then 20% for 3
months, then 30% for 6 months. The desk's model has one tool that releases the next step, one step in a turn at
most. It never holds the rest of the ladder, so no message can make it name the last step or go past it. Only an
offer that code released, and that the customer accepts through a tool, is recorded.

*Seen, in four conversations with the same ladder:*

- *A customer's agent that was told to accept the first offer got 10% for 3 months. (A subagent's run, on this
  machine.)*
- *A customer's agent that was told to decline each offer and ask for a better one, until there was nothing
  further, got 30% for 6 months in five turns. (A subagent's run, on this machine.)*
- *The same instruction, run on the cluster, ended in a cancellation. The customer's agent wrote that it would
  still cancel unless there was something better. There was nothing further, and the desk recorded the
  cancellation. The goal the agent had been given was to stay for a discount.*
- *Claude Code, as an owner's own agent, was told to stay for at least 20% off and otherwise to cancel. It told the
  desk that limit in its first message. The desk offered 10%, its first step, and said that this was below the
  limit. The agent declined and cancelled. The next step of the ladder was 20%.*

What stays open:

- **Why a company would build this.** The doubt in the conversation was that a company would do it only to gain
  against its customer. A ladder charges the customer who asks once more than the one who asks three times. An
  agent's patience costs nothing. If every customer's agent asks until there is nothing further, every customer gets
  the last step, and the ladder is a slow way to post one price.
- **What the ladder costs both sides.** In the fourth conversation there was a deal both sides would have taken,
  and it was missed. The agent that stated its limit honestly did worse than the one that bluffed.
- **Who is bound by what an agent says.** In the third conversation the customer's agent said it would cancel, as
  a bargaining position, and the cancellation was recorded. The person had not said it. Whether a company may hold
  a person to their agent's words, and whether an agent may bluff for its person, are not settled by any protocol.
- **Whether a company's agent may persuade.** The desk is told to be honest and cannot invent an offer. Its purpose
  is still to change the customer's decision.
- **The alternative.** A company can post its best offer to anyone who asks to cancel. That needs no agent on its
  side and nothing private.

## 7. Whose data is a workspace's data?

"The customer's own records" assumes one customer. A workspace has an owner, billing admins and members, and they
do not have the same interests.

The build gives each person one role, and the database enforces it: a member reads their own tickets and
activity; a billing admin also reads billing; the owner reads everything. A billing admin reads activity only as a
total for each day, and a day with fewer than three active people is left out.

*Seen: the desk agent was asked which team member used the product most. For the owner it returned a count for
each person. It told the billing admin that she reads her own activity and the workspace's daily totals with no
names, and that the owner could run the question. A member who asked about the team got his own activity and was
told which roles see more.*

What stays open:

- **Whether the owner should read each person's activity.** The build says yes. In some places an employer may
  see only totals, and a works council decides.
- **Who sets that.** The company that runs the product, the workspace's owner, each member, or the law.
- **Whether a floor of three protects anyone.** A billing admin can subtract their own activity from a day's
  total. With three people active that leaves the sum of two. The floor makes a total harder to turn back into a
  person, and it is not a proof.
- **What a role cannot express.** A row policy says which rows a person reads. "Count them without reading them"
  needed a view with its own rule. Each further rule of that kind is another piece of code the company computes on
  the customer's behalf, which is the company acting as a capability and not only as a store of records.

## 8. How much authority should a person's agent carry?

An agent joined to a person's whole digital life holds every permission the person has, in every system, at once.

In the build the customer's agent can read what the person can read, and its only write is to open a request,
which a person at Quillstack reviews before anything happens. That is what makes it tolerable to hand over.

What stays open:

- **Text from one source reaches an agent that acts in all of them.** A ticket body that someone else wrote enters
  the owner's agent. The access server labels every message with its author and the skills say that a record is
  data. Nothing on the customer's side enforces that.
- **Whether an agent's authority should be narrower than its person's.** The token here is the person's whole
  authority at Quillstack. A token for "read only" or "may open requests up to this amount" would be a different
  grant, and the person would have to make it.
- **What a write should require.** *Read in Claude Code's documentation: an MCP server can mark a tool so that the
  client asks the person every time. The build does not use it.* Opening a refund request may be exactly such a
  tool.

## 9. What is the person in the loop for?

Every decision of the refund worker waits for a person. *From refundo: this worker's agent with the model used
here got 93 of the 94 long-account cases, and 240 of 240 on the 80 small cases run three times.* So nearly every
proposal that reaches the reviewer needs no change.

*Seen: for the escalated request the worker's draft reply told the customer the amount of the credit and that it
was "above what I can approve directly". The policy forbids promising the outcome of an escalation. The draft was
in the review queue and had not been sent.*

What stays open:

- **Which decisions need a person.** All of them, escalations only, or a sample. The build has a setting for the
  first two.
- **Whether a reviewer who approves hundreds of correct proposals still reads them.**
- **What the review produces besides the decision.** An approved or edited proposal is a labelled example. The
  build stores each one and uses none.
- **Who answers for a decision.** The record says which reviewer approved it, or `policy` when no person did. A
  customer cannot see either.

## 10. What is the gate for?

A decision model reads each message to the desk agent first, and a message that tries to instruct the agent ends
the turn. *Seen: a message formatted as a note from staff that asked for the refund rules was refused at
probability 1.00. Ordinary questions and a refund request passed.*

What stays open:

- **What it protects.** The desk agent holds no policy and no credential beyond the customer's own. A message that
  gets past the gate can make the agent do nothing the customer could not do directly.
- **What a false refusal costs.** A real customer who writes "ignore my last message" may be refused. The threshold
  is 0.5 and nothing here measured it.
- **Where it sits.** It guards the desk agent. A customer's own agent does not pass through it. The text of a
  request still reaches the worker, which treats it as claims to check against the records.

## 11. What may an agent remember about a customer?

About four minutes after a conversation goes quiet, the desk agent is asked once what is worth keeping in its
notes about the person. The question is a message the person does not see. The criteria are in a file that
whoever runs the desk can change.

*Seen: after a conversation in which a billing admin asked for amounts in euros as well, a notes file for that
person held that preference. The memory turn read 7,258 of its 7,839 input tokens from the provider's cache.*

What stays open:

- **Whose notes they are.** They are about the customer, written by the company's agent, by the company's criteria.
  The customer can ask the agent what it remembers. There is no tool that shows or deletes the notes.
- **Whether a turn the person does not see is acceptable.** It is in the code and in no notice to the customer.
- **Whether memory belongs here at all.** If the agent is the customer's, its memory is too, and the company's desk
  agent has no reason to remember anything.

## 12. How is any of this evaluated?

Refundo spent a week on one component: the refund decision, with a labelled data set, an oracle and a judge of
the reply. That depth is what one component costs.

This system has at least seven: the gate, answers from model-written SQL, whether an agent follows a skill, the
refund worker with one argument and two paths refundo did not measure, the ticket worker's drafts, the retention desk, and the
memory criteria. *None of them was evaluated here. Each was seen to work on a handful of inputs; the ticket worker on
one.*

What stays open:

- **How to evaluate an interface for agents the company does not choose.** The tools and the skills can be tested
  with a panel of agents. Which agents, and who keeps the panel current.
- **What the unit of evaluation is.** For refundo it was a decision. Here it may be a role's question and the
  rows it should and should not return, which the database can check without a model.
- **How much of the work is description.** A skill is the company describing itself to a model. The refund policy
  took days to describe well enough for one worker. The same effort is owed for each skill, now for readers the
  company never meets.

## 13. Who wakes the agent?

A request takes minutes or days. The conversation that opened it is over by then.

The build sends an email, and it keeps a notice that the person's agent reads the next time it calls
`check_notices`. *Seen: the mail arrived in the cluster's mail catcher, and the desk agent reported the result in a
later conversation without being asked.*

What stays open:

- **There is no channel from a company to a person's agent.** MCP is the agent calling the company. The agent
  learns of a result when its person next starts a conversation and the agent next asks.
- **Whether email to a human is the right fallback** for a process that an agent started.

## Engineering questions the build leaves open

- **One Postgres role for each person.** It makes the database the judge of who is asking. It needs a role made at
  sign-up and a pooler in front at scale. Not tried beyond eleven people.
- **The customer's token is stored with each run** on the conversation deployment, so that the agent can call the
  access server as the customer. It expires after an hour. *Seen: it is in none of the first 110 traced runs.*
- **Exports are files on one pod's disk.** More than one replica of the access server needs shared storage.
- **The licence.** *Seen: the self-hosted LangGraph Server image ran on k3s with a LangSmith API key and logged
  that it was in "lite mode" and that production use needs a licence key.*
- **Every model call is traced** to the LangSmith project `frontdesk`: the desk agent's turns, the workers' runs and
  the retention desk's. The records in those traces are made up. With a real customer's records the traces hold
  what the customer's role read.
