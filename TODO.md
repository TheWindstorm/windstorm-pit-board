# TODO

The plan is [DNA-STRAND-MASTER-PLAN.md](DNA-STRAND-MASTER-PLAN.md). This list tracks where the build is against it.

## Now
- [ ] 2026-11-22 P4 (M1 item 2, moved to M2a): two calendar days, each with a real ask recorded unprompted in an M2a lane; write the dates and lanes into `proven`. On 2026-11-22, test sessions on a shared Linux machine and on an Intel Mac each recorded an ask unprompted, from a task that needed the operator's choice and never named Pit Board (evidence, not one of the two days).
- [ ] 2026-11-22 P1 `proven`: write it the first time an open ask shows the segment first in a real lane.
- [ ] 2026-11-22 M2a (Part 8): lanes of the skill family run 0.1.1 from the catalog, put in by `setup --folder` from a clone of the tag: the skill's own lane since 13:22Z and a sibling skill's lane since 13:55Z (first hook from the 0.1.1 cache). The third lane follows on the skill's owner's word; P4's two days count from that hour.
- [ ] 2026-11-22 P8 (#44, due 0.1.2): before any self-check, the stable launcher (the status line's) runs the first installed entry, not the newest (G21.4 step 6); seen on an Intel Mac with the 0.1.1 candidate beside 0.1.0. Build and test it before the first release that changes code the stable copy runs.
- [ ] 2026-11-22 P9 (#45, due 0.1.2): a failed `claude plugin install` in setup --folder shows only the last line of Claude Code's error; show it from its first error line. The undo-on-failure itself held 7 times in round 6. Also name the no-GitHub-key case in plain words (the clone fell back to SSH: 'Host key verification failed' / 'Permission denied (publickey)'), with what to do.
- [ ] 2026-11-22 P10 (#46, due 0.1.2): `pitboard update --pin VER` / `--unpin` before the rest of the updater, so a person can step a home back; seen with 0.1.0 folders whose status line ran 0.1.1.

## Waiting on
- [ ] 2026-11-17 Plan 1.5: G7.5 ignores PermissionRequest for AskUserQuestion (C7 finding, docs/CONTRACTS.md); before G7.5 is built (M2).

## Later
- [ ] M2 every lane, updating itself · M3 master list (view only), with the harness matrix (G17.4 to G17.10) · M4 answers from the page · M5 public release and other harnesses.

## Done
- [x] 2026-11-22 Release 0.1.1 (G18.1 folder mode, P7): tag v0.1.1 at dc80189 (#47), the GitHub release, and the marketplace entry pinned to `ref` v0.1.1 and its `sha` (merged in the marketplace's own repository after the skill's owner's install in a clean test account). The code is the candidate cf0391e, which was installed from its commit on an Intel Mac and a Linux laptop and held through clean reboots, a sudden reset and a reinstall in another order; each undo put the folder back byte for byte. A fresh clone of the tag differs from it in PROMISES.json and TODO.md only.
- [x] 2026-11-22 Overnight stress test with the skill family's other two skills on two machines, with real reboots: rows P7 to P10 (#43 to #46), each with its issue the same night; P2, P5, P6 and P7 seen on real machines. P9 also names the no-GitHub-key case (#48).
- [x] 2026-11-22 P5 and P6 (#38) in PROMISES.json; P4 and docs/PILOT.md name roles, not lanes (#39).
- [x] 2026-11-22 Release 0.1.0 (G21.1): tag v0.1.0 at f725e23, the GitHub release, the `agent-skills` topic and the CHANGELOG entry. The marketplace entry pins `ref` v0.1.0 and its `sha` (merged in the marketplace's own repository). tests/fixtures/releases/0.1.0 is final.
- [x] 2026-11-22 M1 accepted for 0.1.0: items 1 and 3 to 8 pass; item 2 moved to M2a as P4 (plan 1.11). The operator kept the pilot on 2026-11-21.
- [x] 2026-11-22 Plan 1.10 and G21.14: PROMISES.json and its gate (#32, #33); plan 1.9 and G10.5, segment first (#28, #29); M1 acceptance 6 and 8 (#30).
- [x] 2026-11-20 CI run steps use `shell: bash` (pipefail), so a piped command cannot hide a failure (a lesson from the skill's owner).
- [x] 2026-11-20 M1 pilot notes in docs/PILOT.md: acceptance 1, 3, 4, 5 and 7 pass; Part 9's first week.
- [x] 2026-11-20 Harness matrix proposed as plan 1.8 (#26: G17.4 to G17.10, M3), approved by the skill's owner; its code waits for the operator's M1 sample.
- [x] 2026-11-17 M1: every gene of Part 8 is on main (f105182, PRs #2 to #25), CI 5/5 green.
- [x] 2026-11-17 Tag ruleset "release tags are immutable" on refs/tags/v* (no delete, update or force-push; creating a tag is allowed), id 27497878 (C15 warning).
- [x] 2026-11-17 M1: G2.12 one writer's events never tie (same-millisecond done then reopen kept in order; found by a macOS CI run); 0.1.0 release folder saved again with it.
- [x] 2026-11-17 M1: G10.5 status line wrapper caps Pit Board's part at 1 s (timeout/gtimeout); a slow or broken segment leaves the operator's own line alone (plan 1.7).
- [x] 2026-11-17 M1: G21.11 compatibility test (replays tests/fixtures/releases/<version>/: old logs fold the same, old cache read, config keys keep their meaning, newer-machine events skipped cleanly); 0.1.0 folder saved.
- [x] 2026-11-17 M1: C3 settled (session_title is only the --name or /rename name), so G3.2 step 1 is on; C15 recorded (gh skill publish --dry-run passes on CI).
- [x] 2026-11-17 M1: G9 skills (pit-board = Appendix A.5 word for word, board), stdlib format test, gh skill publish --dry-run CI job (G9.5), CI rules test (G20.8).
- [x] 2026-11-17 M1: G7 hooks for M1 (hooks.json in the G7.0 shape; session-start reminder and env line; user-prompt-submit pb board, ok/no, mentions, stale prompts; stop idle mark; cwd-changed), G16.4 busy/idle, G21.6 generation 1, plugin.json 0.1.0.
- [x] 2026-11-17 M1: G18.1 setup --minimal (config, stable launcher copy, statusline.sh wrapper joining the operator's own line; plan first, --apply with backups).
- [x] 2026-11-17 M1: G10 status segment (nothing when nothing waits; worst colour, blinks for blinking red; about 45 ms through bin/pitboard at load 28; session_name sets lane_name once a minute). The statusline.sh join (G10.5) comes with setup (G18).
- [x] 2026-11-17 M1: G11 board (open view, history, list; widths counted in terminal columns, colour on the flag only).
- [x] 2026-11-17 M1: G6 pitboard command (add, update, answer, ok, no, done, withdraw, reopen, show, lane, export, version; bin/pitboard). list/board come with G11, status G10, hook G7, setup G18.1; outbox, badge and inline sync (G6.6) arrive with G13 and G12.
- [x] 2026-11-17 M1: G21.4 launcher (pin, opt-out, good install, newest good folder, own folder, any install; never a bad version).
- [x] 2026-11-17 M1: G3 lane identity (key form, name from /rename, lanes.json map, --lane / PITBOARD_LANE / session lookup).
- [x] 2026-11-17 M1: G2 store (lane locks, append-only logs, live-only state cache, incremental appends: 2 to 7 ms on a 20 MB log).
- [x] 2026-11-17 M1: Part 7 checks on Claude Code 2.1.326, results in docs/CONTRACTS.md, 17 real hook inputs in tests/fixtures/hooks/.
- [x] 2026-11-17 M1: G5 flags (colour, rank, plain words, sort orders), codon tests; CI runs once per PR (push runs on main only).
- [x] 2026-11-17 M1: G4 time (ET display, ages, deadlines), 34 codon tests (PR #3, merged).
- [x] 2026-11-17 M1: G1 event format and G19 masking, 91 codon tests (PR #2).
- [x] 2026-11-17 M0: the plan, README, LICENSE, NOTICE.
