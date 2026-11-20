# Pilot notes

Plan [Part 8](../DNA-STRAND-MASTER-PLAN.md#part-8-milestones-and-acceptance) says each milestone ends with a short note here. [Part 9](../DNA-STRAND-MASTER-PLAN.md#part-9-how-we-know-it-works) lists the measurements, which are written here weekly. Times are Eastern (ET), with UTC where a log is quoted.

## M1, one lane (0.1.0)

**Setup.** One pilot lane on one Linux machine. Pit Board 0.1.0 is a frozen copy of `main` at `f105182`, the merge of #25, with CI 5/5 green. It is installed with local scope in that lane's folder only, from a one-entry pilot marketplace. The user-scope settings file was backed up first, and its only change is that one marketplace entry; it is removed after the operator samples the pilot. The folder's status line runs the operator's own status line, then `pitboard status` under the 1 s cap (G10.5). Installed Tue 2026-11-17 4:56 PM ET; the pilot lane's first session started 4:58 PM ET.

### Acceptance (Part 8, M1)

| # | Item | Result | When | Evidence |
|---|---|---|---|---|
| 1 | Tests pass on Python 3.10 and 3.13; skill format gate green | **Pass** | Tue 2026-11-17 4:46 PM ET | CI on `main` `f105182`: `test (ubuntu-latest, 3.10)`, `(ubuntu-latest, 3.13)`, `(macos-latest, 3.10)`, `(macos-latest, 3.13)` and `skills` all success. |
| 2 | The agent records its asks without being reminded, for 2 days | **Not shown yet** | from Fri 2026-11-20 | No asks were recorded from Tue 4:58 PM ET to Thu 6:53 PM ET. The lane sat idle with no work queued for most of that time (the lane's miss, not a Pit Board fault), and it asked the operator nothing while it worked. The 2 days are counted again from Fri 2026-11-20, and only days with real asks count. |
| 3 | After a `/compact`, the reminder lists the open asks | **Pass** (scratch home) | Thu 2026-11-19 6:56 PM ET | The SessionStart hook with `source: compact`, run through the installed 0.1.0 `hooks.json` command, returned `1 ask waits on the operator: - A1 [YELLOW, 0m] ... Suggested: keep it.` plus the rules lines (55 ms). A live `/compact` in the pilot lane has not happened yet; its log will show `session-start ... source=compact`. |
| 4 | The status segment shows the count, and nothing when none are open | **Pass** | Thu 2026-11-19 6:56 PM ET | Scratch home: empty with 0 open (34-39 ms), `🟡 YELLOW 1 ask · oldest 0m` with 1 open (31-34 ms), empty again after `done` (33 ms). Live pilot lane: empty, 0 open (34 ms). |
| 5 | `pb` prints the board in under 1 s, with no model turn | **Pass** (hook time) | Thu 2026-11-19 6:56 PM ET | The UserPromptSubmit hook for `pb` returned `decision: block` with the board as `reason` and `suppressOriginalPrompt: true`, in 48 ms and 58 ms. `pitboard board` alone takes 34 ms. Not yet timed over remote desktop (Part 9). |
| 6 | `ok A1` records the operator's approval and the agent acts on it | **Waits for the operator** | | Only the operator can type it. A lane typing `ok` for them would void the test (Skills Boss, 2026-11-19). |
| 7 | A second build, listed in `update/good-versions` by hand, runs on the next hook call without a restart | **Pass** (scratch home) | Thu 2026-11-19 6:56 PM ET | A 0.1.1 build was placed beside 0.1.0 (version raised; on import it writes a marker; `hooks.json` unchanged, so no generation change). Until it was listed, hooks and `pitboard version` through the 0.1.0 folder ran 0.1.0 and the marker was absent. After `0.1.1` was written to `update/good-versions`, the next hook call through the same 0.1.0 folder imported 0.1.1 (marker present), and `pitboard version` printed `0.1.1 (installed 0.1.0, hooks gen 1)`, both through the plugin folder and through the stable copy. |
| 8 | The operator samples it and says to keep it | **Waits for the operator** | | Items 6 and 8 are done together, when the operator samples the pilot. |

**How items 3, 4, 5 and 7 were run.** One script made a temporary `PITBOARD_HOME` and a temporary `HOME` holding a copy of the installed 0.1.0 folder and an `installed_plugins.json` that points at it. It ran each hook exactly as Claude Code does: the command from `hooks/hooks.json` under `sh`, with `CLAUDE_PLUGIN_ROOT` set to the 0.1.0 folder the session started with. The real install and the pilot lane's own Pit Board home were only read (Skills Boss's condition). Afterwards the pilot lane still ran 0.1.0, its board read `nothing waits on you`, and the real plugin cache held only `0.1.0`. The script and its log are kept with the pilot lane.

### Part 9 measurements, week of 2026-11-17

| Measure | Target | This week |
|---|---|---|
| Real asks that were recorded (20 lane endings sampled) | ≥ 90% | No asks raised yet. |
| Needless catcher blocks per lane per day | ≤ 1 | Not in M1 (G8 comes in M2). |
| Open asks older than 3 days, across all lanes | trending to 0 | 0 |
| Median time from ask to answer | falling week on week | No asks yet. |
| Time from `pb` typed to the board shown, over remote desktop | < 1 s | Not timed over remote desktop yet. Hook time is 48-58 ms. |
| Status segment time | < 50 ms | 31-39 ms |
| Lost events (lane logs vs hub) | 0 | Not in M1 (no hub until M3). |
| Machines on the newest release, `update_check_hours` + 1 hour after it ships | 100% | Not in M1 (the updater comes in M2). The launcher's pick was checked by hand (item 7). |
| Releases rolled back somewhere by G21.10 | each gets a fix and a test | None. |
