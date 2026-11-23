# Changelog

## 0.1.3 (not yet released)
- **Pit Board checks that Python is 3.9 or newer before it does anything** (P16, plan 1.26, G21.15). On an older Python it creates no file and stops with one line naming the version needed and the version found. The status line shows that line, a hook writes it to stderr and exits 0 so the session goes on, and any other command, `setup` included, exits 10. Python 3.8 ran before, but with no zone data it showed wrong times with no error. 3.9 is the `python3` that comes with Apple's developer tools (3.9.6 on macOS 13), and CI now runs on 3.9 too.
- **Which version ran is read, not worked out** (P15, plan 1.25, G21.4). Every line a hook writes to `logs/pitboard.log` ends with `v=<version> step=<n>`: the version of the code that ran and the launcher step that picked its folder (`step=?` when a launcher from before 0.1.3 picked it). `pitboard version` has a last line naming what the status line runs: the version the home's launcher copy picks now, and its step. Seen when one lane's update changed what the other lanes' status lines ran within a second, with nothing in the log to show it.

## 0.1.2 (2026-11-23)
- **The README says how to install and update Pit Board**, and which Claude Code versions the install line was seen to work on.
- **An ask only the operator can answer is recorded also when it leaves the chat** (P13, plan 1.24, G7.7 and G9.1). The reminder and the skill say so for an ask sent to another agent (a coordinator, a reviewer) or a shared board. The ask's ID and one line travel in the message: answer under the ID, or say "not mine to answer" under it. The skill no longer tells the agent not to record questions to other agents, only those they can answer themselves. The pilot's sample of lane endings found the one real ask of the week on a shared board, not recorded.
- **One version in every place** (P12, a guard; plan 1.23, G21.1): `plugin.json`, `__version__` and this file's top dated heading must name the same version, and the suite fails when one differs. Run in a fresh clone of a release tag, it refuses the tag unless the tag's name equals every version label in it. Seen in a sister skill, whose old manifest label kept `claude plugin update` from ever updating it.
- **CI's log names every test and its outcome** (plans 1.21 and 1.22, G20.6): the test step runs `pytest -v`, one line per test with its outcome and a skip's reason, so a reader can see a given test ran and passed in each job, not only a count. A row's `proven` that leans on CI names the run and the test.
- **A failed `claude plugin` command in `setup --folder` shows Claude Code's error** (P9, plan 1.13), not only its last line: from its first error line, at most 12 lines, without its progress lines, wrapped to 100 columns so nothing is cut. When the clone failed over SSH because GitHub accepted no key from the account, the message says so first, in plain words, with what to do.
- **The status line runs the newest installed version** (P8, plan G21.4 step 6). Before any version has passed a self-check, the stable launcher took the first entry in `installed_plugins.json`, which on a machine with folders on different versions can be the oldest.
- **A session start refreshes the home's launcher copy** (plan 1.16, G21.4 and G7.1 step 5), so the launcher fix above reaches homes set up by 0.1.0 and 0.1.1. Only from an installed, not-bad version newer than the copy (or when the copy is torn), only after the new launcher has answered its version line, with the replaced copy kept as `.prev`, and not with `self_update` false. `setup --apply` now writes `pitboard/copied-from`. A hook that stops before refreshing logs that it left the copy as it was and what it read when it started, since another hook may already have refreshed it (plan 1.19). On a very busy machine a start may leave the launcher as it was; the next start tries again, and `pitboard version` says on a second line when the copy is older than the newest installed version.
- **`pitboard self-update --pin VER` and `--unpin`** (P10, plan 1.15, G21.10) hold a Pit Board home on a version you choose and release it, before the rest of the updater exists. A version with no runnable folder in the plugin cache, or one in `update/bad-versions`, is refused and nothing changes. Both print the `version` line, and the status line and the hooks follow at their next call. `pitboard update` only ever changes an ask: without an ask ID, or with an updater flag, it is refused with a line that names `self-update`.
- **The promise gate counts only tests the test runner really runs** (P11, plan 1.20, G21.14). It used to find a row's test by its name as text, and passed while that test was skipped, shadowed by a second definition of the same name, or inside a string. Now it runs the rows' tests and reads the runner's own report, for every row that names a test at every version. A name defined twice in one file, an unconditional skip and a skip with no reason fail; a skip on a condition of the machine is listed as not run here. It leaves itself out of what it runs, has a time limit, and never stops more than its own child.

