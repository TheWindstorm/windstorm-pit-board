---
name: pit-board
license: Apache-2.0
description: "Keep every ask you need from the operator out of the scroll. Use whenever you need the operator's decision, approval, login, payment, signature or account before you can go on, and whenever someone mentions \"pit board\", \"pb\", asks, action items or \"what's waiting on me\"."
---

# Pit Board

You keep a list of everything you need from the operator (the person you work for), so nothing you ask gets lost in the scroll, a compaction or a restart.

If `command -v pitboard` finds nothing, use `~/.pitboard/bin/pitboard` wherever this skill says `pitboard`.

## When you need the operator

Before you ask the operator anything that you need an answer or an action for (a decision, an approval, a login, a payment, a signature, an account, a purchase, information only they have):

1. Record it: `pitboard add --title "<the question or action, one line>" --suggested "<the answer you recommend and why, short>"`.
   - Something only they can do with their own hands (pay, sign, log in, create an account, buy): add `--kind hand` and one `--step "..."` per step, and no `--suggested`.
   - It truly cannot wait (a deadline today, something breaking): `--severity urgent`. You can carry on without it for now: `--severity can-wait`. Otherwise leave the default (blocking).
   - A real deadline: `--deadline "YYYY-MM-DD HH:MM"` or `--deadline +2d`.
2. Ask in chat, starting with the ID it printed: "A12: Merge #651 now? I suggest merging now because ..."
3. One ask per decision. Do not bundle three questions into one.
4. If the answer is the operator's to give but you send the ask somewhere else instead of the chat (another agent, such as a coordinator or a reviewer, or a shared board), record it first all the same, and put its ID and this line in your message: "A12 is recorded on the Pit Board for the operator. Answer under A12, or say 'not mine to answer' under A12."
   - They answer under the ID: `pitboard answer A12 --by agent --answer "<who>: <their answer>"`.
   - They say it is not theirs to answer: the ask stays open for the operator. Ask the operator in chat, starting with A12.

Do not record: questions to yourself, questions to other agents that they can answer themselves, rhetorical questions, status updates.

## When it is answered or no longer needed

- The operator answers in chat: `pitboard answer A12 --by operator --answer "<their answer, a few words>"`.
- The operator types `ok A12` or `no A12`: it is already recorded; just act on it.
- The work is finished: `pitboard done A12 --note "<what you did, one line>"`.
- It no longer matters: `pitboard withdraw A12 --reason "<why>"`.

## Never

- Never put a password, key or token in an ask. Name it instead ("the Stripe test key").
- Never mark an ask answered for the operator unless they answered it.
- Never run `pitboard uninstall --delete-asks`: the asks are the operator's, and only they delete them, at their own terminal.

## Showing the list

The operator types `pb` for the open asks and `pb all` for the history. You can show them with `pitboard board` and `pitboard board --all`.
