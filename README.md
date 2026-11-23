# Windstorm Pit Board

**Everything your agents are waiting on you for, in one place, at a glance. By The Windstorm.**

In racing, the pit board is the sign the crew holds out over the pit wall as the car flashes past at full speed: big, short, readable in one second. You are the driver. Your coding agents are the crew. Pit Board is the sign.

> **Status: blueprint.** This repository holds the complete [DNA Strand Master Plan](DNA-STRAND-MASTER-PLAN.md) for Pit Board. The code is built from it, gene by gene. The first release (one lane) is Milestone 1.

## The problem

When you run many coding agents at once, they often need you: a decision, an approval, a login, a payment, a signature, an account. They ask in the chat. Then heartbeats, messages from other agents and ongoing work push the ask out of sight. Days later, often over a slow remote desktop, you scroll up and up looking for it. Sometimes the agent has compacted its context and forgotten it asked at all. Work stalls quietly, and across many agents the stalls add up.

## What Pit Board does

- **Every ask is written down when it is made,** in a small per-session file outside the chat that compaction and restarts cannot touch.
- **Asks are caught even when the agent forgets** to write them down: question boxes, permission prompts, and questions written in plain text at the end of a turn.
- **Asks come back after compaction:** the agent sees its open asks every time it starts or compacts.
- **No scrolling:** one short segment on the status line (`🔴 3 asks · oldest 2d`), the full list at the bottom of the screen when you type `pb`, and a badge on the terminal tab. Nothing at all when nothing waits.
- **One-line answers:** `ok A12 A13` approves the agent's suggested answers.
- **One master list** for every agent on every machine: a page with Open and History tabs that can float on top of your screen.
- **Always up to date:** it finds new releases by itself, moves every running part onto them, and steps back by itself if a release is bad. Until that updater is built, the first session start of a newer installed version refreshes the launcher copy in your Pit Board home (the one your status line runs) when that copy came from an older version, after checking that the new launcher answers; set `"self_update": false` in `~/.pitboard/config.json` to switch that off. On a very busy machine a start may leave the launcher as it was; the next start tries again, and until then `pitboard version` says on a second line that the copy is older.

Colours: blinking red (urgent), red (blocking you), blue (only you can do it: pay, sign, log in), yellow (can wait), chequered (done).

## Install and update

Pit Board is installed from The Windstorm's plugin catalog, which lives in the Windstorm Pit Stop repository.

It needs Python 3.9 or newer (a Mac's own `python3` is enough) and nothing else: no `pip install`. On an older Python it changes nothing and says what it found, in the status line and when you run `pitboard`.

**For every project** (your user settings):

```
claude plugin marketplace add TheWindstorm/windstorm-pit-stop
claude plugin install windstorm-pit-board@thewindstorm
```

Then, in a new Claude Code session, `pitboard setup` shows what it would change (the status line segment, the launcher copy in your Pit Board home) and `pitboard setup --apply` does it.

**For one project folder only** (that folder's own settings, never yours), from a clone of a release tag (`vX.Y.Z`, the newest on the Releases page):

```
git clone --depth 1 --branch vX.Y.Z https://github.com/TheWindstorm/windstorm-pit-board
windstorm-pit-board/bin/pitboard setup --folder /path/to/your/project --apply
```

`--undo` in place of `--apply` takes it out of that folder again.

**To update:**

```
claude plugin marketplace update thewindstorm
claude plugin update windstorm-pit-board@thewindstorm
```

For a one-folder install, run the second line in that folder with `--scope local`. The next session start uses the new version; `pitboard version` shows which one runs.

**Claude Code versions.** Since 2026-11-23 the catalog's entry for Pit Board is a URL source over HTTPS. With it, the install lines and the update lines above were seen to work on a machine with no GitHub key and no sign-in, on Claude Code 2.1.280 and 2.1.330: a new install on both, and an install made before that day updated from 0.1.1 to 0.1.2 on 2.1.330. They were also seen to update installs on a machine that has GitHub keys (2.1.330).

Before that day the entry was a GitHub source, which Claude Code fetches over SSH when it updates (and, on 2.1.280, when it installs), so on a machine with no GitHub key the update failed. If an install made before 2026-11-23 still fails to update with a host-key message, uninstall it and install it again:

```
claude plugin uninstall windstorm-pit-board@thewindstorm
claude plugin install windstorm-pit-board@thewindstorm
```

## Built for

Claude Code first (hooks, status line, skills). Any agent that can run a shell command or use MCP can use it too.

## Read the plan

[DNA-STRAND-MASTER-PLAN.md](DNA-STRAND-MASTER-PLAN.md): the full blueprint, from the event format to the milestones, written so that any builder can follow it exactly.

## Sibling

[Windstorm Pit Stop](https://github.com/TheWindstorm/windstorm-pit-stop): a context optimizer for Claude Code.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
