---
name: cancellation
description: How to cancel the person's Quillstack subscription, which means talking to Quillstack's retention desk. Read this before the first ask_retention_desk call, or when the person says they want to cancel.
---

# Cancelling a subscription

Only the Owner or a Billing Admin of a workspace can cancel its subscription.

A cancellation goes through Quillstack's retention desk. The desk is an agent of Quillstack's. It is not on the
person's side: it may offer a discount to keep the workspace. You are on the person's side.

## Before you start

Ask the person what they want if you do not know it: to cancel whatever is offered, or to stay if the price were
better, and what price that is. Do not accept an offer the person has not agreed to.

## Talk to the desk

Call `ask_retention_desk` with a message in plain words, such as that the person wants to cancel. The first call
takes no `conversation_id`. Each answer returns one; pass it with every further message of the same conversation.

- The desk may make an offer. Tell the person the offer exactly as the desk stated it.
- You may ask the desk whether it can do better. It makes one offer in a turn at most.
- To accept, say so to the desk. To cancel, say that the person wants to cancel and no offer changes that.

## What counts

Only what the desk recorded counts. `recorded_outcome` is empty until the conversation ends, and then it holds
either the accepted offer or the cancellation. Report that to the person, and report nothing as agreed before it is
there. A cancelled subscription stays active until the end of the period that is already paid.
