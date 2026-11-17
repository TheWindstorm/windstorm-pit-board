# Changelog

## Plan 1.4 (2026-11-17)
Fixes from the DNA Strand lane's review of plan 1.2:
- G21.12: `self_update: false` uses G21.4 step 2 (the recorded install path), one behaviour.
- G13.2 / G14.4: sync batches are capped at 1 000 000 bytes as well as 200 events; the hub answers 413 to a bigger body.
- M1 build order: Part 7 checks come before G10.
- G2.11 (new): incremental state cache with a 200 ms budget at 20 MB; G2.6 points to it.
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