## 0.1.1 (2026-11-22)
Install Pit Board in one lane's folder, and take it out again.

- **`pitboard setup --folder DIR`** (G18.1 folder mode, plan 1.12): plan first, then `--apply`, and `--undo`.
  - It never touches the user's own settings, and it refuses the home folder and a folder where more than one session runs. Sessions are counted by their command, so the count is right on macOS too (P6).
  - It records the folder's settings; the undo puts them back byte for byte, or removes only Pit Board's entries when another tool changed the file since (P5).
  - A Pit Board home other than the default is written into the folder's own `env`, so a session brought back by any tool keeps it.
- **Promises:** P1 (the status segment first) is proven on a Linux and a macOS machine; P5 and P6 have their tests.

Every release before this one still reads the same: the lane logs, the cache and the config keys are unchanged (G21.11; `tests/fixtures/releases/0.1.1`).

## Plan 1.27 (2026-11-23)
- G21.15: the Mac's 3.9 is named for what it is, the `python3` that comes with Apple's developer tools (3.9.6 on macOS 13), not "what a Mac with no Python added has": `/usr/bin/python3` is Apple's shim to it. Seen on the Mac test run, where the interpreter asked from inside was Xcode's.
- Part 11 question 9: a Mac without Apple's developer tools. What its first `python3` call shows has not been seen, so the plan no longer describes a dialog.
No codon is renumbered and no existing test changes.

## Plan 1.26 (2026-11-23)
- G21.15 (new, P16): the Python floor is 3.9, and it is checked as `launch.py`'s first act (and again first in `cli.main()`, for a launcher copy from before 0.1.3). Below the floor, nothing is made: a hook writes one stderr line and exits 0; the status line shows one short true line naming the floor and the version found; any other command, `setup` included, says where Pit Board does run and exits 10. `launch.py` stays readable by 3.6's grammar so the check is reached. 3.9 is the Mac's own `/usr/bin/python3` (3.9.6), and the suite passes there unchanged. 3.8 is refused because it has no `zoneinfo`: it showed wrong times with no error (seen 2026-11-23). A sister skill named a floor without checking it and started a service on 3.8 before it crashed. Before 0.1.3 is tagged, the refusal is seen once on a real 3.8 machine and the Mac run once on its own interpreter.
- Part 0 rule 4 names 3.9 (was 3.10). G6.1: the floor check is the launcher's first act. G6.3: new exit code `10`. G10.4: one exception, the floor line. G20.6: CI adds Python 3.9.
- Part 11: new question 9, a Mac with no developer tools, where the hooks' command line fails before the check.
No codon is renumbered. With the code, one existing test changes: `test_G20_6_python_and_os_matrix_and_triggers` (`tests/test_g20_ci.py`), which holds CI's Python list and now holds 3.9 in it.

## Plan 1.25 (2026-11-23)
- G21.1: the catalog's entry for Pit Board is a URL source over HTTPS (`"source": "url"`), not a `github` source. Claude Code fetches a `github` source over SSH when it updates, so `claude plugin update` failed on a machine with no GitHub key (seen on 2.1.330; 2.1.280 could not even install it there). The URL form installs and updates there on both versions.
- G21.2 (P14): the README's two update lines must move a stock install with no GitHub key and no sign-in to the newest release, and the README names the versions they were seen to work on and the way back for an install from before the change (uninstall, then install again).
- G7 hooks and G6.2 `version` (P15): every line a hook writes to `logs/pitboard.log` ends with the version of the code that ran and the G21.4 step that picked it, and `version` gets a last line naming what the status line runs. Seen 2026-11-23: one lane's `claude plugin update` changed what the other lanes' status lines ran within a second (the launcher copy took the first installed entry, G21.4 step 6), and nothing in the log showed it.

## Plan 1.24 (2026-11-23)
- G7.7 and G9.1 (P13): an ask only the operator can answer is recorded also when it is sent to another agent (a coordinator, a reviewer) or a shared board instead of the chat. The reminder's Rules line says so. The skill's new step 4 puts the ask's ID and one line into that message: answer under the ID, or say "not mine to answer" under it. An answer given under the ID is written with who gave it; otherwise the operator is asked in chat under the same ID. The skill's "Do not record" line now covers only questions to other agents that they can answer themselves. Found by the week's sample of lane endings: the one real ask went to a shared board and was not recorded.

