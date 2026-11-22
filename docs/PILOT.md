# Pilot notes

Plan [Part 8](../DNA-STRAND-MASTER-PLAN.md#part-8-milestones-and-acceptance) says each milestone ends with a short note here. [Part 9](../DNA-STRAND-MASTER-PLAN.md#part-9-how-we-know-it-works) lists the measurements, which are written here weekly. Times are Eastern (ET), with UTC where a log is quoted.

## M1, one lane (0.1.0)

**Setup.** One pilot lane on one Linux machine. Pit Board 0.1.0 is a frozen copy of `main` at `f105182`, the merge of #25, with CI 5/5 green. It is installed with local scope in that lane's folder only, from a one-entry pilot marketplace. The user-scope settings file was backed up first, and its only change is that one marketplace entry. The operator kept the pilot (item 8), so the pilot install stays until 0.1.0 is installed from the real marketplace. The folder's status line runs the operator's own status line, then `pitboard status` under the 1 s cap (G10.5). Installed Tue 2026-11-17 4:56 PM ET; the pilot lane's first session started 4:58 PM ET.

### Acceptance (Part 8, M1)

| # | Item | Result | When | Evidence |
|---|---|---|---|---|
| 1 | Tests pass on Python 3.10 and 3.13; skill format gate green | **Pass** | Tue 2026-11-17 4:46 PM ET | CI on `main` `f105182`: `test (ubuntu-latest, 3.10)`, `(ubuntu-latest, 3.13)`, `(macos-latest, 3.10)`, `(macos-latest, 3.13)` and `skills` all success. |
| 2 | The agent records its asks without being reminded, for 2 days | **1 day of 2** | from Fri 2026-11-20 | No asks were recorded from Tue 4:58 PM ET to Thu 6:53 PM ET. The lane sat idle with no work queued for most of that time (the lane's miss, not a Pit Board fault), and it asked the operator nothing while it worked. The 2 days are counted again from Fri 2026-11-20, and only days with real asks count. Sat 2026-11-21: one real ask (A2, 11:23 PM ET), recorded with `pitboard add` before it was asked in chat, with its ID first. |
| 3 | After a `/compact`, the reminder lists the open asks | **Pass** (scratch home) | Thu 2026-11-19 6:56 PM ET | The SessionStart hook with `source: compact`, run through the installed 0.1.0 `hooks.json` command, returned `1 ask waits on the operator: - A1 [YELLOW, 0m] ... Suggested: keep it.` plus the rules lines (55 ms). A live `/compact` in the pilot lane has not happened yet; its log will show `session-start ... source=compact`. |
| 4 | The status segment shows the count, and nothing when none are open | **Pass** | Thu 2026-11-19 6:56 PM ET | Scratch home: empty with 0 open (34-39 ms), `🟡 YELLOW 1 ask · oldest 0m` with 1 open (31-34 ms), empty again after `done` (33 ms). Live pilot lane: empty, 0 open (34 ms). |
| 5 | `pb` prints the board in under 1 s, with no model turn | **Pass** (hook time) | Thu 2026-11-19 6:56 PM ET | The UserPromptSubmit hook for `pb` returned `decision: block` with the board as `reason` and `suppressOriginalPrompt: true`, in 48 ms and 58 ms. `pitboard board` alone takes 34 ms. Not yet timed over remote desktop (Part 9). |
| 6 | `ok A1` records the operator's approval and the agent acts on it | **Pass** | Sat 2026-11-21 11:24 PM ET | The operator typed `ok A1 A2`. The UserPromptSubmit hook recorded both answers (`answered by operator`, via `ok`: A1 "keep it", A2 "yes, first line") and told the agent to carry them out. The agent did: A2's status line change was live in the pilot lane at 11:25 PM ET (below), and A1's results are this note. |
| 7 | A second build, listed in `update/good-versions` by hand, runs on the next hook call without a restart | **Pass** (scratch home) | Thu 2026-11-19 6:56 PM ET | A 0.1.1 build was placed beside 0.1.0 (version raised; on import it writes a marker; `hooks.json` unchanged, so no generation change). Until it was listed, hooks and `pitboard version` through the 0.1.0 folder ran 0.1.0 and the marker was absent. After `0.1.1` was written to `update/good-versions`, the next hook call through the same 0.1.0 folder imported 0.1.1 (marker present), and `pitboard version` printed `0.1.1 (installed 0.1.0, hooks gen 1)`, both through the plugin folder and through the stable copy. |
| 8 | The operator samples it and says to keep it | **Pass** | Sat 2026-11-21 11:24 PM ET | A1 answered "keep it". Asked Thu 7:07 PM ET, so it waited 2 days 4 hours. |

**How items 3, 4, 5 and 7 were run.** One script made a temporary `PITBOARD_HOME` and a temporary `HOME` holding a copy of the installed 0.1.0 folder and an `installed_plugins.json` that points at it. It ran each hook exactly as Claude Code does: the command from `hooks/hooks.json` under `sh`, with `CLAUDE_PLUGIN_ROOT` set to the 0.1.0 folder the session started with. The real install and the pilot lane's own Pit Board home were only read (Skills Boss's condition). Afterwards the pilot lane still ran 0.1.0, its board read `nothing waits on you`, and the real plugin cache held only `0.1.0`. The script and its log are kept with the pilot lane.

### What the sample found

- **The status segment was hard to find.** The operator asked where the pilot was running, because they saw no red dot. The segment was there, but at the end of line 11 of an 11-line status line, after the operator's own fields. Ask A2 proposed printing it first, and the operator approved it. Plan 1.9 changes G10.5 so the wrapper prints the segment first: before a one-line status line, joined with ` · `, or on its own first line above a status line of several lines. The coloured dots on terminal tab labels belong to the terminal, not to Pit Board.
- **The `pitboard` on the agent's PATH is the pilot marketplace's source folder** (its `bin/`), not the 0.1.0 cache folder. So a command the agent types runs that copy (launcher step 5, its own folder), while hooks run the cache copy. Both are the same frozen commit here; with a real marketplace they could differ for a moment after an update.
- **A machine reboot lost nothing.** On Sat 2026-11-21 the machine was rebooted (boot 10:36 PM ET; the lane was resumed with the same session at 10:42 PM ET):
  - The lane log was byte-identical before and after.
  - The open ask kept its ID, uid and state, and the board listed the same asks.
  - The SessionStart reminder listed the open ask on resume.
  - The status segment ran in 20-30 ms.
  - Only things outside Pit Board were lost: the session's temporary files, and its own scheduled checks.
  - Pit Board itself needed nothing re-armed. The hooks and the status line wrapper are files that run on each call, so they worked on the first prompt and the first status line after the resume. This is promise P2 in `PROMISES.json`.

### Part 9 measurements, week of 2026-11-17

| Measure | Target | This week |
|---|---|---|
| Real asks that were recorded (20 lane endings sampled) | ≥ 90% | 1 of 1 (A2). A1 was the pilot's own question, written at setup. |
| Needless catcher blocks per lane per day | ≤ 1 | Not in M1 (G8 comes in M2). |
| Open asks older than 3 days, across all lanes | trending to 0 | 0 |
| Median time from ask to answer | falling week on week | Two answers: A2 in 1 minute, A1 in 2 days 4 hours. |
| Time from `pb` typed to the board shown, over remote desktop | < 1 s | Not timed over remote desktop yet. Hook time is 48-58 ms. |
| Status segment time | < 50 ms | 31-39 ms |
| Lost events (lane logs vs hub) | 0 | Not in M1 (no hub until M3). |
| Machines on the newest release, `update_check_hours` + 1 hour after it ships | 100% | Not in M1 (the updater comes in M2). The launcher's pick was checked by hand (item 7). |
| Releases rolled back somewhere by G21.10 | each gets a fix and a test | None. |
