---
name: refunds
description: How to take a refund request for a Quillstack charge and report its result. Read this before you open a refund request or answer a question about whether a charge can be refunded.
---

# Refund requests

Quillstack decides every refund request itself, from its own records, and a person at Quillstack reviews the
decision. You do not decide a refund and you do not predict one. Your part is to pass the request on in the
customer's words and to report the result when there is one.

## What you can say about the rules

This outline is public. You may tell it to anyone.

- Only the Owner or a Billing Admin of a workspace can ask for a refund. A Member cannot.
- A billing error is refunded: a duplicate charge, a charge after a cancellation, a charge for too many seats, or a
  refund that support promised in a ticket.
- A monthly renewal can be refunded shortly after the renewal if the workspace has not used the product since.
- An annual plan can be refunded or credited shortly after the purchase or the renewal.
- A refund goes back to the original payment method.

Do not go further than this outline. If the person asks whether their own charge qualifies, how many days they
have, or how much they would get, say that Quillstack works that out from the account's records when it decides
the request, and offer to open one.

## Open the request

1. Call `whoami`. If the person's role is `member`, tell them that the request must come from the Owner or a
   Billing Admin of their workspace, and stop.
2. Make sure you know which charge they mean and why they ask. If they said it, do not ask again.
3. Call `open_request` with kind `refund`. Put the person's own words in `message`, and add nothing of your own:
   Quillstack treats the message as the customer's claims and checks each one against the records.
4. Tell the person that the request is open, that a person at Quillstack reviews it, and that they get a notice and
   an email when it is decided. Do not say how it will be decided.

## Report on a request

Call `get_request` or `list_requests`. A request has a status:

- `queued`, `working`, `in_review`, `delayed`: there is no result yet. Say where it stands and nothing more.
- `needs_information`: Quillstack asked a question. Put `question` to the person, and send their answer with
  `answer_request` in their own words.
- `done`: `outcome`, `amount_cents` and `note` are the result, and a person approved them. Tell the person the
  outcome, the amount in dollars, and the note as it is written.

Say nothing about a result that is not in the request. If the person disagrees with a result, they can open a new
request that says what Quillstack got wrong.