## Plan 1.23 (2026-11-22)
- G21.1: one version in every place. `plugin.json`, `__version__` and `CHANGELOG.md`'s top dated heading name the same version, and a not-yet-released heading above it names a later one; the suite fails when one differs. A release step: before the marketplace pin moves, the suite runs in a fresh clone of the tag and refuses it unless the tag's name equals every version label in it. Seen in a sister skill: an old manifest label kept `claude plugin update` from ever updating it.
- G21.14: a row may carry `kind: guard`, a promise taken from a fault seen in a sister skill, held like any other row.

## Plan 1.22 (2026-11-22)
- G20.6: CI names every test with `pytest -v` (without `-q`), not `-rA`. On CI's own macOS log, `-rA` folded the two skipped cases of one test into `SKIPPED [2] file:line: reason`, with no names; `-v` gives each test its own line with its outcome and a skip's reason.

## Plan 1.21 (2026-11-22)
- G20.6: CI's log names every test and its outcome (`pytest -rA`), so a reader can see that a given test ran and passed in each job; a count cannot show that.
- G21.14: a row's `proven` that leans on CI names the run and the test, as the log shows them.
No codon is renumbered and no existing test changes.

## Plan 1.20 (2026-11-22)
- G21.14: a promise row's test counts only when the test runner collects it and runs it to a pass in this checkout, never because its name is found as text. A skipped test, one the runner cannot collect, and a name defined twice in one file (only the last definition runs) do not count. A planted test showed the old check passing for all three while the real test never ran. The gate runs the rows' tests and reads the runner's own report. Every row that names a test is checked at every version, not only once the version reaches the row's due version. A test skipped on a condition of the machine, with a written reason, is listed as not run here and is not a pass. A skip with no reason fails, and so does an unconditional skip, whatever its reason, because it runs on no machine. The gate leaves itself out of what it runs, has a time limit, and leaves nothing behind when stopped part-way.
No codon is renumbered and no existing test changes.

## Plan 1.19 (2026-11-22)
- G21.4 step 4: when a hook stops before refreshing the stable copy, its log line says what that hook did and what it read (`this hook left the copy as it was (it read 0.1.1 when it started)`), not that the copy was kept at the old version. Ten hooks at once on a loaded machine showed why: four stopped at the 3 s check after six others had already refreshed the copy, and their lines said `kept at before-0.1.2` about a copy that was new.
- G21.4: on a very busy machine every hook of a restore may miss the 3 s check, so that start leaves the launcher as it was and the next start tries again. This is stated, not changed: it fails on the safe side, and the limit is not raised, because a session start must not wait longer for Pit Board. The README says it in one sentence.
- G6.2 `version`: a second line when the home's launcher copy came from a version older than the newest installed one (`launcher copy from 0.1.1; the next session start refreshes it`), so a person can see a copy that has not been refreshed yet. Only when that newest version is not in `update/bad-versions` and no pin holds the home: in either case no session start refreshes the copy from it, so the line would be false. The first line, which the refresh's own check and scripts read, does not change.
No codon is renumbered. With the code, one existing test changes: the stopped hook's expected log line in `tests/test_g21_stablecopy.py`.

## Plan 1.18 (2026-11-22)
- G21.4 step 1: the pin is skipped for `pitboard self-update`, which starts at step 2. Without this, a home pinned to 0.1.1 or older could not be released: every launcher would run the pinned version, which has no `self-update`, and the person would have to delete `update/pin` by hand.
No codon is renumbered and no existing test changes.

## Plan 1.17 (2026-11-22)
- Part 7, C16: where an installed plugin's code runs from, by catalog source. On Claude Code 2.1.330 a `github` or git-URL source runs from its version folder in the cache, but a directory source runs in place from the catalog folder, although `installed_plugins.json` names a cache path. So G21.4's refresh treats a directory-source install like a checkout, and test rounds of cache behavior use a git source. Result in `docs/CONTRACTS.md`.
No codon is renumbered and no existing test changes.

## Plan 1.16 (2026-11-22)
- G21.4, refreshing the stable copy from a session start, and G7.1 step 5: until the updater exists, the session-start hook refreshes a home's stable launcher copy when it came from an older version (a new one-line file, `pitboard/copied-from`, says which) or is torn. It never refreshes from a bad version, never writes an older copy over a newer one, and does not run with `self_update` false. The new launcher must answer its `version` line from a temporary copy before it replaces the old one, the old copy is kept as one backup, and any number of hooks at once leave one whole copy. The README says so in one sentence. Without this, P8's launcher fix would reach only homes set up by 0.1.2 or later, not those set up by 0.1.0 or 0.1.1.
No codon is renumbered and no existing test changes.

