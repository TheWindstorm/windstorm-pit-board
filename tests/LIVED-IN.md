# Lived-in lines (family rule 2, part 3)

A stock machine holds nothing of a person's. Before a tag, after the stock round, one round runs on the same
stock machine carrying these lines, the settings and environment a real person who runs Claude Code lanes
commonly has. A line is added the day a person's machine shows one this list lacked, with the day.

## Claude Code settings (`~/.claude/settings.json`)

- 2026-11-24: ten top-level keys, mode 600: `hooks` (another plugin's or the person's own Stop hook), `env`,
  `enabledPlugins` (another plugin), `extraKnownMarketplaces` (another catalog), `model`, `statusLine`, `theme`,
  `permissions`, `includeCoAuthoredBy`, `cleanupPeriodDays`.
- 2026-11-24: an own status line of four keys: `type`, `command` (the full path of an executable script with no
  interpreter in front, reading the session's JSON on stdin), `padding` 0, `refreshInterval` 5.

## The session

- 2026-11-24: a session name holding a quote, a backslash and a letter that is not ASCII (Claude Code sends it
  JSON-escaped; tests/fixtures/statusline holds its own bytes, captured from Claude Code 2.1.331).

## The shell's environment

- 2026-11-24: a token exported (`GH_TOKEN`), tool settings exported (`EDITOR`, `GIT_CONFIG_GLOBAL`), `LANG` set,
  `NO_COLOR` set, a value holding a newline and one that is not ASCII.
