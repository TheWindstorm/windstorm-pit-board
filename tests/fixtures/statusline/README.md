# Status line input, as Claude Code sends it

Captured on 2026-11-24 from Claude Code 2.1.331: a session whose status line command saved its stdin to a file.

- `no-name.json`: the first redraw of a session with no name.
- `name-1.json`: after `/rename Pit "Bo\ard" é·1`; Claude Code sends the name JSON-escaped.
- `name-2.json`: after `/rename Pit "Bo\ard" é·2`, a name that differs from the one before only after the quote and
  the backslash.

Only these were replaced, byte for byte otherwise as captured: the paths (`transcript_path`, `cwd`,
`scratchpad_dir`, `workspace`), now under `/home/person`, and the account's weekly usage number.