## Plan 1.15 (2026-11-22)
- G21.4 step 6 (P8): before any version has passed a self-check, the launcher runs the highest installed version, not the first entry in `installed_plugins.json`, which can be the oldest when folders have different versions.
- G21.10 (P10): `pitboard self-update --pin VER` and `--unpin` come before the rest of the updater, so a person can hold a Pit Board home on a version and release it. A version with no runnable folder, or a bad one, is refused.
- The updater is renamed `pitboard self-update` (G6.2, G21.3, G21.4, G21.10, M1), and `pitboard update` keeps one meaning: it changes an ask. With no ask ID it is refused, with a line that names `self-update`, and it never updates anything. One name, one job: a command that changes the installed version when an agent forgets an ask ID would be a trap. The updater is not built yet, so the rename costs nothing to anyone. P10's promise wording changed with it (`self-update --pin` for `update --pin`); its date does not move.
No codon is renumbered and no existing test changes.

## Plan 1.14 (2026-11-22)
- G18.1 folder mode, step 6: the lines of a failed command's message (the plain words and Claude Code's error) are wrapped to G6.8's 100 columns, never cut with `…`; a continued line starts with two spaces. The plain-words line is longer than 100 columns, so cutting it would lose the words P9 is for.
No codon is renumbered and no existing test changes.

## Plan 1.13 (2026-11-22)
- G18.1 folder mode, step 6 (P9): a failed `claude plugin` command shows Claude Code's error from its first error line, not only its last line (which is often a progress line, or the end of git's sentence). When the clone failed over SSH because GitHub accepted no key from the account, the message says so first, in plain words, with what to do. The wording follows Claude Code's real output for a failed clone, captured on 2.1.280 and 2.1.330 in test accounts with no GitHub key.
No codon is renumbered and no existing test changes.

