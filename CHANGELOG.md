# Changelog

## Plan 1.2 (2026-11-17)
- Part 8, M1 build order: G5 (flags) now comes before G2 (store), because the state cache (G2.6) computes `worst_flag` with G5.

## Plan 1.1 (2026-11-17)
- G19.1: the long-opaque-string rule no longer includes `/`, so long file paths and URLs in asks are not masked. Found while writing G19.

## Plan 1.0 (2026-11-17)
- The DNA Strand Master Plan: 21 genes, from the event format (G1) to self-update (G21), the platform checks, and milestones M0 to M5. No code yet.
