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

It needs Python 3.9 or newer (on a Mac, the `python3` that comes with Apple's developer tools is enough: 3.9.6 on macOS 13) and nothing else: no `pip install`. On an older Python it changes nothing and says what it found, in the status line and when you run `pitboard`.

**For every project** (your user settings):

```
claude plugin marketplace add TheWindstorm/windstorm-pit-stop
claude plugin install windstorm-pit-board@thewindstorm
```

Then, in a new Claude Code session, `pitboard setup --minimal` shows what it would change (the status line segment, the launcher copy in your Pit Board home) and `pitboard setup --minimal --apply` does it. (0.1.2's README left out `--minimal`, and setup refuses the line without it.) Setup writes `~/.claude/settings.json` private (mode 600). When the file has another mode, the plan says so first: the backup setup keeps (the file as setup found it, after the install line added the plugin) has the old mode, and uninstall puts the old mode back only when it puts the file back byte for byte.

The status line then runs your own status line command as before, with the same input and environment, and puts Pit Board's segment in front of it. When nothing Pit Board shows can have changed, a redraw starts no Python: it shows what Pit Board kept for that session in its home's `state` folder (one small file per session, mode 600, holding the count and the age it shows, never an ask's words; a file goes after a week or when a new version runs). The first redraw of a session, and the first after an ask or a setting changes, runs Pit Board.

**For one project folder only** (that folder's own settings, never yours), from a clone of the newest release tag:

```
claude plugin marketplace add TheWindstorm/windstorm-pit-stop
git clone --depth 1 --branch v0.1.3 https://github.com/TheWindstorm/windstorm-pit-board
windstorm-pit-board/bin/pitboard setup --folder /path/to/your/project --apply
```

Put your project's folder in place of `/path/to/your/project`; until you do, setup refuses it. `--undo` in place of `--apply` takes it out of that folder again. From 0.1.3, `pitboard uninstall --folder /path/to/your/project --apply` does too.

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

## Settings

None is needed. Each one is an environment variable, read when Pit Board runs:

- `PITBOARD_HOME`: the folder Pit Board keeps its files in (default `~/.pitboard`): a folder for Pit Board alone, never your home folder.
- `PITBOARD_MACHINE`: the machine name asks are recorded with (default: this computer's name).
- `PITBOARD_TZ`: the time zone times are shown in, such as `America/New_York` (default: the computer's own).
- `PITBOARD_SELF_UPDATE`: `0` stops Pit Board updating itself, `1` lets it (default: on).
- `PITBOARD_LANE`: the lane a `pitboard` command writes to. Each Claude Code session sets it for its own commands, so set it yourself only outside a session.

## Uninstall

```
pitboard uninstall
pitboard uninstall --apply
```

The first line shows what it would take off; the second does it, however Pit Board was set up: each folder install, the install for every project, and what setup changed in your settings, which goes back byte for byte when you have not changed it since (or, when you have, loses only Pit Board's entry). Your asks, and the log of what Pit Board did on this computer (`logs/`, and the `.bak-` copies setup kept of your settings files), stay where they are and are counted. Setup's own record (`setup-record.json`) goes last, once every step before it is done, then Pit Board's home when nothing is left in it; uninstall never prints a delete command for you to run. When Pit Board's home holds anything Pit Board did not make, uninstall still takes Pit Board off: inside that home it removes only what carries Pit Board's mark or setup's record, and Pit Board's own folders that hold nothing else; it leaves the rest, names what it left and why, and does not delete your asks there. Setup refuses a home that is your home folder or already holds things that are not Pit Board's. The last thing it prints is a census of what went and what stayed, and why. When Pit Board was installed as a plugin, the census also names what Claude Code's own uninstall, which it runs, changed and kept, as read after it ran: Claude Code's plugin list and `~/.claude.json`, the version folder it keeps in its plugin cache, and the plugin catalog. Pit Board leaves the catalog listed, because removing it with `claude plugin marketplace remove thewindstorm` also uninstalls every other plugin installed from that catalog. Run it again and it says `nothing of Pit Board is here`.

When a session is writing to a lane at that moment, it waits a moment as every command does; if the lane is still busy, it names the lane and changes nothing in that home: run it again. When it cannot read a file it needs, it changes nothing in that place, says which file, and exits 11.

To delete your asks and the log too, at your own terminal (it asks you to type their count; an agent cannot do it for you):

```
pitboard uninstall --apply --delete-asks-and-log
```

**After Claude Code's own `claude plugin uninstall`**, Pit Board's code is gone from the plugin list, but your status line setting and your Pit Board home stay. The status line then shows `Pit Board was removed by Claude Code · run ~/.pitboard/bin/pitboard uninstall`, and that one command takes the rest off; it needs no plugin.

**A home set up before 0.1.3** has no uninstall of its own until a session on 0.1.3 or newer starts in it. If the plugin is already gone, this line puts back your own status line (the command the wrapper recorded), and touches nothing else in the file, its mode included:

```
python3 -c 'import json,os; h=os.environ.get("PITBOARD_HOME") or os.path.expanduser("~/.pitboard"); w=os.path.join(h,"statusline.sh"); p=os.path.expanduser("~/.claude/settings.json"); s=json.load(open(p)); m="# pitboard-original-command: "; c=[json.loads(l[len(m):]) for l in open(w) if l.startswith(m)] if (s.get("statusLine") or {}).get("command")==w else None; c is None or (s["statusLine"].update(command=c[0]) if c and c[0] else s.pop("statusLine")); c is None or json.dump(s,os.fdopen(os.open(p+".tmp",os.O_WRONLY|os.O_CREAT|os.O_EXCL,os.stat(p).st_mode&0o777),"w"),indent=2); c is None or os.replace(p+".tmp",p)'
```

What is left is Pit Board's home: the folder `~/.pitboard`, or the folder `PITBOARD_HOME` names, which may hold other things of yours. Deleting it is yours to do, after you have looked inside it. From 0.1.3, `pitboard uninstall` removes what Pit Board made there.

**Known in 0.1.3, fixed in 0.1.4.** A status line run that Claude Code cuts at the wrong moment can leave a small `.tmp` file in Pit Board's home; nothing reads it, and uninstall takes it away (0.1.4 clears it by itself). After `pitboard uninstall`, setup run from the version folder Claude Code keeps says `Pit Board was removed by Claude Code`, which is not what happened: to set Pit Board up again, run the install line above first (0.1.4 says so itself). The status line shows nothing when it fails for any reason, exactly as it does when nothing waits (read in its code; seen with Pit Board's lanes folder made unreadable). In that seen case `pitboard board` says there are no lanes, and `pitboard board --lane <lane>` shows the error. A full disk does the same when the status line has to build its list of asks again (seen with Pit Board's state folder made unwritable, the path a full disk takes in its code): the status line shows nothing, `pitboard status --json` says there are no asks, and `pitboard board --lane <lane>` shows the error. Where Claude Code gives the status line a `PATH` with no `python3`, an open ask leaves the status line once the segment Pit Board kept for it runs out (a minute), and nothing is said (seen in a made home with this version's code). So an empty status line is not proof that nothing waits. 0.1.4 says when it could not read or write, or could not start.

## What 0.1.3 does not do yet

Each line is something this version does today, and when that is wrong. The fix is due in the version named.

- With no lane given, a command answers with the keys of every lane on this computer, so an agent's transcript can carry other lanes' names (0.1.4).
- `pitboard add` does not name the lane it wrote to, so an ask filed in the wrong lane by a `PITBOARD_LANE` left set in a shell looks the same as one filed right (0.1.4).
- `pitboard board` and the session reminder do not say which Pit Board home they read when it is not `~/.pitboard`, and `pitboard version` does not say when self-update is off (0.1.4).
- `pitboard version` says "installed X" from Claude Code's plugin list alone: it still says so after the version folder is gone, and says "none" when the list cannot be read (0.1.4).
- A few reads other than the launcher's (the stable copy's refresh, setup's reads of your settings and of its own record, the lane logs) can take a file that cannot be read for one that is not there (read in its code, not seen) (0.1.4).
- `setup --apply` and `uninstall --apply` change things at once; neither waits for a key at your terminal (0.1.4).
- When `pitboard self-update --pin` is the very first Pit Board command on an account, it makes Pit Board's home 755, not 700, and setup afterwards neither names nor changes that mode (seen in a made home under umask 0002) (0.1.4).
- Setup makes your settings file private (600). Its plan says so, and the backup keeps the old mode, but uninstall puts the old mode back only when it puts the whole file back byte for byte (0.1.4).
- When your settings file cannot be written, setup stops after it has already made Pit Board's home and its copies, with a bare system error; when it cannot be read, setup stops before writing anything, also with a bare system error. Neither names the next step (0.1.4).
- `setup --folder` counts the Claude Code sessions in a folder with `ps` (and `lsof` on a Mac); when either cannot answer, it counts none, so its refusal of a folder with more than one session can miss (read in its code, not seen) (0.1.4).
- Uninstall on an account where Claude Code is already gone stops after putting your status line back, keeps Pit Board's files, and names what to do; it cannot take Pit Board's files off by itself in that case (0.1.4).
- When uninstall keeps your asks, its census does not say that setting Pit Board up again takes them up again, in the same lanes (0.1.4).
- Setup's "Done: N change(s)." counts the steps it applied; it does not check afterwards that Pit Board's commands run (0.1.4).
- With no asks, uninstall's census says "kept: 0 asks" when what it keeps is the lane map and the log (0.1.4).
- A session that starts and ends without an ask leaves a row in `lanes.json` and a few small state files behind, which nothing removes (0.1.4).
- `logs/pitboard.log` is not rotated: every hook in every session adds a line (seen: about 21 KB in an hour and a half on a busy shared machine) (0.1.4).
- In a session where Pit Board was installed after it started (`/reload-plugins`), the session reminder was not given (seen once, on Claude Code 2.1.331); asks were still caught (0.1.4).
- When `pitboard add` itself is refused (a harness that blocks the call), the reminder does not tell the agent to ask in the chat without mentioning the tool (0.1.4).
- Pit Board's own programs get the whole environment Claude Code hands a hook or the status line, not one built for them (0.1.4).
- A stop that says "lane busy ... (try again)" does not say what will differ at the next try (0.1.4).
- When a Claude Code plugin command fails, setup and uninstall recognize its error lines in English only; in another language the hint for a failed clone may not show, though the error itself still does (0.1.4).
- tmux names with letters outside ASCII can be kept as `_` in an ask's place when Pit Board runs without a UTF-8 language (0.1.4).
- A log an older copy cut and then added to can hold two asks under one ID: the board, list and reminder show both rows with nothing saying why, while a command by that ID is refused and names both (0.1.4).
- Stop lines name the next step, but the words for you are not yet one numbered block an agent passes on whole (0.1.4).

## Built for

Claude Code first (hooks, status line, skills). Any agent that can run a shell command or use MCP can use it too.

## Read the plan

[DNA-STRAND-MASTER-PLAN.md](DNA-STRAND-MASTER-PLAN.md): the full blueprint, from the event format to the milestones, written so that any builder can follow it exactly.

## Sibling

[Windstorm Pit Stop](https://github.com/TheWindstorm/windstorm-pit-stop): a context optimizer for Claude Code.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