## Wording (2026-11-22)
- Wording only: the plan, this changelog, `docs/CONTRACTS.md` and `TODO.md` name roles (the skill's owner, a test machine), not lanes or machines. No rule changes and no test changes.

## Plan 1.12 (2026-11-22)
- G18.1 folder mode (new): `pitboard setup --folder DIR`, its `--apply` and its `--undo`, for M2a. It is the tested folder installer of the first night of folder installs, moved into Pit Board, with promises P5 and P6. It never touches the user's own settings. It counts a folder's sessions by their command, not their process name. It writes a Pit Board home other than the default into the folder's own `env`, so a session brought back by any tool keeps it. The undo puts the folder's file back byte for byte, or removes only Pit Board's entries if another tool changed the file since.
- Part 8, M2a: the one install command and the one undo command are `setup --folder`.
No codon is renumbered and no existing test changes.

## 0.1.0 (2026-11-22)
The first release, Milestone 1 (one lane): every ask an agent needs from its operator is kept out of the scroll.

- **Lane logs:** one append-only log per lane, with locks, and a state cache that can be deleted without loss. Secrets are masked before anything is written (G1, G2, G19).
- **The `pitboard` command:** `add`, `update`, `answer`, `ok`, `no`, `done`, `withdraw`, `reopen`, `show`, `lane`, `list`, `board`, `status`, `export`, `version` and `hook` (G6, G10, G11).
- **Hooks:**
  - the start-up reminder lists the open asks after a new session, a resume or a compaction;
  - `pb`, `ok A1` and `no A1` typed at the prompt are handled without a model turn;
  - busy and idle marks (G7, G16.4).
- **Status line segment:** it shows the count of open asks, and nothing when none are open. It is printed first, before the operator's own status line, under a 1 s cap, so a fault never costs the operator that line (G10, G10.5).
- **`pitboard setup --minimal`:** the config, a stable launcher copy and the status line wrapper, with a backup of every file it changes (G18.1).
- **The launcher** runs the newest good installed version on every call (G21.4). This release has hook generation 1 (G21.6) and skips events from newer releases cleanly (INV9). Every later release must read what this one writes; the files are saved in `tests/fixtures/releases/0.1.0` (G21.11).
- **Skills:** `pit-board` and `board`, in the open Agent Skills format (G9).
- **The promise gate:** `PROMISES.json` holds the pilot's lessons, P1 to P4 (G21.14).

Accepted in a one-lane pilot (`docs/PILOT.md`): items 1 and 3 to 8 pass, and item 2 moved to M2a (plan 1.11). Tested on Python 3.10 and 3.13, on Linux and macOS.

## Plan 1.11 (2026-11-22)
Rulings of the skill's owner on 2026-11-22, before 0.1.0:
- **Part 8:** M1's acceptance item 2 (the agent records its asks without being reminded, for 2 days) moves to M2a.
  - It was shown on 1 of the 2 days. It could not be shown on 2, because the pilot lane's decisions go to its owner, not to the operator.
  - M2a is accepted when two calendar days each have at least one real ask recorded unprompted in an M2a lane (promise P4).
- **G21.1:** the marketplace entry pins the release, with `ref` set to the tag and `sha` to the tag's commit, instead of pointing at `main`. A machine that installs it later gets that release. Each release moves the pin in the same hour as its tag.
- **Part 6:** the listing is pinned to the release tag.

No codon is renumbered and no test changes.

## Plan 1.10 (2026-11-22)
Ruling of the skill's owner on M1, 2026-11-22: a lesson from real use is a gate in the skill's own repository, and M2 is rolled out in two stages.
- G21.14 (new): `PROMISES.json` and `tests/test_g21_promises.py`, the same mechanism as the other Windstorm skills. It refuses a version while a promise due in it has no test, refuses the version after until the promise was seen to work on a real machine, and only the person who saw a `person` row can move its date. Declined lessons keep their reason. M1 now lists G21.14, so 0.1.0 is released with it.
- G21.1: a release needs the promise gate green on its commit.
- G16.5: waking types only into a pane that is still this lane's (same tmux session name and same folder). A tmux restart gives pane ids out again from the start, so a saved id can name another lane's pane (seen at a reboot on 2026-11-22). Window names are not compared, because they change.
- Part 6: `PROMISES.json`. The marketplace listing moves from M5 to 0.1.0 (for M2a); announcing it stays at M5.
- Part 8: M2 in two stages. M2a: the skill family's own lanes, from the hour 0.1.0 is tagged, with one install and one tested undo command. M2b: every lane, after 3 days of M2a with no needless block and no broken status line, and the go of those lanes' owners.
No codon is renumbered and no existing test changes.

## Plan 1.9 (2026-11-22)
- G10.5: the status line wrapper prints Pit Board's segment first: before a one-line status line, joined with ` · `, or on its own first line above a status line of several lines. Before, it came last, and in the M1 pilot the operator could not find it at the end of an 11-line status line; the operator approved the change. The 1 s cap and the fail-soft path are unchanged.
No codon is renumbered. `test_G10_5_wrapper_joins_the_operator_line_and_the_segment` gains a several-line case and checks the new order.

## Plan 1.8 (2026-11-20)
The harness matrix, at the skill's owner's request (P3): what degrades gracefully in a harness without hooks, and how the ask still reaches the operator. Plan text only; no code follows until the skill's owner reads it and the operator has sampled M1.
- G17 is now "Other harnesses: the matrix, MCP server and adapters", with an introduction.
- G17.2: `AGENTS.md` gains the lines that stand in for missing hooks: run `pitboard list` at session start and after a summary; pass `--lane` as G17.6 says; a message that is only `pb`, `ok A12` or `no A12` is handled with that `pitboard` command. The same text goes into a harness's own rules file.
- G17.4 (new) the floor: in any harness that can run `pitboard` or the MCP tools, an ask reaches the operator through the ID in chat, `pitboard board --lane KEY`, the page and the tmux badge, with no hook. Neither means `unsupported`.
- G17.5 (new) capabilities H1 to H10 (H6 split into a and b), with Claude Code 2.1.326's answers.
- G17.6 (new) what takes the place of each missing piece, part by part; new state file `state/<key>.reminded` (Part 4) for the hourly open-asks line in harnesses without a post-compaction hook.
- G17.7 (new) one code path: adapters only translate; a harness with Claude Code's hook shapes needs none.
- G17.8 (new) checking a harness the Part 7 way; results in `docs/HARNESSES.md`, inputs in `tests/fixtures/harnesses/<harness>/` (Part 6); rows go stale after 90 days.
- G17.9 (new) the first harness: T3 Code, Claude provider first, then Codex; on a fixed test machine if the machines' owner rules the exception, else on another booked test machine where the lane installs T3 Code itself (a change from the skill's owner, so M3 never waits on one machine).
- G17.10 (new) `tests/test_g17_matrix.py`.
- Part 8: G17.2 and G17.4 to G17.10 (T3 Code's rows) move to M3, because the page is the floor; M3's acceptance gains T3 Code's rows and an ask from a T3 Code lane on the page within 90 s. M5 keeps G17.1, G17.3 and the other harnesses' rows.
- Part 11.8 (new, answered by the skill's owner): one harness matrix for the skill family, growing by division. H1 to H10 live in this plan for now, Pit Stop adds its own from H11 up, and the matrix moves to a shared home when a third skill needs it.
No existing codon is renumbered and no existing test changes.

## Plan 1.7 (2026-11-17)
- G2.12 (new): one writer's events never tie. An event this writer created, stamped at or up to 1 s before the lane's newest event, gets that event's `ts` + 1 ms, so `done` then `reopened` in the same millisecond keep their order (found by a macOS CI run).
- G10.5: the status line wrapper runs Pit Board's part under a 1 s cap (`timeout`, or `gtimeout` on macOS, when either exists); on an error, no output or the cap, the operator's own line prints alone (G10.4). A pilot condition set by the skill's owner.

## Plan 1.6 (2026-11-17)
Clarifications found while building G9 (no behaviour changes elsewhere):
- Appendix A.5 (the skill body, used word for word by G9.1) now holds the G9.2 fallback sentence: use `~/.pitboard/bin/pitboard` when `command -v pitboard` finds nothing. Before, G9.1 and G9.2 could not both hold.
- G9.3: the board skill runs `pitboard board --plain`, or `--all --plain` when its argument is `all`; `pitboard board all` was never a valid command (G6.2).
- G20.6 and G9.5: CI runs on every pull request and every push to `main`, so each job runs once per change (it ran twice when every push and every pull request triggered it).

## Plan 1.5 (2026-11-17)
- G7.5: a PermissionRequest for `AskUserQuestion` writes nothing. On Claude Code 2.1.326 a question box also fires PermissionRequest and a `permission_prompt` Notification (check C7, `docs/CONTRACTS.md`; saved inputs under `tests/fixtures/hooks/`), so without this every question box would be two asks. New test `test_G7_5_question_box_is_one_ask`. C7 now also records which tools fire PermissionRequest. Ruled by the skill's owner on 2026-11-17.

## Plan 1.4 (2026-11-17)
Fixes from the DNA Strand lane's review of plan 1.2:
- G21.12: `self_update: false` uses G21.4 step 2 (the recorded install path), one behaviour.
- G13.2 / G14.4: sync batches are capped at 1 000 000 bytes as well as 200 events; the hub answers 413 to a bigger body.
- M1 build order: Part 7 checks come before G10.
- G2.11 (new): incremental state cache with a 200 ms budget at 20 MB; G2.6 points to it, and the cache now holds only live asks (open or answered) plus `max_ask`, `last_applied` and `stats`, so it stays small; history views fold the log. The fallback full fold runs outside the lock (fold up to size N, then lock and apply only the bytes after N); hook drops on a busy lane are logged and counted by doctor.
- G3.6 removed (`lane adopt`): the key is internal and views show `lane_name`.
- Inline sync respects backoff; `permission-open` is deleted on every closing path; `<ts compact>`, machine-name cleaning, `lanes.json.lock` and `outbox/.backoff` defined; plain output shows ANSWERED vs DONE; marketplace catalog added to open questions; C9 marked removed; DST rule for G4.4; the G21.5 self-check log named.

## Plan 1.3 (2026-11-17)
- The Windstorm skill standard (set by the skill's owner, 2026-11-17): G9.4 format (agentskills.io, quoted description up to 1 024 characters, SKILL.md under 500 lines, references/scripts/assets), G9.5 `gh skill publish --dry-run` gate, G9.6 20-query trigger evals, G9.7 with-skill vs. without-skill evals, G20.8 CI rules (read-only permissions, no repo secrets, no pull_request_target, standard GitHub-hosted runners only), G21.1 release with `gh skill publish --tag`, check C15. Format gate in M1, evals in M2; M1 order unchanged.

## Plan 1.2 (2026-11-17)
- Part 8, M1 build order: G5 (flags) now comes before G2 (store), because the state cache (G2.6) computes `worst_flag` with G5.

## Plan 1.1 (2026-11-17)
- G19.1: the long-opaque-string rule no longer includes `/`, so long file paths and URLs in asks are not masked. Found while writing G19.

## Plan 1.0 (2026-11-17)
- The DNA Strand Master Plan: 21 genes, from the event format (G1) to self-update (G21), the platform checks, and milestones M0 to M5. No code yet.
