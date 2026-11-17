# TODO

The plan is [DNA-STRAND-MASTER-PLAN.md](DNA-STRAND-MASTER-PLAN.md). This list tracks where the build is against it.

## Now
- [ ] 2026-11-17 M1: genes in the order of Part 8 (G1 → G19 → G4 → G5 → G2 → G3 → G21.4 → G6 → G11 → G10 → G7.0/7.1/7.2/7.8 → G9), each with its codon tests.
- [ ] 2026-11-17 M1: pilot in one lane; the operator samples it before any other lane gets it.

## Waiting on
- [ ] 2026-11-17 Plan 1.5: G7.5 ignores PermissionRequest for AskUserQuestion (C7 finding, docs/CONTRACTS.md); before G7.5 is built (M2).
- [ ] 2026-11-17 C3 interactive case (does a never-named interactive session get a generated session_title?) and C15 (gh skill publish on CI, with G9).

## Later
- [ ] M2 every lane, updating itself · M3 master list (view only) · M4 answers from the page · M5 public release and other harnesses.

## Done
- [x] 2026-11-17 M1: G6 pitboard command (add, update, answer, ok, no, done, withdraw, reopen, show, lane, export, version; bin/pitboard). list/board come with G11, status G10, hook G7, setup G18.1; outbox, badge and inline sync (G6.6) arrive with G13 and G12.
- [x] 2026-11-17 M1: G21.4 launcher (pin, opt-out, good install, newest good folder, own folder, any install; never a bad version).
- [x] 2026-11-17 M1: G3 lane identity (key form, name from /rename, lanes.json map, --lane / PITBOARD_LANE / session lookup).
- [x] 2026-11-17 M1: G2 store (lane locks, append-only logs, live-only state cache, incremental appends: 2 to 7 ms on a 20 MB log).
- [x] 2026-11-17 M1: Part 7 checks on Claude Code 2.1.326, results in docs/CONTRACTS.md, 17 real hook inputs in tests/fixtures/hooks/.
- [x] 2026-11-17 M1: G5 flags (colour, rank, plain words, sort orders), codon tests; CI runs once per PR (push runs on main only).
- [x] 2026-11-17 M1: G4 time (ET display, ages, deadlines), 34 codon tests (PR #3, merged).
- [x] 2026-11-17 M1: G1 event format and G19 masking, 91 codon tests (PR #2).
- [x] 2026-11-17 M0: the plan, README, LICENSE, NOTICE.
