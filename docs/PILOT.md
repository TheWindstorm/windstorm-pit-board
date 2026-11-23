# Pilot notes

Plan [Part 8](../DNA-STRAND-MASTER-PLAN.md#part-8-milestones-and-acceptance) says each milestone ends with a short note here. [Part 9](../DNA-STRAND-MASTER-PLAN.md#part-9-how-we-know-it-works) lists the measurements, which are written here weekly. Times are Eastern (ET), with UTC where a log is quoted.

## M1, one lane (0.1.0)

**Setup.** One pilot lane on one Linux machine. Pit Board 0.1.0 is a frozen copy of `main` at `f105182`, the merge of #25, with CI 5/5 green. It is installed with local scope in that lane's folder only, from a one-entry pilot marketplace. The user-scope settings file was backed up first, and its only change is that one marketplace entry. The operator kept the pilot (item 8), so the pilot install stays until 0.1.0 is installed from the real marketplace. The folder's status line runs the operator's own status line, then `pitboard status` under the 1 s cap (G10.5). Installed Tue 2026-11-17 4:56 PM ET; the pilot lane's first session started 4:58 PM ET.

### Acceptance (Part 8, M1)

| # | Item | Result | When | Evidence |
|---|---|---|---|---|
| 1 | Tests pass on Python 3.10 and 3.13; skill format gate green | **Pass** | Tue 2026-11-17 4:46 PM ET | CI on `main` `f105182`: `test (ubuntu-latest, 3.10)`, `(ubuntu-latest, 3.13)`, `(macos-latest, 3.10)`, `(macos-latest, 3.13)` and `skills` all success. |
| 2 | The agent records its asks without being reminded, for 2 days | **Moved to M2a** | Sat 2026-11-21 (the 1 day) | Shown on 1 of the 2 days: on Sat 2026-11-21 the one real ask (A2, 11:23 PM ET) was recorded with `pitboard add` before it was asked in chat, with its ID first. It could not be shown for 2 days, because the pilot lane's decisions go to its owner, not to the operator, and a made-up ask would be a false proof. It is now an acceptance item of M2a. Moved by the skill's owner's ruling of 2026-11-22, with this reason (plan 1.11; promise P4 in `PROMISES.json`). |
| 3 | After a `/compact`, the reminder lists the open asks | **Pass** (scratch home) | Thu 2026-11-19 6:56 PM ET | The SessionStart hook with `source: compact`, run through the installed 0.1.0 `hooks.json` command, returned `1 ask waits on the operator: - A1 [YELLOW, 0m] ... Suggested: keep it.` plus the rules lines (55 ms). A live `/compact` in the pilot lane has not happened yet; its log will show `session-start ... source=compact`. |
| 4 | The status segment shows the count, and nothing when none are open | **Pass** | Thu 2026-11-19 6:56 PM ET | Scratch home: empty with 0 open (34-39 ms), `🟡 YELLOW 1 ask · oldest 0m` with 1 open (31-34 ms), empty again after `done` (33 ms). Live pilot lane: empty, 0 open (34 ms). |
| 5 | `pb` prints the board in under 1 s, with no model turn | **Pass** (hook time) | Thu 2026-11-19 6:56 PM ET | The UserPromptSubmit hook for `pb` returned `decision: block` with the board as `reason` and `suppressOriginalPrompt: true`, in 48 ms and 58 ms. `pitboard board` alone takes 34 ms. Not yet timed over remote desktop (Part 9). |
| 6 | `ok A1` records the operator's approval and the agent acts on it | **Pass** | Sat 2026-11-21 11:24 PM ET | The operator typed `ok A1 A2`. The UserPromptSubmit hook recorded both answers (`answered by operator`, via `ok`: A1 "keep it", A2 "yes, first line") and told the agent to carry them out. The agent did: A2's status line change was live in the pilot lane at 11:25 PM ET (below), and A1's results are this note. |
| 7 | A second build, listed in `update/good-versions` by hand, runs on the next hook call without a restart | **Pass** (scratch home) | Thu 2026-11-19 6:56 PM ET | A 0.1.1 build was placed beside 0.1.0 (version raised; on import it writes a marker; `hooks.json` unchanged, so no generation change). Until it was listed, hooks and `pitboard version` through the 0.1.0 folder ran 0.1.0 and the marker was absent. After `0.1.1` was written to `update/good-versions`, the next hook call through the same 0.1.0 folder imported 0.1.1 (marker present), and `pitboard version` printed `0.1.1 (installed 0.1.0, hooks gen 1)`, both through the plugin folder and through the stable copy. |
| 8 | The operator samples it and says to keep it | **Pass** | Sat 2026-11-21 11:24 PM ET | A1 answered "keep it". Asked Thu 7:07 PM ET, so it waited 2 days 4 hours. |

**How items 3, 4, 5 and 7 were run.** One script made a temporary `PITBOARD_HOME` and a temporary `HOME` holding a copy of the installed 0.1.0 folder and an `installed_plugins.json` that points at it. It ran each hook exactly as Claude Code does: the command from `hooks/hooks.json` under `sh`, with `CLAUDE_PLUGIN_ROOT` set to the 0.1.0 folder the session started with. The real install and the pilot lane's own Pit Board home were only read (the skill owner's condition). Afterwards the pilot lane still ran 0.1.0, its board read `nothing waits on you`, and the real plugin cache held only `0.1.0`. The script and its log are kept with the pilot lane.

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

## M2a, the skill family's lanes (0.1.1)

Three lanes of the skill family run 0.1.1 from the catalog, put in by `setup --folder` from a clone of the tag; the third since Sun 2026-11-22 9:47 AM ET (14:47Z). From then to Mon 2026-11-23 12:30 AM ET, the shared log shows 11 session starts (one resume, ten after a compaction, each with the reminder of the rules), 280 prompts and 185 turn ends across the three lanes.

