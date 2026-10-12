---
name: support
description: How to pass a bug report, a billing question or any other support request to Quillstack's team, and how to report what they said. Read this before you open a request that is not a refund.
---

# Bug reports, billing questions and support requests

Some things only Quillstack's team can do: fix a bug, explain a charge that the records do not explain, change
something on the account. Pass these on as a request.

1. Look first. A question about a charge, a plan or a past ticket may already be answered in the records: see the
   skill `records`. An earlier ticket about the same problem is worth a mention in the request.
2. Call `open_request` with the kind that fits:
   - `bug_report`: something does not work as it should. Say what the person did, what happened, and what they
     expected.
   - `billing_question`: a question about a charge or an invoice that the records do not answer.
   - `support`: anything else.
   Write the message in the person's words.
3. Tell the person that Quillstack's team has the request and that they get a notice and an email with the answer.

To report on a request, call `get_request`. When its status is `needs_information`, put `question` to the person and
send their answer with `answer_request`. When it is `done`, `note` is the team's answer: give it as it is written.
