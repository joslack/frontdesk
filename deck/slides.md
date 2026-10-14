---
marp: true
title: Agent-native customer support for SaaS products
paginate: true
style: |
  section {
    background: #F7F6F2;
    color: #17212B;
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 30px;
    line-height: 1.45;
    padding: 70px 90px;
  }
  h1 { font-size: 56px; line-height: 1.15; font-weight: 650; color: #17212B; }
  h2 { font-size: 44px; font-weight: 650; color: #17212B; margin-bottom: 0.6em; }
  strong { color: #2F5BD9; }
  code { background: #E8E6DF; color: #17212B; border-radius: 4px; }
  section::after { color: #7A858F; font-size: 18px; }
  .small { font-size: 22px; color: #5F6B76; }

  /* Lists and tables: rows separated by hairlines. */
  ul { list-style: none; padding: 0; }
  ul > li { margin: 0; padding: 11px 0; border-top: 1px solid #D6D3CA; }
  table { display: table; width: 100%; font-size: 24px; line-height: 1.35; }
  table tr, table tr:nth-child(2n) { background: none; border: 0; }
  table th, table td { border: 0; border-top: 1px solid #D6D3CA; padding: 9px 28px 9px 0; text-align: left; vertical-align: top; }
  table th { border-top: 0; border-bottom: 2px solid #17212B; color: #5F6B76; font-size: 20px; font-weight: 500; }
  table thead:not(:has(th:not(:empty))) { display: none; }
  table th:last-child, table td:last-child { padding-right: 0; }
  table td:first-child strong { color: #17212B; }
  section.dense { padding-top: 50px; padding-bottom: 50px; }
  section.dense table td { padding-top: 6px; padding-bottom: 6px; }
  blockquote { border: 0; padding: 0 0 12px 32px; color: #17212B; }

  /* Statement slides: one sentence under a rail. */
  section.statement { justify-content: center; }
  section.statement h1 { position: relative; margin: 0 0 0.5em; padding-top: 44px; }
  section.statement h1::before { content: ""; position: absolute; top: 7px; left: 0; right: 0; border-top: 2px solid #17212B; }
  section.statement h1::after { content: ""; position: absolute; top: 0; left: 0; width: 16px; height: 16px; border-radius: 50%; background: #17212B; }
  section.statement p { margin: 0; color: #5F6B76; }

  /* Rail of stages or steps: a name above a dot, a date and items below. */
  section.wide { padding-left: 72px; padding-right: 72px; }
  .tl { display: grid; grid-template-columns: repeat(5, 1fr); column-gap: 26px; }
  .st { display: grid; grid-template-rows: 68px 16px auto auto; align-content: start; min-width: 0; }
  .nm { align-self: end; padding-bottom: 14px; font-size: 26px; font-weight: 650; line-height: 1.2; }
  .rail { position: relative; }
  .rail::before { content: ""; position: absolute; top: 7px; left: 0; right: -26px; border-top: 2px solid #17212B; }
  .rail::after { content: ""; position: absolute; top: 0; left: 0; width: 16px; height: 16px; box-sizing: border-box; border-radius: 50%; background: #17212B; }
  .st:last-child .rail::before { display: none; }
  .st.now .rail::before { display: block; right: 0; border-top: 2px dashed #7A858F; }
  .st.now .rail::after { background: #F7F6F2; border: 4px solid #2F5BD9; }
  .dt { margin-top: 12px; font-size: 20px; color: #5F6B76; font-variant-numeric: tabular-nums; }
  .tl ul { margin: 16px 0 0; font-size: 22px; line-height: 1.3; }
  .tl ul > li { padding: 8px 0; }
  .tl.n7 { grid-template-columns: repeat(7, 1fr); column-gap: 18px; margin-bottom: 34px; }
  .tl.n7 .st { grid-template-rows: 46px 16px; }
  .tl.n7 .nm { font-size: 22px; }
  .tl.n7 .rail::before { right: -18px; }
---

<!-- _class: statement -->
<!-- _paginate: false -->

# Agent-native customer support for SaaS products

Frontdesk: the design, the evaluation of one backend agent, and the path to production

Jonah Slack

---

<!-- _class: todo -->

## How I want to deal with a business

![w:1100](images/my-agent.svg)

---

<!-- _class: todo -->

## What I think a business should build

- An **agent-native** interface to its records and processes
- **Agents of its own** for sub-processes inside
- Not necessarily a chatbot of its own

---

<!-- _class: todo -->

## Project goals

- An agent-native interface to customer support
- A deep dive into one sub-function, refunds

---

<!-- _class: todo -->

## Why I chose refunds

- Unvalidated input
- Dynamic world state, strict policy
- Real money

---

<!-- _class: todo wide -->

## Project timeline

<style scoped>
.tl { grid-template-columns: repeat(8, 1fr); column-gap: 14px; }
.nm { font-size: 19px; }
.rail::before { right: -14px; }
.tl ul { font-size: 17px; }
.tl ul > li { padding: 7px 0; }
</style>

<div class="tl">
<div class="st">
<div class="nm">Simulation building</div>
<div class="rail"></div>
<ul>
<li>Refund policy</li>
<li>Customer records</li>
<li><strong>80</strong> cases</li>
<li>Oracle</li>
</ul>
</div>
<div class="st">
<div class="nm">Evaluation setup</div>
<div class="rail"></div>
<ul>
<li>Labeling UI</li>
<li><strong>41</strong> hand labels</li>
<li>Rulings</li>
<li>Second review</li>
</ul>
</div>
<div class="st">
<div class="nm">Agent and environment</div>
<div class="rail"></div>
<ul>
<li>Harbor task per case</li>
<li>Its own Postgres</li>
<li>One MCP server</li>
<li>SQL agent</li>
</ul>
</div>
<div class="st">
<div class="nm">Model sweep</div>
<div class="rail"></div>
<ul>
<li>SQL agent</li>
<li>8 models</li>
<li>Each effort level</li>
<li><strong>37</strong> experiments</li>
</ul>
</div>
<div class="st">
<div class="nm">Agent ablation</div>
<div class="rail"></div>
<ul>
<li>4 agents</li>
<li>4 models</li>
<li>3 runs per case</li>
<li><strong>20</strong> experiments</li>
</ul>
</div>
<div class="st">
<div class="nm">Served agent</div>
<div class="rail"></div>
<ul>
<li>Human review</li>
<li>Customer chat</li>
<li>Reply judge</li>
<li>Online evaluator</li>
</ul>
</div>
<div class="st">
<div class="nm">Long accounts</div>
<div class="rail"></div>
<ul>
<li>Years of history</li>
<li><strong>94</strong> cases</li>
<li>4 agents</li>
</ul>
</div>
<div class="st">
<div class="nm">The product</div>
<div class="rail"></div>
<ul>
<li>Access over MCP</li>
<li>Jobs and review</li>
<li>On k3s</li>
</ul>
</div>
</div>

---

<!-- _class: todo whole -->

## Simulating a fictional SaaS product

| | |
|---|---|
| **Refund policy** | Grounded in the published policies of Zoho, Atlassian and Slack, with internal rules added |
| **Records** | Members, invoices, refunds, disputes, sessions, app events, support tickets |

---

<!-- _class: todo -->

## User needs for our fictional SaaS product

- Ask questions about my own records
- Get my records as a file
- Start a process: a refund, a bug report, a support question
- See the status of a request
- Do all of this through my own agent

---

<!-- _class: todo whole -->

## What an agent can do

| I say | The agent calls |
|---|---|
| "How much did my team use the product last week?" | `run_sql` |
| "Export all of our invoices." | `export_csv` |
| "I found a bug." | `open_request` |
| "We have not used it. I would like a refund." | `open_request` |
| "What is the status of my request?" | `get_request` |

---

<!-- _class: todo whole -->

## What an agent can access

<style scoped>table td:not(:first-child), table th:not(:first-child) { text-align: center; } table td { font-size: 28px; }</style>

| | Own records | Billing | Usage totals | Everyone's activity |
|---|---|---|---|---|
| **Member** | ✓ | | | |
| **Billing admin** | ✓ | ✓ | ✓ | |
| **Owner** | ✓ | ✓ | ✓ | ✓ |

---

<!-- _class: todo -->

## What the business needs to do on the backend

- Route to the correct specialized agent
- Reliably execute jobs
- Receive human input
- Respond or take action

---

<!-- _paginate: false -->

![bg contain](images/architecture.svg)

---

<!-- _class: statement -->

# Demo

---

<!-- _class: todo -->

![bg right:34% contain](images/labeling-ui.png)

## Labeling the cases by hand

- **80** small accounts, about **1,800** tokens each
- **94** long accounts, about **49,000** tokens each
- Labelled **41** cases manually
- First pass accuracy: **34 of 41**, 83%
- Improving internal consistency: **4** policy gaps, **1** oracle bug
- **2 min 45 s** a case

---

## How a case is run

<div class="tl">
<div class="st">
<div class="nm">Case</div>
<div class="rail"></div>
</div>
<div class="st">
<div class="nm">Harbor task</div>
<div class="rail"></div>
</div>
<div class="st">
<div class="nm">Agent</div>
<div class="rail"></div>
</div>
<div class="st">
<div class="nm">Verifier</div>
<div class="rail"></div>
</div>
<div class="st">
<div class="nm">LangSmith</div>
<div class="rail"></div>
</div>
</div>

---

<!-- _class: dense -->

## Model sweep

<style scoped>section { padding-top: 36px; padding-bottom: 30px; } h2 { margin-bottom: 0.15em; } p { margin: 0.15em 0; font-size: 24px; } p:has(img) { text-align: center; margin-top: 10px; }</style>

The SQL agent on **8** models at every reasoning effort: **37** experiments in LangSmith.

![w:1100](images/model-sweep.png)

---

<!-- _class: whole -->

## Four agents

| Agent | Tools the model calls |
|---|---|
| **sql** | `get_request_context` `list_tables` `run_sql` `submit_proposal` |
| **structured** | `get_request_context` `get_requester` `list_charges` `get_subscription` `get_usage` `list_tickets` `list_account_credits` `submit_proposal` |
| **case_file** | `get_case_file` `submit_proposal` |
| **pipeline** | None. Code calls `get_case_file` and `submit_proposal` |

---

<!-- _class: dense -->

## Agent comparison

<style scoped>section { padding-top: 36px; padding-bottom: 30px; } h2 { margin-bottom: 0.15em; } p { margin: 0.15em 0; font-size: 24px; } p:has(img) { text-align: center; margin-top: 10px; }</style>

**4** agents on **3** models, and **8** more experiments on Claude Haiku 5.5: **20** in LangSmith. Each case ran **3** times.

![w:1100](images/agent-comparison.png)

---

<!-- _class: todo whole -->

## Longer accounts

| Agent | Right, of 94 | Cost a case | Seconds a case | Input tokens a case |
|---|---|---|---|---|
| **structured** | 93 | $0.012 | 37 | 59,600 |
| **case_file** | 93 | $0.023 | 31 | 119,500 |
| **sql** | 92 | $0.013 | 80 | 89,000 |
| **pipeline** | 93 | $0.020 | 41 | 56,000 |

---

<!-- _class: todo whole -->

## Judging replies offline

<style scoped>h2 { margin-bottom: 0.05em; } .sub { margin: 0 0 0.9em; font-size: 27px; font-weight: 500; color: #5F6B76; }</style>

<div class="sub">OpenAI Decisions API (released October 6, 2026) and code</div>

**2,875** replies from the finished experiments, for $0.76.

| Replies flagged | DeepSeek V4.1 Flash | GLM-5.3 Flash | GPT-6 Luna |
|---|---|---|---|
| **Made stuff up** | 117 of 960 | 129 of 955 | 6 of 960 |
| **Rude** | 0 | 0 | 2 |
| **Prompt injection** | 0 | 0 | 0 |
| **States a different dollar amount than proposed** (code) | 0 | 0 | 0 |
| **Reveals internal identifiers** (code) | 3 | 3 | 0 |

---

<!-- _class: todo -->

## Applying the same method online: Jev in LangSmith

| | |
|---|---|
| **The customer** | "cancel for me" |
| **The agent** | "Done — I've submitted the cancellation on your Workspace, so the subscription won't renew on Oct 8." |
| **Its tools** | It has no tool that cancels. It called no tool |
| **Jev** | "Says something was done that no tool did": **0.93** |
| **When it declined** | **0.04** to **0.23** |

---

<!-- _class: todo -->

## Each part needs a deep evaluation

<style scoped>
.tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; }
.tiles > div { display: flex; flex-direction: column; gap: 6px; padding: 22px 24px; border: 1.5px dashed #9AA3AB; border-radius: 10px; background: #FFFFFF; }
.tiles b { font-size: 28px; font-weight: 650; }
.tiles span { font-size: 21px; color: #5F6B76; }
.tiles .on { border: 2.6px solid #2F5BD9; }
.tiles { margin-bottom: 26px; }
.tiles .on span { color: #2F5BD9; font-weight: 600; }
</style>

<div class="tiles">
<div class="on"><b>Refunds</b><span>Evaluated in depth</span></div>
<div><b>External tools and skills</b></div>
<div><b>Support tickets</b></div>
<div><b>Bug reports</b></div>
<div><b>Retention desk</b></div>
</div>

---

<!-- _class: todo wide -->

## Deploying locally on k3s

<style scoped>
section { padding-top: 40px; padding-bottom: 34px; }
h2 { margin-bottom: 0.25em; }
p { margin: 0; }
.small { display: block; margin-top: 8px; font-size: 20px; }
</style>

![w:1136](images/k3s.svg)

---

<!-- _class: todo dense -->

## Path to production

| | |
|---|---|
| **Infrastructure** | Plug in to the customer's infrastructure, or deploy in it |
| **Auth** | Harden SQL access for external users. Add auth between services |
| **Job durability** | Failure recovery, retries, provider rate limits |
| **Guardrails** | Detect prompt injection and harmful content |

---

<!-- _class: todo dense -->

## Trade-offs

- A business agent vs. **exposing tools for external agents**
- **Async** vs. real time
- **Managed** vs. custom
- **Limiting tools** vs. expressive tools

---

<!-- _class: todo -->

## Open questions

- Who owns the agent a customer talks to?
- Can a company instruct an agent it does not own?
- Should a company's agent negotiate?
- How do we evaluate how well external agents can use our interface?

---

<!-- _class: todo dense -->

## Friction log

- Annotation queues
- A model released that day
- Structured answers and thinking
- Harbor's LangSmith plugin
- What worked well

---

<!-- _class: todo -->

## Conclusions and next steps

- **93 of 94** long accounts right
- The agent: **$0.012** and **37 s** a case
- A person at $30 an hour: **$1.38** and **2 min 45 s** a case
- **Next:** evaluate over "real" historical refund decisions
- **Then:** the other interfaces, support tickets, bug fixes