The agent's `pitboard` is now the 0.1.1 folder in the plugin cache, the one the catalog installed. Last week's note, that it was the marketplace's source folder instead of the cache, applied to the M1 pilot copy only, which is gone.

### Part 9 measurements, week of 2026-11-23

Started Mon 2026-11-23 12:30 AM ET; updated through the week.

| Measure | Target | This week |
|---|---|---|
| Real asks that were recorded (20 lane endings sampled) | ≥ 90% | **0 of 1.** 20 endings sampled Mon 12:50 AM ET, evenly over each lane's turns since 9:47 AM ET Sunday (7, 7 and 6 of 63, 75 and 52 endings): 19 needed no ask of the operator, and 1 needed one and did not record it: a lane's work waited on the operator's own login step, and the lane said so on the shared board only. No lane ran `pitboard add` in any of its 190 endings. P4's two days count from 0.1.2 now. See "What the sample found" below. |
| Needless catcher blocks per lane per day | ≤ 1 | Not in 0.1.1 (the catcher, G8, is not built yet). |
| Open asks older than 3 days, across all lanes | trending to 0 | 0 (no open ask). |
| Median time from ask to answer | falling week on week | No ask this week yet. |
| Time from `pb` typed to the board shown, over remote desktop | < 1 s | Not timed over remote desktop yet. Hook time through the 0.1.1 folder: median 35 ms (32-50 ms, 15 runs). |
| Status segment time | < 50 ms | Median 29 ms (27-34 ms, 15 runs) through the home's stable copy, as the status line runs it. |
| Lost events (lane logs vs hub) | 0 | Not in M2a (no hub until M3). |
| Machines on the newest release, `update_check_hours` + 1 hour after it ships | 100% | 0.1.1 is the newest release and all three lanes run it. 0.1.2 is not released: every promise due in it is built and proven except P4. |
| Releases rolled back somewhere by G21.10 | each gets a fix and a test | None. |

Both timings were taken on the pilot machine at load 8, against a copy of the lane's Pit Board home, so the runs left nothing in the real one.

### What the sample found, week of 2026-11-23

The sample read only each ending's turn (its prompt's kind, the tools it called, its last text), with the lanes told first and the skill's owner's agreement; nothing from them is quoted here. Each ending got one category:

| Category | Endings |
|---|---|
| No ask of the operator was needed | 19 |
| An ask was made and recorded | 0 |
| An ask was made and not recorded | 1 |
| Cannot tell | 0 |

Where a lane waited on someone, it was almost always a staff lane, a peer lane or a test run, not the operator: those are not asks for Pit Board. The one ask that was the operator's (the operator's own login step) went to the shared board instead. The skill's owner, who is staff, also reported asks for the operator that two lanes brought to him over the same two days instead of recording them: whether something may be posted under the operator's name, and a decision about another user's install on the machine. The sample did not land on those turns, but they are the same kind.

So the pilot's finding is that **an ask routed through a boss, a staff lane or the shared board is not recorded by the lane that had it.** The reminder says to record an ask "before you ask it", and the lanes read that as a question typed in the chat. Promise P13 (due 0.1.2) is to change the reminder and the skill so they name these asks, and nobody is asked to go back and record the old ones. Because the promise P4 measures was not kept under 0.1.1's words, the skills' department head moved P4 to 0.1.2: its two days count from the day all three lanes run 0.1.2, and they hold back 0.1.3. P13's proof is P4's.

### Release 0.1.2: what the stock machine found before the pin moved

The release list for 0.1.2 had one step it had not had before: before the catalog's pin moves, run the README's update lines on a stock machine, a fresh virtual machine with no GitHub key and no sign-in, against a copy of the catalog with only Pit Board's entry moved to the new tag.

That step failed. The catalog's entry was a GitHub source. Claude Code 2.1.330 installed 0.1.1 through it, falling back to HTTPS, but `claude plugin update` fetched over SSH, failed with "Host key verification failed", and left the install on 0.1.1. Claude Code 2.1.280 could not even install it there.

**Had the pin moved as it was**, every install on a machine without a GitHub key would have stayed on 0.1.1, its update line would have failed, and the README's update lines would have been wrong for exactly the people who most need them. The pilot itself would not have shown it: the pilot machine has GitHub keys, and all three lanes updated there without trouble.

The fix was the entry's form, not Pit Board's code. With only the entry changed to a URL source over HTTPS, on the same kind of machine:
- an install of 0.1.1 updated to 0.1.2 by the README's lines, on 2.1.330 and 2.1.280;
- a fresh install worked on both versions;
- uninstall then install worked, which the README now gives as the way back for an install from before.

The catalog's owner then moved the entry in that form. The same lines, run against the real catalog on another fresh machine, gave the same results, with every file equal to the tag's. On the pilot machine, each of the three lanes ran the two lines in its own folder, which is the case with a key, and each moved from 0.1.1 to 0.1.2 (P14).

One more thing the update showed, which nobody would guess: **one lane's update changed what another lane's status line ran, within a second.** Every lane's status line runs through the Pit Board home's launcher copy. That copy took the first installed entry, the behaviour 0.1.2 changes, and the first entry was the lane that had just updated. The status line writes no log line, so only the code showed it. From 0.1.3, every hook line names the version that ran and the launcher step that picked it, and `pitboard version` names what the status line runs (P15).

The hooks of the three running sessions still run 0.1.1 from their own folders until each lane starts a new session. P4's two days count from the first day all three lanes have started a session on 0.1.2, so that the reminder and the skill text are both the new ones.
