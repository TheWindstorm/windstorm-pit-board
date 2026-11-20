# Changelog

## Plan 1.8 (2026-11-20)
The harness matrix, for Skills Boss's P3 request: what degrades gracefully in a harness without hooks, and how the ask still reaches the operator. Plan text only; no code follows until Skills Boss reads it and the operator has sampled M1.
- G17 is now "Other harnesses: the matrix, MCP server and adapters", with an introduction.
- G17.2: `AGENTS.md` gains the lines that stand in for missing hooks: run `pitboard list` at session start and after a summary; pass `--lane` as G17.6 says; a message that is only `pb`, `ok A12` or `no A12` is handled with that `pitboard` command. The same text goes into a harness's own rules file.
- G17.4 (new) the floor: in any harness that can run `pitboard` or the MCP tools, an ask reaches the operator through the ID in chat, `pitboard board --lane KEY`, the page and the tmux badge, with no hook. Neither means `unsupported`.
- G17.5 (new) capabilities H1 to H10 (H6 split into a and b), with Claude Code 2.1.326's answers.
- G17.6 (new) what takes the place of each missing piece, part by part; new state file `state/<key>.reminded` (Part 4) for the hourly open-asks line in harnesses without a post-compaction hook.
- G17.7 (new) one code path: adapters only translate; a harness with Claude Code's hook shapes needs none.
- G17.8 (new) checking a harness the Part 7 way; results in `docs/HARNESSES.md`, inputs in `tests/fixtures/harnesses/<harness>/` (Part 6); rows go stale after 90 days.
- G17.9 (new) the first harness: T3 Code on OC3, Claude provider first, then Codex.
- G17.10 (new) `tests/test_g17_matrix.py`.
- Part 8: G17.2 and G17.4 to G17.10 (T3 Code's rows) move to M3, because the page is the floor; M3's acceptance gains T3 Code's rows and an ask from a T3 Code lane on the page within 90 s. M5 keeps G17.1, G17.3 and the other harnesses' rows.
- Part 11.8 (new): one harness matrix for the whole skill family?
No existing codon is renumbered and no existing test changes.

## Plan 1.7 (2026-11-17)
- G2.12 (new): one writer's events never tie. An event this writer created, stamped at or up to 1 s before the lane's newest event, gets that event's `ts` + 1 ms, so `done` then `reopened` in the same millisecond keep their order (found by a macOS CI run).
- G10.5: the status line wrapper runs Pit Board's part under a 1 s cap (`timeout`, or `gtimeout` on macOS, when either exists); on an error, no output or the cap, the operator's own line prints alone (G10.4). A pilot condition from Skills Boss.

## Plan 1.6 (2026-11-17)
Clarifications found while building G9 (no behaviour changes elsewhere):
- Appendix A.5 (the skill body, used word for word by G9.1) now holds the G9.2 fallback sentence: use `~/.pitboard/bin/pitboard` when `command -v pitboard` finds nothing. Before, G9.1 and G9.2 could not both hold.
- G9.3: the board skill runs `pitboard board --plain`, or `--all --plain` when its argument is `all`; `pitboard board all` was never a valid command (G6.2).
- G20.6 and G9.5: CI runs on every pull request and every push to `main`, so each job runs once per change (it ran twice when every push and every pull request triggered it).

## Plan 1.5 (2026-11-17)
- G7.5: a PermissionRequest for `AskUserQuestion` writes nothing. On Claude Code 2.1.326 a question box also fires PermissionRequest and a `permission_prompt` Notification (check C7, `docs/CONTRACTS.md`; saved inputs under `tests/fixtures/hooks/`), so without this every question box would be two asks. New test `test_G7_5_question_box_is_one_ask`. C7 now also records which tools fire PermissionRequest. Skills Boss ruling 2026-11-17.

## Plan 1.4 (2026-11-17)
Fixes from the DNA Strand lane's review of plan 1.2:
- G21.12: `self_update: false` uses G21.4 step 2 (the recorded install path), one behaviour.
- G13.2 / G14.4: sync batches are capped at 1 000 000 bytes as well as 200 events; the hub answers 413 to a bigger body.
- M1 build order: Part 7 checks come before G10.
- G2.11 (new): incremental state cache with a 200 ms budget at 20 MB; G2.6 points to it, and the cache now holds only live asks (open or answered) plus `max_ask`, `last_applied` and `stats`, so it stays small; history views fold the log. The fallback full fold runs outside the lock (fold up to size N, then lock and apply only the bytes after N); hook drops on a busy lane are logged and counted by doctor.
- G3.6 removed (`lane adopt`): the key is internal and views show `lane_name`.
- Inline sync respects backoff; `permission-open` is deleted on every closing path; `<ts compact>`, machine-name cleaning, `lanes.json.lock` and `outbox/.backoff` defined; plain output shows ANSWERED vs DONE; marketplace catalog added to open questions; C9 marked removed; DST rule for G4.4; the G21.5 self-check log named.

## Plan 1.3 (2026-11-17)
- The Windstorm skill standard (Skills Boss, 2026-11-17): G9.4 format (agentskills.io, quoted description up to 1 024 characters, SKILL.md under 500 lines, references/scripts/assets), G9.5 `gh skill publish --dry-run` gate, G9.6 20-query trigger evals, G9.7 with-skill vs. without-skill evals, G20.8 CI rules (read-only permissions, no repo secrets, no pull_request_target, standard GitHub-hosted runners only), G21.1 release with `gh skill publish --tag`, check C15. Format gate in M1, evals in M2; M1 order unchanged.

## Plan 1.2 (2026-11-17)
- Part 8, M1 build order: G5 (flags) now comes before G2 (store), because the state cache (G2.6) computes `worst_flag` with G5.

## Plan 1.1 (2026-11-17)
- G19.1: the long-opaque-string rule no longer includes `/`, so long file paths and URLs in asks are not masked. Found while writing G19.

## Plan 1.0 (2026-11-17)
- The DNA Strand Master Plan: 21 genes, from the event format (G1) to self-update (G21), the platform checks, and milestones M0 to M5. No code yet.
