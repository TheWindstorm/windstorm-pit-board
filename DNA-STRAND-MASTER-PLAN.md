# Windstorm Pit Board · DNA Strand Master Plan

**Plan version 1.35 · 2026-11-24 · The Windstorm**

> In racing, the pit board is the sign the crew holds out over the pit wall as the car flashes past at full speed: big, short, readable in one second. You are the driver. Your agents are the crew. Pit Board is the sign.

This document is the complete blueprint for Windstorm Pit Board. Everything that gets built is built from here. If you are an agent (any model, any size) building a part of this, read **Part 0** first and follow it exactly. If you are a person, read **Part 1** and you will know what this is and why.

---

## Contents

- [Part 0. Rules for builders (the ribosome rules)](#part-0-rules-for-builders-the-ribosome-rules)
- [Part 1. The organism on one page](#part-1-the-organism-on-one-page)
- [Part 2. Words used in this plan](#part-2-words-used-in-this-plan)
- [Part 3. Invariants that are never broken](#part-3-invariants-that-are-never-broken)
- [Part 4. Architecture](#part-4-architecture)
- [Part 5. The genes](#part-5-the-genes)
  - [G1 Contract: the event format](#g1-contract-the-event-format)
  - [G2 Store: files, locks, the state cache](#g2-store-files-locks-the-state-cache)
  - [G3 Lane identity](#g3-lane-identity)
  - [G4 Time](#g4-time)
  - [G5 Flags: colour and order](#g5-flags-colour-and-order)
  - [G6 The pitboard command](#g6-the-pitboard-command)
  - [G7 Hooks](#g7-hooks)
  - [G8 The ask catcher](#g8-the-ask-catcher)
  - [G9 Skill and command files](#g9-skill-and-command-files)
  - [G10 Status line segment](#g10-status-line-segment)
  - [G11 Board view](#g11-board-view)
  - [G12 Tab badge](#g12-tab-badge)
  - [G13 Sync: outbox and inbox](#g13-sync-outbox-and-inbox)
  - [G14 Hub](#g14-hub)
  - [G15 Master list page](#g15-master-list-page)
  - [G16 Answers from the page and waking a lane](#g16-answers-from-the-page-and-waking-a-lane)
  - [G17 Other harnesses: the matrix, MCP server and adapters](#g17-other-harnesses-the-matrix-mcp-server-and-adapters)
  - [G18 Setup and doctor](#g18-setup-and-doctor)
  - [G19 Secret masking](#g19-secret-masking)
  - [G20 Tests and CI](#g20-tests-and-ci)
  - [G21 Self-update: always the newest Pit Board](#g21-self-update-always-the-newest-pit-board)
- [Part 6. Repository layout](#part-6-repository-layout)
- [Part 7. Platform contracts to check before coding](#part-7-platform-contracts-to-check-before-coding)
- [Part 8. Milestones and acceptance](#part-8-milestones-and-acceptance)
- [Part 9. How we know it works](#part-9-how-we-know-it-works)
- [Part 10. Decisions already made, and why](#part-10-decisions-already-made-and-why)
- [Part 11. Open questions](#part-11-open-questions)
- [Appendix A. Worked examples](#appendix-a-worked-examples)
- [Appendix B. Changing this plan](#appendix-b-changing-this-plan)

---

## Part 0. Rules for builders (the ribosome rules)

These rules apply to every agent and person who writes code for Pit Board. They are short on purpose. Follow them literally.

1. **The plan wins.** If the code and this plan disagree, the code is wrong. If the plan itself is wrong, change the plan first, in its own commit, using [Appendix B](#appendix-b-changing-this-plan), and only then change the code.
2. **Every requirement has an ID** like `G6.4` (gene 6, codon 4). Every codon gets at least one test. The test's name contains the ID: `test_G6_4_add_prints_the_ask_id`. A codon without a test is not done.
3. **Build genes in the order of [Part 8](#part-8-milestones-and-acceptance).** Do not start a gene before the genes it depends on pass their tests.
4. **Python 3.9 or newer, standard library only.** The floor is checked, not only written ([G21.15](#g21-self-update-always-the-newest-pit-board)). No `pip install` for the product. Tests may use `pytest`. The page uses plain HTML, CSS and JavaScript with no build step and no downloaded libraries.
5. **Never invent a field, a command, a flag or a file path** that is not in this plan. If you need one, change the plan first (rule 1).
6. **Hooks never break the session.** Every hook catches every exception, exits 0 unless this plan says otherwise, and finishes within its time budget. When unsure, do nothing.
7. **Never print, log or send a secret.** Every text field goes through masking ([G19](#g19-secret-masking)) before it is written anywhere. Tests build fake secrets at run time from pieces, never as one literal string in the repo.
8. **Before writing a hook, run the checks in [Part 7](#part-7-platform-contracts-to-check-before-coding)** against the installed Claude Code and record the results in `docs/CONTRACTS.md`. If a check fails, use the fallback written next to it.
9. **One gene per pull request.** The pull request title starts with the gene ID: `G6: the pitboard command`. The description lists the codon IDs it covers.
10. **Do not grow the product.** Pit Board shows what waits on a person. It does not summarise activity, log turns, or show anything when nothing waits. Ideas go to [Part 11](#part-11-open-questions) or `TODO.md`, not into the code.

---

## Part 1. The organism on one page

### The problem

One person runs many coding agents at once (in our case about 100 Claude Code sessions on a dozen machines in four states). The agents regularly need that person: a question, a decision, a login, a card, a signature, an account to create. They ask in the chat. Then heartbeats, messages from other agents and ongoing work push the ask up and out of sight. When the person comes back, maybe days later, often over a slow remote desktop, the ask is buried. Scrolling up through a laggy remote screen to find it takes a long time and sometimes freezes the screen. Worse, the agent may have compacted its context in the meantime and forgotten that it asked. Work stalls without anyone noticing, and across 100 sessions the stalls add up.

### The cure

1. **Every ask is written down when it is made,** in a small file per session ("lane") that lives outside the chat. Compaction, restarts and heartbeats cannot touch it.
2. **The asks are caught even when the agent forgets to write them down:** question boxes and permission prompts are recorded by hooks, and a check at the end of each turn notices a question written in plain text.
3. **The asks come back after compaction:** the agent is shown its open asks every time it starts or compacts.
4. **The asks are visible without scrolling:** one short segment at the bottom of the terminal (`🔴 3 asks · oldest 2d`), a board view printed at the bottom of the screen when the operator types `pb`, and a badge on the terminal tab.
5. **Answering is one line:** `ok A12 A13` approves the agent's suggested answers.
6. **One master list for every lane on every machine:** each machine sends its asks to one hub, which serves a page with two tabs (Open and History) that can float on top of the screen.
7. **It keeps itself up to date:** every installation finds new releases by itself, installs them, and moves its running parts (hooks in running sessions, the sync timer, the hub, the open page) onto the new version without anyone touching a machine. If a new version fails its self-check, it steps back to the last good one.

### What it is not

- Not a log of what agents did. It never summarises activity.
- Not a task tracker for agents' own work. Only things that wait on a **person**.
- Not a cloud service. Everything stays on the operator's own machines.

### The shape

```
 IN EACH LANE                    ON EACH MACHINE                                   ON THE HUB
 agent asks ─► pitboard add ─┐
 hooks catch asks ───────────┴─► lane log (append-only) ─► outbox ─► POST /v1/events ─► SQLite ─► page: Open | History
                                   │                                                                  (any browser)
                                   ├─► state cache ─► status segment · pb board · tab badge   (in the terminal)
                                   └─► open asks shown to the agent at start-up and after every compaction
```

---

## Part 2. Words used in this plan

| Word | Meaning |
|---|---|
| **Operator** | The person the asks are for. One operator per installation. |
| **Lane** | One agent session, identified by its name (see [G3](#g3-lane-identity)). Lanes outlive restarts. |
| **Machine** | One computer. Each has a short name (`config.machine`). |
| **Ask** | One thing that waits on the operator: a question, a decision, a permission, or a hand item. |
| **Hand item** | An ask only the operator can do with their own hands: pay, sign, log in, create an account, buy something. It has steps, not a suggested answer. |
| **Event** | One line in a lane log that records something that happened to an ask. Events are never changed or deleted. |
| **Lane log** | The append-only file of events for one lane on one machine. |
| **State cache** | A file per lane with the current state of every ask, rebuilt from the lane log after each write. |
| **Fold** | Rebuilding the current state of asks by applying events in order. |
| **Hub** | The one machine that collects every machine's events and serves the master list. |
| **Flag** | The colour an ask shows: blinking red, red, yellow, blue, chequered, grey ([G5](#g5-flags-colour-and-order)). |
| **Display time zone** | The time zone in which times are shown to the operator (`config.display_tz`). Times are always stored in UTC. |

---

## Part 3. Invariants that are never broken

Each invariant has a test (named `test_INV<n>_...`).

- **INV1 Append only.** Nothing ever rewrites or deletes a line of a lane log. The only writes are appends.
- **INV2 The log is the truth.** The state cache, the hub database and every view can be rebuilt from the lane logs alone. Deleting the cache or the hub database loses nothing.
- **INV3 Idempotent events.** Every event has a unique `event_id`. Applying the same event twice has the same result as applying it once, everywhere (fold, hub, inbox).
- **INV4 UTC inside, local outside.** Every stored time is UTC in the form `YYYY-MM-DDTHH:MM:SS.mmmZ`. Every time shown to a person is in the display time zone.
- **INV5 Silent when empty.** When a lane has no open asks, the status segment prints nothing and the tab badge is empty.
- **INV6 Hooks fail open.** No hook error, missing file, bad JSON or timeout ever stops, blocks or slows a session beyond its budget.
- **INV7 No secrets leave masking.** No text reaches a file, the screen, the hub or the page without passing [G19](#g19-secret-masking).
- **INV8 Private network only.** The hub never listens on all interfaces unless the operator passes `--allow-all-interfaces`, and every `/v1/*` request except `/v1/health` needs a token. (The page files under `/` and `/static/` hold no data and need none.)
- **INV9 Unknown is skipped, never fatal.** A reader that meets an event with a higher `v` or an unknown `type` skips it, counts it, and carries on.
- **INV10 The operator's word is final.** An `answered` event by an agent never replaces an answer by the operator. An answer by the operator replaces an answer by an agent. After an operator's answer, an agent can only add `done`, `withdrawn` or `reopened`, and a reopened ask starts a new round in which the old answer stays in history (G1.11).
- **INV11 Updates never lose or strand anything.** Every release reads every lane log any earlier release wrote, accepts events from machines still on older releases, and talks to hubs one release older or newer. A release that fails its self-check on a machine is rolled back on that machine by itself ([G21](#g21-self-update-always-the-newest-pit-board)).

---

## Part 4. Architecture

### Parts and where they run

| Part | Runs on | Lives in | Gene |
|---|---|---|---|
| `pitboard` command | every machine | `pitboard/cli.py` | G6 |
| Hooks | every machine, inside each Claude Code session | `hooks/hooks.json` → `pitboard hook <event>` | G7, G8 |
| Skills (rules, board) | every session | `skills/pit-board/SKILL.md`, `skills/board/SKILL.md` | G9 |
| Status segment | every terminal | `pitboard status` | G10 |
| Tab badge | every tmux pane | `pitboard badge` | G12 |
| Sync | every machine, every 60 s | `pitboard sync` (timer) | G13 |
| Hub | one machine | `pitboard hub serve` | G14 |
| Page | the operator's browser | served by the hub | G15 |
| Launcher and updater | every machine | `bin/pitboard` → newest installed version; `pitboard self-update` (daily timer) | G21 |

### Data flow for one ask

1. The agent decides it needs the operator. It runs `pitboard add --title "..." --suggested "..."`.
2. `pitboard` validates and masks the fields, takes the lane lock, appends an `asked` event to the lane log, rebuilds the state cache, writes a copy of the event to the outbox, sets the tab badge, and prints `A12`.
3. The agent asks the operator in chat as usual, starting with the ID: `A12: merge #651 now?`.
4. The status segment, read every few seconds, now shows `🔴 1 ask · oldest 0m`.
5. Within 60 s, `pitboard sync` posts the outbox to the hub. The hub stores it. The page shows the ask on the next refresh.
6. The operator types `ok A12` in the lane. The UserPromptSubmit hook records an `answered` event (by the operator, with the suggested answer) and tells the agent which answer was approved.
7. The agent does the work, then runs `pitboard done A12`.

### Files on each machine

All under `PITBOARD_HOME` (default `~/.pitboard`):

```
~/.pitboard/
  config.json                 operator settings (G2.10)
  lanes.json                  session_id -> lane key map (G3)
  lanes.json.lock             lock for lanes.json (G3.3)
  lanes/<key>.jsonl           lane logs (G1, G2)
  lanes/<key>.lock            lane locks
  state/<key>.json            state caches
  state/<key>.activity        "busy <ts>" or "idle <ts>" (G16.4)
  state/<key>.wake            time of the last wake typed into this lane (G16.5)
  state/<key>.page-told       uids of page answers already told to the agent (G16.5)
  state/<key>.reminded        session_id -> when a prompt hook last added the open asks (G17.6, harnesses without H5)
  state/permission-open       exists while any permission ask is open (G7.0, G7.5)
  state/statusline-seen.json  session_id -> last time status recorded its name (G10.6)
  statusline.sh               status line wrapper (G10.5)
  outbox/<ts>-<event_id>.json events waiting to go to the hub (G13)
  inbox.cursor                last hub event seen by this machine (G16)
  machine.token               this machine's hub token, mode 600 (G13)
  logs/pitboard.log           diagnostics, rotated at 1 MB, 3 kept (not built: P33, due 0.1.4; until then it grows)
  outbox/rejected/            events the hub refused, kept for doctor (G13.2)
  outbox/.backoff             when the next sync may run (G13.4)
  update/last-check.json      result of the last update check (G21.3)
  update/good-versions        versions that passed the self-check, one per line (G21.4)
  update/bad-versions         versions that failed, one per line (G21.10)
  update/pin                  the version to run, when pinned (G21.10)
  update/minute               this machine's fixed random minute for update checks (G21.3)
  update/last-seen-version    the version the last SessionStart on this machine ran (G21.9)
  update/generation-shown/<session_id>  last hook generation the reload note was shown for (G21.6)
  bin/pitboard                stable launcher copy for timers and the status line (G21.4)
  pitboard/launch.py          the launcher the copy runs (G21.4)
  hub/                        only on the hub machine (G14)
```

---

## Part 5. The genes

Every codon is a requirement. "Must" means must.

### G1 Contract: the event format

The event format is the most important part of this plan. Every other gene can be rewritten in any language later without losing a single ask, as long as this format is kept.

**G1.1 One event per line.** A lane log is UTF-8 text. Each line is one JSON object written with `json.dumps(event, ensure_ascii=False, separators=(",", ":"))`, followed by `\n`. A writer refuses an event whose line would be longer than 16 384 bytes (exit code 6). U+2028, U+2029 and U+0085, which `json.dumps` leaves raw and only inside strings, are written as `\u2028`, `\u2029` and `\u0085` (P75), so a reader that also ends lines at them, an older copy of Pit Board or a person's own line tool, still sees one event per line. A reader ends a line at a line feed only: it splits the bytes at `\n` and decodes each line after, never with Python's `splitlines()`, which also breaks at those three and at VT, FF, FS, GS and RS.

**G1.2 Envelope.** Every event has exactly these top-level fields:

| Field | Type | Rule |
|---|---|---|
| `v` | integer | Format version. This plan defines `1`. |
| `event_id` | string | 32 lowercase hex characters (`uuid4().hex`). Unique everywhere. |
| `type` | string | One of `asked`, `updated`, `answered`, `done`, `withdrawn`, `reopened`. |
| `uid` | string | 32 lowercase hex characters. The ask's global ID, set by its `asked` event and repeated on every later event for that ask. |
| `ask` | string | The ask's short ID in its lane: `A` followed by a positive integer, no leading zeros (`A1`, `A12`). |
| `lane` | string | Lane key ([G3](#g3-lane-identity)). |
| `lane_name` | string | The lane's display name at the time of the event, 1 to 120 characters. |
| `machine` | string | Machine name, `[a-z0-9][a-z0-9-]{0,62}`. |
| `session_id` | string or null | The Claude Code session that wrote it, or null (hub, operator tools). |
| `ts` | string | UTC time of the event, `YYYY-MM-DDTHH:MM:SS.mmmZ`. |
| `origin` | string | `lane` (written on a machine) or `hub` (written by the hub, [G16](#g16-answers-from-the-page-and-waking-a-lane)). |
| `by` | string | `agent`, `operator` or `hook`. |
| `data` | object | Type-specific fields (G1.3 to G1.8). |

**G1.3 `asked` data.**

| Field | Type | Required | Rule |
|---|---|---|---|
| `kind` | string | yes | `question`, `decision`, `permission` or `hand`. |
| `severity` | string | yes | `urgent`, `blocking` or `can-wait`. |
| `title` | string | yes | One line, 1 to 120 characters, no newline. Written as the question or the action ("Merge #651 now?", "Create a Stripe account"). |
| `detail` | string | no | Up to 2 000 characters. |
| `why` | string | no | Up to 500 characters. What it unblocks. |
| `suggested` | string | yes unless `kind` is `hand` or `permission` | Up to 500 characters. The answer the agent recommends. |
| `steps` | array of strings | yes if `kind` is `hand` | 1 to 10 items, each up to 200 characters. What the operator does. |
| `deadline` | string or null | no | UTC time in the G1.2 `ts` form. |
| `source` | string | yes | `agent`, `question-box`, `permission`, `stop-catch`, `operator`. |
| `where` | object | no | `{"cwd": str, "host": str, "tmux_session": str, "tmux_window": str, "tmux_pane": str}`; any key may be missing. `cwd` and `host` up to 500 characters; `host` and every `tmux_*` value must match `^[A-Za-z0-9._%:@-]{1,64}$` or the key is dropped (never refused, never stored). Used to say which terminal to open. |

**G1.4 `updated` data.** Any non-empty subset of `severity`, `title`, `detail`, `why`, `suggested`, `steps`, `deadline`, with the same rules as G1.3. `kind` and `source` never change.

**G1.5 `answered` data.** `{"answer": str (1 to 2 000 chars), "via": "ok" | "no" | "text" | "page" | "question-box" | "permission"}`.

**G1.6 `done` data.** `{"note": str (0 to 500 chars)}`.

**G1.7 `withdrawn` data.** `{"reason": str (1 to 500 chars)}`.

**G1.8 `reopened` data.** `{"reason": str (1 to 500 chars)}`.

**G1.9 Validation.** Order on the way in: mask every text field first ([G19](#g19-secret-masking)), then validate. A writer must refuse an event that breaks any rule in G1.2 to G1.8 (exit code 6, [G6](#g6-the-pitboard-command)). A reader must skip such a line, count it in `pitboard doctor`, and carry on (INV9). Text over a limit: `pitboard add`, `update`, `answer` and the MCP tools refuse it; hooks and the hub (which cannot ask anyone to shorten it) cut it to the limit, ending with `…`.

**G1.10 Ask status.** Each ask has one status: `open`, `answered`, `done` or `withdrawn`.

**G1.11 Fold.** To get the state of every ask in a lane:
1. Read every valid line. Drop events whose `event_id` has already been seen (INV3).
2. Sort the events by `(ts, event_id)`.
3. Apply them in order with this table. A transition not in the table is ignored and counted.

| Current status | `asked` | `updated` | `answered` | `done` | `withdrawn` | `reopened` |
|---|---|---|---|---|---|---|
| (none) | → open | ignore | ignore | ignore | ignore | ignore |
| open | ignore | apply fields | → answered | → done | → withdrawn | ignore |
| answered | ignore | apply fields | replace the answer only if the new one is `by: operator` and the current one is `by: agent`; else ignore (INV10) | → done | → withdrawn | → open |
| done | ignore | ignore | ignore | ignore | ignore | → open |
| withdrawn | ignore | ignore | ignore | ignore | ignore | → open |

The fold also records, per ask: `asked_at` (the `asked` event's `ts`), `answered_at`, `answer`, `answered_by`, `answered_via`, `done_at`, `done_note`, `withdrawn_at`, `withdrawn_reason`, `updated_at` (the last event applied), and `events` (the count applied). `reopened` clears `answered_*`, `answer`, `done_*` and `withdrawn_*` (they stay in the event history).

**G1.12 Short IDs.** A new ask's `ask` is `A` + (1 + the highest number used by any `asked` event in that lane log, or 0 if none). Short IDs are never reused, even after `withdrawn`. They are unique within a lane, not across lanes; across lanes, use `uid`. Two asks under one ID can only be in a log an older copy wrote (before P75 its reader lost an ask holding U+2028, U+2029 or U+0085, and after a rebuild gave its number out again). Both are kept, and which ask an ID means never depends on the cache: every command that takes an ID takes a `uid` in its place; one given an ID that names two asks it could act on writes nothing (exit 4), and its message names each (uid, status, when it was asked, title) and says to give the uid; where only one of them can be acted on, it acts on that one and names it; `show` prints every ask under the ID, its first line saying how many share it. The cache's `doubled` lists such IDs, so a command looks them up in the whole log.

**G1.13 Compatibility.** Readers must ignore unknown fields. A future format adds fields freely; it raises `v` only when an existing field changes meaning, and then this plan gets a migration section.

### G2 Store: files, locks, the state cache

**G2.1 Home.** `PITBOARD_HOME` env var, else `~/.pitboard`. Created with mode 700 on first write.

**G2.2 Lane key in file names.** File names use the lane key unchanged; [G3](#g3-lane-identity) guarantees it is safe in a file name.

**G2.3 Lock.** Every write to a lane holds an exclusive lock on `lanes/<key>.lock` (POSIX `fcntl.flock`; Windows `msvcrt.locking` on byte 0). Lock wait: up to 3 s for commands, 1 s inside hooks, then exit code 7 ("lane busy"; a hook then does nothing, INV6, but writes one `lane-busy <hook name> <lane key>` line to `logs/pitboard.log`, and `pitboard doctor` reports how many asks hooks dropped this way in the last 7 days).

**G2.4 Append.** Inside the lock: open the log with `O_APPEND | O_CREAT`, mode 600, write the whole line with one `os.write`, then `os.fsync`.

**G2.5 Next short ID.** Computed inside the same lock as the append (G1.12), so two writers never get the same ID.

**G2.6 State cache.** After each append, still inside the lock, bring the cache up to date (G2.11) and write `state/<key>.json` atomically (write `state/<key>.json.tmp`, then `os.replace`). Shape:

```json
{"v": 1, "lane": "api-server", "lane_name": "API Server", "machine": "studio-1",
 "built_at": "2026-11-17T19:04:05.123Z", "log_bytes": 40213,
 "open": 3, "oldest_open_at": "2026-11-15T13:00:00.000Z", "worst_flag": "red",
 "asks": [ {"uid": "...", "ask": "A12", "status": "open", "kind": "decision", "severity": "blocking",
            "title": "...", "suggested": "...", "steps": [], "deadline": null, "detail": "", "why": "",
            "asked_at": "...", "answered_at": null, "answer": null, "answered_by": null, "answered_via": null,
            "done_at": null, "done_note": null, "withdrawn_at": null, "withdrawn_reason": null,
            "updated_at": "...", "source": "agent", "where": {}} ]}
```

`asks` holds only **live** asks (status `open` or `answered`), so the cache stays small however long the log grows; views that show closed asks (`board --all`, `list --all`, `show`, `export`) fold the log. The cache also holds `max_ask` (the highest short ID number used, for G1.12), `last_applied` (G2.11), `reader` (the mark of the reader that built it, G2.7), `doubled` (IDs that name two asks, G1.12) and the fold `stats`, and each ask carries the `session_id` of its `asked` event. `worst_flag` is computed at build time with [G5](#g5-flags-colour-and-order) and is a hint only; readers that show flags recompute them at read time (flags change with age).

**G2.7 Stale cache.** A reader that finds `log_bytes` different from the log's size on disk, or a cache whose `reader` is not this reader's mark (P75: a cache an older copy built can lack an ask its reader lost; such a cache is rebuilt once), rebuilds the cache (taking the lock) before using it.

**G2.8 Reads without the lock.** Readers (status, board, list) never take the lock unless they rebuild. A torn last line (no trailing `\n`) is ignored.

**G2.9 Size.** No rotation of lane logs, ever (INV1). An ask with all fields full is about 5 KB; 10 000 asks are about 50 MB. `pitboard doctor` warns when a lane log passes 20 MB.

**G2.10 Config.** `config.json`, every key optional:

| Key | Default | Meaning |
|---|---|---|
| `machine` | the short host name, cleaned: lower-cased, every run of characters other than `a-z`, `0-9`, `-` replaced by `-`, `-` trimmed from both ends, cut to 63; an empty result is `machine` | This machine's name. |
| `operator_name` | `"you"` | How the skill and reminders refer to the operator. |
| `display_tz` | the system's local zone | IANA name, e.g. `America/New_York`. |
| `escalate_after_hours` | `24` | A `can-wait` ask turns red after this many hours open. |
| `urgent_deadline_hours` | `24` | An ask with a deadline closer than this blinks. |
| `stop_catch` | `true` | Turns the ask catcher (G8) on or off. |
| `hub_url` | `null` | e.g. `http://100.64.0.5:8765`. Null means no sync. |
| `wake` | `"off"` | `"off"` or `"tmux"` ([G16](#g16-answers-from-the-page-and-waking-a-lane)). |
| `reminder_max_items` | `20` | Open asks listed in the start-up reminder. |
| `self_update` | `true` | Find and install new releases by itself ([G21](#g21-self-update-always-the-newest-pit-board)). `false` leaves the installed version alone. |
| `update_check_hours` | `6` | How often the updater looks for a new release (minimum 1). |

Environment variables override config: `PITBOARD_MACHINE`, `PITBOARD_TZ`, `PITBOARD_SELF_UPDATE` (`0` or `1`). `PITBOARD_HUB_URL` comes with the hub (G13); until then nothing reads it (P38). Every setting a person may set is listed in the README, and a test holds the code's environment reads to that list (P38).

**G2.11 Incremental cache, with a time budget.** Logs are never rotated (G2.9), so re-folding a whole log on every write would grow without limit inside the lock, and a hook that waits 1 s (G2.3) would drop its ask. So an append updates the cache incrementally when all of these hold: the cache's `log_bytes` equals the log's size before the append; every new event was created in this same call (fresh `event_id`s); each new event's `(ts, event_id)` sorts after the cache's `last_applied` (the `[ts, event_id]` of the last event the cache applied); and each new event is an `asked` event or belongs to an ask the cache holds (a live ask). Then it applies only the new events to the cached asks with the G1.11 table, drops asks that became `done` or `withdrawn`, and takes the next short ID from `max_ask` without reading the log. Otherwise (inbox events, an old timestamp, a reopen of a closed ask, a stale or missing cache) it folds the whole log, but **not inside the lock**: it first reads and folds the log up to its current size N without the lock, then takes the lock, reads only the bytes after N (lines other writers added meanwhile), and applies those. Only if one of those lines sorts before the end of the first fold does it fold the whole log again inside the lock. Budget: an append to a lane whose log is 20 MB finishes in under 200 ms on the CI machines; a test builds such a log and checks it.

**G2.12 One writer's events never tie.** G1.11 sorts by `(ts, event_id)` and `event_id` is random, so two events stamped in the same millisecond (`done`, then `reopened` from a script) could apply in either order. Inside the lock (G2.4), before validation: an event this writer created (`origin: lane`) whose `ts` is at or before the `ts` of the lane's newest applied event (`last_applied`), by at most 1 s, gets that `ts` + 1 ms; each later event of the same append is at least 1 ms after the one before it. A gap over 1 s comes from another machine's clock and is left alone: the one-way status table (G1.11) covers it. Events from the hub (`origin: hub`) keep their `ts`.

### G3 Lane identity

A lane must keep the same key across restarts, compactions and resumes, and two lanes in the same folder must not share a key.

**G3.1 Key form.** Lowercase letters, digits and `-`, 1 to 64 characters, made from the lane's name by: lower-case, replace every run of other characters with `-`, trim `-` from both ends, cut to 64. Empty result → `session-` + the first 8 characters of the session ID.

**G3.2 The lane's name**, in this order of preference:
1. `session_title` from the SessionStart hook input, when present and when C3 confirms it is the `/rename` name.
2. The newest `custom-title` record (`customTitle` field) in the session's transcript file (written by `/rename`; seen on Claude Code 2.1.326, not documented, so check C3).
3. None: the key falls back to `session-<first 8 of session id>`.

`session_name` from the status line input (documented: the `--name` or `/rename` value, or else Claude Code's generated title) only ever sets `lane_name` (G10.6), never the key, because two unrelated sessions can get the same generated title.

**G3.3 The map.** `lanes.json` maps `session_id` → `{"lane": key, "lane_name": name, "first_seen": ts, "last_seen": ts}`. It is written atomically under a lock on `lanes.json.lock`. From 0.1.4 (plan 1.33, P31) a session that records nothing leaves nothing behind: a headless or harness session that starts, never adds an ask and ends leaves no row in the map, no `lanes/<key>.lock` and no `state/<key>.json` or `state/<key>.activity`; the README says what a session writes and when each piece goes (the family's rule 26). Seen 2026-11-24 with the plugin at user scope: eighteen such sessions in an hour and a half, each a nameless `session-<id>` row, an empty lock file and two state files that nothing removed.

**G3.4 First sight wins the key.** The first time a session ID is seen, its key is computed (G3.1 and G3.2) and stored. The key for that session ID never changes after that. Renaming a session updates `lane_name` only, so its log stays in one file.

**G3.5 Same name, new session, same lane.** A new session ID whose name gives an existing key joins that lane (same log, continues the short IDs). This is how a lane survives being started fresh under the same name. Two sessions running at once under the same `/rename` name share one lane on purpose; the lock (G2.3) keeps their short IDs unique.

**G3.6 Removed in plan 1.4:** `lane adopt` is gone. The lane key is internal: every view shows `lane_name`, which follows a rename (G3.4), so a lane first keyed `session-xxxxxxxx` and named later simply keeps that key. Copying or aliasing logs would add a second place an ask could live (review 2026-11-17, item 5).

**G3.7 Finding the lane from the command line**, in this order:
1. `--lane KEY` flag.
2. `PITBOARD_LANE` env var.
3. `CLAUDE_CODE_SESSION_ID` env var (present in commands an agent runs on Claude Code 2.1.326 but not documented; check C2 in [Part 7](#part-7-platform-contracts-to-check-before-coding)), looked up in `lanes.json`.
4. Otherwise exit code 3 with: `pitboard: which lane? Pass --lane KEY. Lanes on this machine: <keys>`.

### G4 Time

**G4.1** Stored times: UTC, `YYYY-MM-DDTHH:MM:SS.mmmZ` (INV4).

**G4.2 Shown times:** in `display_tz`, as `7:04 PM ET` when today, `Tue 7:04 PM ET` within the last or next 6 days, `Nov 3 7:04 PM ET` otherwise. The zone label is the zone's own abbreviation (`strftime("%Z")`), except that `EST`/`EDT` show as `ET`, `CST`/`CDT` as `CT`, `MST`/`MDT` as `MT`, and `PST`/`PDT` as `PT`.

**G4.3 Ages:** `0m` to `59m`, then `1h` to `47h`, then `2d` and up. No seconds.

**G4.4 Deadline input** (`--deadline`) accepts exactly:
- ISO 8601 with an offset or `Z` (`2026-11-20T17:00:00-05:00`).
- `YYYY-MM-DD HH:MM` in the display time zone.
- `YYYY-MM-DD` = 5:00 PM that day in the display time zone.
- Relative: `+Nm`, `+Nh`, `+Nd`.
Anything else: exit code 6, `pitboard: deadline not understood: <text>`. A local time in the hour repeated when clocks go back means its first occurrence; a local time in the hour skipped when clocks go forward is read with the offset in force before the jump (Python `zoneinfo` with `fold=0`).

**G4.5 Time zone data.** Use `zoneinfo`. If the zone cannot be loaded (Windows without tz data), fall back to the system's local time and show its offset (`UTC-5`).

### G5 Flags: colour and order

**G5.1 The flag function.** `flag(ask, now)` returns the first match, top to bottom:

| # | Condition | Flag | Symbol | ANSI |
|---|---|---|---|---|
| 1 | status is `answered` or `done` | `chequered` | 🏁 | none |
| 2 | status is `withdrawn` | `grey` | ⚪ | `\x1b[90m` |
| 3 | severity is `urgent`, or a deadline is set and is less than `urgent_deadline_hours` away or already past | `blinking-red` | 🔴 | `\x1b[5;31m` |
| 4 | kind is `hand` | `blue` | 🔵 | `\x1b[34m` |
| 5 | severity is `blocking` | `red` | 🔴 | `\x1b[31m` |
| 6 | severity is `can-wait` and open for `escalate_after_hours` or more | `red` | 🔴 | `\x1b[31m` |
| 7 | otherwise | `yellow` | 🟡 | `\x1b[33m` |

Reset after each coloured span: `\x1b[0m`.

**G5.2 Rank** (for "worst" and for sorting by severity): `blinking-red` 0, `red` 1, `blue` 2, `yellow` 3, `chequered` 4, `grey` 5. Lower is worse.

**G5.3 No colour.** When the env var `NO_COLOR` is set (any value) or `--plain` is passed, print no ANSI codes and no blinking; print the flag word in capitals instead of the colour (`RED`, `BLINK-RED`, `BLUE`, `YELLOW`, `GREY`; a chequered ask shows its status: `ANSWERED` or `DONE`).

**G5.4 Sort orders**, used by the board, list and page:
- `severity`: rank, then deadline (none last), then `asked_at` oldest first.
- `deadline`: deadline soonest first (none last), then rank, then `asked_at`.
- `age`: `asked_at` oldest first.
- `lane`: machine, then lane name, then short ID number.

### G6 The pitboard command

**G6.1 Running it.** `bin/pitboard` is a POSIX shell file that runs `python3 -I "$(dirname "$0")/../pitboard/launch.py" "$@"` (the same relative path works in the plugin folder and in the stable copy, G21.4), falling back to `python` when `python3` is not a real interpreter (same trick as Windstorm Pit Stop). `launch.py` picks the version to run ([G21.4](#g21-self-update-always-the-newest-pit-board)), puts that version's folder first on `sys.path` and calls its `pitboard.cli.main()`. Its first act is the Python floor check (G21.15). Claude Code puts a plugin's `bin/` folder on the agent's `PATH` while the plugin is enabled, so agents type `pitboard`.

**G6.2 Commands.** Every command accepts `--lane KEY` and `--json`. With `--json`, the only thing printed to stdout is one JSON object with exactly these keys: `{"ok": bool, "exit": int, "message": str, "ids": [short IDs written or affected], "asks": [ask objects in the G2.6 shape], "data": {command-specific, or {}}}`. `data` holds: for `version`, `{"running", "installed", "pinned", "generation"}`; for `sync`, `{"sent", "received", "rejected"}`; for `self-update`, the `last-check.json` object; for `lane`, `{"lane", "lane_name"}`; for `doctor`, `{"checks": [{"name", "ok", "detail", "fix"}]}`. Every flag any gene names is listed in this table; a flag not listed here does not exist.

| Command | Does | Prints (text) |
|---|---|---|
| `add --title T [--kind K] [--severity S] [--suggested S] [--why W] [--detail D] [--step S]... [--deadline D]` | Appends `asked` (`by: agent`, `source: agent`). Defaults: `--kind question`, `--severity blocking`. | `A12 recorded (RED). Ask it in chat as: "A12: <title>"` |
| `update A12 [same field flags]` | Appends `updated`. It only ever changes an ask: with no ask ID it is refused (exit 2) with one line that names `self-update`, and it never updates Pit Board itself. | `A12 updated.` |
| `answer A12 --answer TEXT [--by operator\|agent]` | Appends `answered` (`via: text`). Default `--by agent` (an agent writing down an answer the operator gave in chat). | `A12 answered.` |
| `ok A12 [A13 ...]` / `ok all` | For each: appends `answered` with `answer` = the ask's `suggested`, `via: ok`, `by: operator`. `all` = every open ask in the lane that has a `suggested`. Asks without `suggested` are skipped with a note. | `Approved: A12, A13. Skipped (no suggested answer): A14.` |
| `no A12 [A13 ...]` | Appends `answered` with `answer: "No."`, `via: no`, `by: operator`. | `Declined: A12.` |
| `done A12 [--note N]` | Appends `done`. | `A12 done.` |
| `withdraw A12 --reason R` | Appends `withdrawn`. | `A12 withdrawn.` |
| `reopen A12 --reason R` | Appends `reopened`. | `A12 reopened.` |
| `list [--all] [--sort S]` | Lists asks: open only, or all with `--all`. One line each. | see G11 |
| `board [--all] [--limit N] [--width N] [--plain]` | The board view (G11). | see G11 |
| `show A12` | Every field and every event of one ask, oldest first. | |
| `status [--plain]` | The status segment (G10). | |
| `badge` | Updates the tab badge (G12). | nothing |
| `lane` | Shows this session's lane key and name. | `api-server (API Server)` |
| `sync [--backfill]` | G13. One pass, then exits (the timer repeats it). | `sent 4, received 1, rejected 0` |
| `inbox` | Lists hub answers for this lane that the agent has not acted on yet (G16). | |
| `hook EVENT` | Hook entry point (G7). Reads hook JSON on stdin. | per G7 |
| `hub serve [--bind ADDR] [--port N] [--allow-all-interfaces]` · `hub add-machine NAME` · `hub add-viewer NAME` · `hub status [--refold]` | G14; `--refold` rebuilds the `asks` table from `events` (G21.7). | |
| `setup [--apply] [--tmux] [--hub] [--minimal]` · `setup --folder DIR [--plugin P] [--apply]` | G18. Shows a plan; changes nothing without `--apply`. `--folder` is G18.1 folder mode; `--folder DIR --undo` is the old spelling of `uninstall --folder DIR --apply`, for 0.1.3 only. | |
| `uninstall [--folder DIR] [--apply] [--delete-asks-and-log]` | G18.3 (plan 1.30). Shows a plan; changes nothing without `--apply`. It is for the whole computer, so `--lane` is taken and not needed. `data`: `{"applied", "census": [{"state", "what", "why"}]}`. | the census |
| `doctor [--quick]` | G18.2; `--quick` is the self-check (G21.5). | |
| `export [--format jsonl\|csv] [--all-lanes]` | Writes every event (jsonl) or every ask's folded state (csv) to stdout. | |
| `mcp` | G17. | |
| `self-update [--check] [--now] [--pin VER] [--unpin]` | Pit Board's own updater (G21.3, G21.10). `--pin` and `--unpin` come first (P10). | |
| `version` | The running version, the newest installed version, the pinned version if any (`self-update --pin`), and the hook generation. When the home's launcher copy came from a version older than the newest installed one that is not in `update/bad-versions` (G21.4), and no pin holds the home, a second line says so (with `self_update` false: `launcher copy from 0.2.0; self_update is off, so no start refreshes it`); the first line never changes. A last line names what the status line runs: the version the home's launcher copy picks now and the G21.4 step that picked it, since the status line writes no log line (plan 1.25, P15). | `0.2.1 (installed 0.2.1, hooks gen 1)`, then perhaps `launcher copy from 0.2.0; the next session start refreshes it`, then `status line runs 0.2.1 (step 3)` |
| `update [--check] [--now] [--pin VER] [--unpin]` | G21. | `up to date (0.2.1)` / `updated 0.2.0 → 0.2.1` |

**G6.3 Exit codes.** `0` ok · `1` unexpected error · `2` bad usage · `3` lane unknown · `4` ask not found · `5` transition not allowed (G1.11), with the current status in the message · `6` invalid field · `7` lane busy (lock timeout) · `8` hub unreachable (sync only) · `9` update failed (update only; the running version is unchanged) · `10` Python older than the floor (G21.15; nothing was written) · `11` uninstall incomplete: a read or a removal failed, and the census names it (G18.3).

**G6.4** `add` prints the new short ID first on its line, so `pitboard add ... | cut -d' ' -f1` gives `A12`.

**G6.5** `add` refuses `--kind hand` without at least one `--step`, and refuses `--kind question` or `decision` without `--suggested`, with exit code 6 and a one-line reason.

**G6.6** Every write command finishes by: rebuilding the state cache (G2.6), writing the outbox copy if `hub_url` is set (G13.1), and running `badge` (G12) when inside tmux. Failure of the outbox copy or badge never fails the command. Commands run by a person or an agent also try one inline sync (G13.3) unless `outbox/.backoff` says to wait (G13.4); hooks never sync inline.

**G6.7 `add` fills `where`** by itself: `cwd` from the current folder, `host` from the short host name, `tmux_pane` from `TMUX_PANE`, and `tmux_session` / `tmux_window` from `tmux display -p -t $TMUX_PANE '#{session_name}'` and `'#{window_name}'` (1 s limit). Values that fail the G1.3 pattern are dropped. Hooks that write `asked` do the same.

**G6.8** All text output fits in 100 columns unless `--width` is given; longer text is cut with `…`.

### G7 Hooks

All hooks are declared in `hooks/hooks.json`. Each runs `pitboard hook <event>` with the hook JSON on stdin, time limit 5 s (10 s for `session-start`). Every handler is wrapped so that any exception exits 0 with no output (INV6). Each handler appends one line to `logs/pitboard.log` with the event name, lane key and what it did (no ask text), and ends it with `v=<version> step=<n>`: the version of the code that ran and the G21.4 step that picked its folder, so which version ran in which lane is read from the log, never worked out (plan 1.25, P15). The log is the record of what Pit Board did, not state: it stays when a session ends (the family's rule 26), and it is bounded: rotated at 1 MB, 3 old files kept, with no line lost or split when several hooks write at once (plan 1.33, P33, due 0.1.4; until then nothing rotates it). From 0.1.4 the `session-start` line also names the session (`session=<the first 8 characters of its id>`), because two sessions can share one lane key, for example a lane restarted under a new session id; which version runs in which session is then read from the log alone (plan 1.32, P27).

**G7.0 Hook command form.** Every command in `hooks/hooks.json` is exactly this shape (with its own event name), so that a session whose plugin folder has been removed after an update does nothing instead of failing, and so that hooks run the newest installed code (G21.4):

```
R="${CLAUDE_PLUGIN_ROOT}"; [ -f "$R/pitboard/launch.py" ] || exit 0; P=python3; python3 -I -c pass </dev/null >/dev/null 2>&1 || P=python; exec "$P" -I "$R/pitboard/launch.py" hook session-start
```

The `hook` names, the Claude Code events and matchers they serve, and the fixture folder names (`tests/fixtures/hooks/<name>/`) are exactly:

| `hook` name | Claude Code event | Matcher | Codon |
|---|---|---|---|
| `session-start` | SessionStart | (none) | G7.1 |
| `user-prompt-submit` | UserPromptSubmit | (none) | G7.2 |
| `pre-tool-use` | PreToolUse | `AskUserQuestion` | G7.3 |
| `post-tool-use` | PostToolUse | `AskUserQuestion` | G7.4 |
| `post-tool-use` | PostToolUse | `*`, guarded (below) | G7.5 |
| `permission-request` | PermissionRequest | `*` | G7.5 |
| `stop` | Stop | (none) | G7.6 |
| `cwd-changed` | CwdChanged | (none) | G7.8 |
| `user-prompt-expansion` | UserPromptExpansion | (none) | G7.9 |

The guarded `*` entry exists only to close permission asks, and must not start Python on every tool call. Its command begins with `[ -e "${PITBOARD_HOME:-$HOME/.pitboard}/state/permission-open" ] || exit 0;` and then continues as the shape above. G7.5 creates that empty file when it records a permission ask. Every write that closes a permission ask (G7.5, G7.2 step 5, G7.6 step 2) then checks the machine's state caches and deletes the file when no permission ask is open on any lane.

Each handler writes at most one JSON object to stdout. Context for the model goes in `hookSpecificOutput.additionalContext` (with `hookEventName`); a line for the operator goes in top-level `systemMessage`; a block uses `decision` and `reason`. One object may carry several of these.

**G7.1 SessionStart** (all sources: `startup`, `resume`, `clear`, `compact`, `fork`).
1. Resolve the lane (G3), record the session in `lanes.json`.
2. Append `export PITBOARD_LANE=<key>` as one line to the file named by `CLAUDE_ENV_FILE` (documented for SessionStart; each later Bash command runs it first), unless that exact line is already in the file. Never overwrite the file: other plugins write to it too.
3. Return the reminder (G7.7) as `additionalContext`.
4. *(From M2.)* If the version this machine runs differs from `update/last-seen-version`, also return the one-line update note (G21.9) as `systemMessage` (shown to the operator, not to the model), then write the version there. So it shows once per machine per version.
5. *(From 0.1.2.)* Refresh the stable launcher copy when it came from an older version (G21.4, the stable copy).

**G7.2 UserPromptSubmit.** Reads `prompt`.
1. **Board request.** If the whole prompt, trimmed and lower-cased, is `pb`, `pb all`, `/board` or `/board all`: block the prompt (`decision: "block"`, `reason` = the board as text, `hookSpecificOutput.suppressOriginalPrompt: true`). The operator sees the board at once and no model turn runs. (`pb` is the sure trigger. Whether a typed `/board`, which is not a registered command, reaches this hook is check C4.)
2. **Approval.** If the whole prompt matches, case-insensitive, `^\s*(ok|yes|approve|approved)\s+(all|(A\d+)([\s,]+A\d+)*)\s*[.!]?\s*$`: run the `ok` logic (G6.2) for those IDs, then add context: `Pit Board: the operator approved <ID>: "<suggested>"; ... Carry them out now. When each is finished, run: pitboard done <ID>.`
3. **Decline.** Same with `^\s*(no|decline|declined)\s+(A\d+)([\s,]+A\d+)*\s*[.!]?\s*$`: run `no`, then add context: `Pit Board: the operator declined <IDs>. Do not do them. Ask what to do instead only if you are blocked.`
4. **Mentions.** If the prompt contains one or more `A\d+` IDs of open asks in this lane (whole word), add context: `Pit Board: this message answers or mentions <IDs>. If it answers one, run: pitboard answer <ID> --by operator --answer "<the operator's answer in a few words>".`
5. **Close stale prompts.** Any open `permission` or `question-box` asks of this session are closed: `withdrawn` with reason `prompt closed`.
6. Mark the lane busy (G16.4).
7. *(From M4.)* Add the page-answer context line of G16.5 for asks not yet told.

**G7.3 PreToolUse, matcher `AskUserQuestion`.** For each question in `tool_input.questions`: append `asked` with `kind: decision`, `severity: blocking`, `source: question-box`, `title` = the question (cut to 120), `detail` = the options as `label: description` lines, `suggested` = the first option's label, `by: hook`. Record the tool use ID (if given, check C6) in `detail`'s last line as `tool_use_id: <id>` so G7.4 can find it. Never blocks.

**G7.4 PostToolUse** (matcher `*`; this part acts only when `tool_name` is `AskUserQuestion`). Find this session's open `question-box` asks from G7.3 (same tool use ID when available, else all open `question-box` asks of the session) and append `answered` with `via: question-box`, `by: operator`, `answer` = the chosen answers as text (check C6 for the shape).

**G7.5 PermissionRequest** (documented; its input has `tool_name` and `tool_input`, no `tool_use_id`). The handler returns no decision, so the prompt shows as usual. When `tool_name` is `AskUserQuestion` it writes nothing: a question box also fires PermissionRequest (and a `permission_prompt` Notification), and G7.3 already records it (check C7 on Claude Code 2.1.326; the saved inputs `tests/fixtures/hooks/pre-tool-use/AskUserQuestion.json`, `tests/fixtures/hooks/permission-request/AskUserQuestion.json` and `tests/fixtures/hooks/notification/permission_prompt.json` come from one question box). `test_G7_5_question_box_is_one_ask` feeds those three inputs, in that order, to `pitboard hook` and checks the lane holds exactly one ask, with `source: question-box`. Otherwise it appends `asked` with `kind: permission`, `severity: blocking`, `source: permission`, `title` = `Allow <tool name>?` plus the command or file when given (cut to 120), `detail` = `tool_input` as compact JSON (masked, cut to 2 000). `by: hook`. It is closed by whichever comes first:
- a PostToolUse in this session whose `tool_name` and `tool_input` are equal to the ones recorded: `answered`, `via: permission`, `answer: "allowed"`, `by: hook`;
- G7.2 step 5 or G7.6 step 1: `withdrawn`, reason `prompt closed`.

**G7.6 Stop.** In this order:
1. Read the busy mark's time from `state/<key>.activity` (G16.4) before anything else writes to it.
2. Close stale prompts as in G7.2 step 5.
3. Run the ask catcher (G8) with that busy time.
4. Run `badge`.
5. If the catcher said block: return `{"decision": "block", "reason": <the G8.4 text>}` (documented: the agent continues with the reason as its instruction) and do **not** mark the lane idle, because it keeps working.
6. Otherwise mark the lane idle (G16.4). If G21.6 has a reload note due for this session, return it as `systemMessage`; else no output.

**G7.7 The reminder text** (SessionStart). With open asks:

```
Pit Board: you are lane "<lane_name>" (key <key>) on <machine>. <n> ask(s) wait on <operator_name>:
- A12 [RED, 2d] Merge #651 now or wait for review? Suggested: merge now.
- A14 [BLUE, 5h] YOUR HAND: create a Stripe account. Due Thu 5:00 PM ET.
Rules: record every new ask with `pitboard add` before you ask it, and start the question with its ID. Put the ask's words in single quotes, with no backtick and no dollar sign in them. That includes an ask only <operator_name> can answer that you send to another agent (a coordinator, a reviewer) or a shared board instead of the chat.
If <operator_name> has answered one, run `pitboard answer <ID> --by operator --answer '...'`. If it no longer matters, `pitboard withdraw <ID> --reason '...'`. Do not ask again in chat unless it still blocks your next step.
```

When asks of this lane were answered on the master list (`via: page`) and are not `done` yet, add after the open asks, one line each: `Answered on the master list, not done yet: A12 → "<answer>"`.

From 0.1.4 (plan 1.33, P32) the `Rules:` line adds: when `pitboard add` itself is refused or fails (a session's permissions, a harness), ask in the chat as usual and say nothing to <operator_name> about the tool. Seen 2026-11-24 in a harness session whose permissions refused the call: its first message to the person opened with a sentence about the refused call.

Without open or page-answered asks: only the first sentence and the `Rules:` line. At most `reminder_max_items` asks, worst first (G5.4 `severity`); then `(+N more: pitboard list)`. Total under 3 000 characters.

**G7.8 CwdChanged.** Claude Code clears the `CLAUDE_ENV_FILE` lines when the working folder changes. Append the `export PITBOARD_LANE=<key>` line again, exactly as G7.1 step 2. Nothing else.

**G7.9 UserPromptExpansion, for the board skill.** When `command_name` is the plugin's board skill (`windstorm-pit-board:board`, check C8 for the exact name), block it the same way as G7.2 step 1 if the event allows blocking (check C4); otherwise let it expand and the skill (G9.3) shows the board.

### G8 The ask catcher

The catcher notices when an agent ends its turn with a question to the operator that it did not record.

**G8.1 Input.** The last assistant message's text: the Stop input's `last_assistant_message` (documented); when that is missing or empty, the transcript file's last record with `type: assistant`, joining its `text` content blocks.

**G8.2 Cleaning.** Remove fenced code blocks (```` ``` ```` to ```` ``` ````), inline code (`` `...` ``), block quotes (lines starting with `>`), and URLs. Keep the last 1 500 characters.

**G8.3 Trigger.** The catcher says "ask" when either:
- a line of the cleaned text, after trimming, ends with `?`; or
- the cleaned text matches, case-insensitive, any of: `\b(do|would) you (want|like|prefer)\b`, `\bshall i\b`, `\bshould i\b`, `\b(can|could) you\b`, `\bplease (log ?in|sign|create|buy|approve|confirm|pay|add|enable|grant|choose|pick|decide)\b`, `\b(your|the operator's) (go|ok|okay|approval|call|decision|signature|login)\b`, `\bwaiting (on|for) (you|your)\b`, `\bneed(s)? you to\b`, `\blet me know\b`, `\bwhich (one|option) (do|would) you\b`.

**G8.4 Decision.** Block only when all are true:
- `config.stop_catch` is true;
- `stop_hook_active` is false (never block twice in a row);
- the trigger says "ask";
- no `asked` event was written in this lane at or after the busy time read in G7.6 step 1 (if there is no busy mark, use the time of the transcript's last `type: user` record), and the text does not already contain the ID of an open ask.

Block text (shown to the agent, which then continues its turn):

```
Pit Board: your last message seems to ask <operator_name> something, and no ask was recorded this turn.
If it really asks <operator_name> for something, record it now: pitboard add --title "..." --suggested "..." (hand items: --kind hand --step "..."), then end your turn with one line: "Recorded as A<n>."
If it does not, end your turn now without saying anything more.
```

**G8.5 Quality target** (measured in the pilot, [Part 9](#part-9-how-we-know-it-works)): it catches at least 9 of 10 real unrecorded asks and causes at most one needless block per lane per day. The test corpus (`tests/fixtures/catcher/ask/*.txt` and `no_ask/*.txt`, at least 25 each, from real anonymised endings) must pass at 100% before release; new real misses are added to it.

### G9 Skill and command files

**G9.1 `skills/pit-board/SKILL.md`** has frontmatter `name: pit-board` and a quoted description (G9.4) that triggers on: needing the operator's decision, approval, login, payment, signature or account; "pit board", "pb", "asks", "action items", "what's waiting on me". The body is the text in [Appendix A.5](#a5-the-skill-body), word for word. The skill is a fixed file and says "the operator"; the configured `operator_name` is used only in text Pit Board generates (G7.7, G8.4). When an ask leaves the chat (step 4 of the body), the line that travels with its ID tells whoever receives it what to do, with or without Pit Board, so the ask ends with an answer under its ID, with who gave it, or back with the operator in chat, never as a line on a shared board alone (plan 1.24, P13).

**G9.2** `pitboard` is on the agent's `PATH` through the plugin's `bin/` folder (documented; check C14). If `command -v pitboard` finds nothing, the skill says to use `~/.pitboard/bin/pitboard` (the stable launcher copy, G21.4).

**G9.3 `skills/board/SKILL.md`** (invoked as `/windstorm-pit-board:board`, with `all` as its argument for history). It is the fallback when G7.9 cannot block: it runs `pitboard board --plain`, or `pitboard board --all --plain` when its argument (`$ARGUMENTS`) is `all` (the command has no positional `all`, G6.2), and tells Claude to show the output exactly, inside a code block, with no comment before or after. The operator's quick way is still `pb` (G7.2 step 1).

**G9.4 The Windstorm skill standard (format).** Every skill in this repository follows the Agent Skills specification (agentskills.io), the standard for every Windstorm skill:
1. Each skill is `skills/<name>/SKILL.md`, and its frontmatter `name` equals `<name>` exactly (lower-case letters, digits and `-`).
2. The frontmatter is strict YAML. `description` is a quoted string (double quotes, with `"` and `\` escaped) of at most 1 024 characters, so a colon or other YAML character in it can never break parsing.
3. `SKILL.md` is under 500 lines. Longer material goes in the skill's own `references/` (documents the agent reads when needed), `scripts/` (code it runs) and `assets/` (files it uses), each linked from `SKILL.md` by a relative path.
4. No install metadata (`metadata.github-*`) is committed; `allowed-tools`, if used, is a string.

**G9.5 Format gate.** CI runs `gh skill publish --dry-run` (check C15) wherever it runs the tests (G20.6), and a red result fails CI like a failed test. `tests/test_g9_skills.py` also checks G9.4 points 1 to 3 with the standard library alone (a strict parse of the frontmatter block: `name`, quoted `description`, line counts), so the rule holds even where `gh` is missing.

**G9.6 Trigger evals** (the skill-creator method). Each skill has `evals/<name>/triggers.json`: exactly 20 queries, of which 8 to 10 must make the skill fire and the rest are near-misses that must not (for `pit-board`: fire on "I need you to log in to Stripe before I can go on", "what's waiting on me?"; must not fire on "summarise what you did today", "ask the API server lane for its status"). Each query is `{"id": "G9.6-<name>-<nn>", "query": "...", "should_fire": true|false}`; the id carries the codon (the naming rule for eval cases is set by the DNA Strand method). A run records which skill Claude Code loaded for each query; the skill passes when at least 18 of 20 are right.

**G9.7 With-skill vs. without-skill evals.** Each skill has `evals/<name>/tasks/`: at least 5 real tasks from the pilot (anonymised), each run once with the plugin enabled and once without, recording for each run: the asks the agent raised, whether each was recorded (`pitboard export`), whether it came back after a `/compact`, and the turns and tokens used. The skill earns its place only when the with-skill runs record at least 9 of 10 real asks and the without-skill runs are measurably worse on the same tasks. Results go in `docs/EVALS.md` by date and version.

### G10 Status line segment

**G10.1** `pitboard status` reads the status line JSON from stdin when stdin is not a terminal, finds the lane from `session_id` (G3), reads the state cache, and prints one line with no newline at the end.

**G10.2 Output.** No open asks: nothing at all (INV5). Otherwise: `<symbol> <n> ask(s) · oldest <age>`, coloured with the worst flag (G5.1, G5.2), e.g. `🔴 3 asks · oldest 2d`. When any ask is `blinking-red`, the whole segment blinks.

**G10.3 Speed.** It must finish in under 50 ms on a warm disk: it reads only `lanes.json` and one state cache, and never folds a log unless G2.7 forces it.

**G10.4 It never fails loudly.** Any error prints nothing and exits 0. The one exception is a Python older than the floor (G21.15): the segment is one short true line naming the floor and the version found, in place of times that would be wrong.

**G10.5 Joining an existing status line.** A plugin cannot set `statusLine` (the documentation describes only user and project settings, and the plugin manifest has no such key). `pitboard setup` writes `~/.pitboard/statusline.sh`, which saves stdin to a variable, runs the operator's original status line command with that input, then runs `~/.pitboard/bin/pitboard status` (the stable launcher, G21.4) with the same input. When both print something, Pit Board's segment comes first: before a one-line status line, joined with ` · `, or on its own first line above a status line of several lines, so a long status line never pushes it past the right edge. (In the M1 pilot the operator could not find the segment at the end of an 11-line status line.) Pit Board's part runs under a 1 s cap (`timeout`, or `gtimeout` on macOS, when either exists): when it errors, prints nothing or runs past the cap, the operator's own line is printed alone, so a Pit Board fault never costs the operator their status line (G10.4). Setup shows the change and asks before replacing `statusLine.command` in the operator's `settings.json`, and keeps a backup.

**G10.6** `pitboard status` records `session_name` from its input into `lanes.json` (`lane_name` only, G3.2, G3.4), at most once a minute per session, tracked in `state/statusline-seen.json`.

### G11 Board view

**G11.1 Open view** (`pitboard board`), sorted by `severity` (G5.4):

```
PIT BOARD · API Server · 3 open · 7:04 PM ET
A12 🔴 RED     2d  Merge #651 now or wait for review?
                   → merge now (CI green, no shared files)
A14 🔵 BLUE    5h  YOUR HAND: create a Stripe account · due Thu 5:00 PM ET
                   1. Go to stripe.com/register  2. Use the company email  3. Paste the key name here
A15 🟡 YELLOW  3h  Keep the old pricing page?
                   → no, redirect it to /pricing
Answer: ok A12 A15 · no A15 · or just reply · pb all = history
```

**G11.2** Line 1 is the header. Each ask is one title line plus one line for `suggested` (prefixed `→ `) or steps (numbered, joined on one line). The last line is the answer hint. With no open asks: `PIT BOARD · <lane_name> · nothing waits on you · <time>`.

**G11.3 History view** (`pitboard board --all`): every ask in the lane, sorted by `asked_at`, oldest first, so the newest is at the bottom next to the cursor. Default `--limit 50` (the newest 50); `--limit 0` shows all. Closed asks show their flag, status word, when, and the answer: `A9 🏁 DONE  Nov 12  Use staging first? → yes (ok)`.

**G11.4** The view fits `--width`, else the `COLUMNS` env var, else 100. History rows are always one line each (answer on the same line, cut with `…`), so history prints at most `limit + 2` lines (header, rows, hint). The open view shows at most 30 asks (two lines each) and then one line `(+N more: pitboard list)`: at most 2 × 30 + 3 lines.

### G12 Tab badge

**G12.1** When the env var `TMUX_PANE` is set, `pitboard badge` runs `tmux set-option -w -t <pane> @pitboard "<text>"`, where `<text>` is `●<n>` for n open asks (prefixed by `!` when any is `blinking-red`) or empty when none.

**G12.2** It never renames windows. Showing the badge is the operator's choice: `pitboard setup` prints (and with `--apply` and consent, appends to `~/.tmux.conf`) this line:

```
set -g window-status-format '#W#{?@pitboard, #{@pitboard},}'
set -g window-status-current-format '#W#{?@pitboard, #{@pitboard},}'
```

**G12.3** Badge failures (no tmux, old tmux) are silent.

**G12.4** Tools that show tmux window names (Herdr and similar) can read `@pitboard` from tmux. Adapters for specific tools are listed in [Part 11](#part-11-open-questions) until someone confirms how each tool reads it.

### G13 Sync: outbox and inbox

**G13.1 Outbox.** When `hub_url` is set, every event written on this machine is also written to `outbox/<ts compact>-<event_id>.json` (`<ts compact>` is the event's `ts` with `-`, `:` and `.` removed, e.g. `20261117T190405123Z`, so file names sort in time order) (mode 600) right after the append.

**G13.2** `pitboard sync` posts outbox events oldest first, at most 200 per request and at most 1 000 000 bytes of request body per request (an event is at most 16 384 bytes, G1.1, so one always fits), to `POST <hub_url>/v1/events` with header `Authorization: Bearer <machine.token>` (read from the file, never from a command-line argument). On HTTP 200 it deletes the outbox files whose IDs are in the response's `accepted` and `duplicate` lists, and moves those in `rejected` to `outbox/rejected/` with the reason added (`pitboard doctor` reports them), so a refused event never blocks the ones behind it. On any other result it keeps them all and backs off (G13.4).

**G13.3 Timing.** `pitboard sync` (through the stable launcher copy, G21.4) runs every 60 s from a user timer (systemd user timer on Linux, launchd agent on macOS, Task Scheduler on Windows), installed by `pitboard setup --apply`. Also, each write command tries one sync with a 2 s time limit; failure is silent.

**G13.4 Backoff.** After a failed sync, the next timer runs skip for 1, 2, 4, 8, then at most 15 minutes, tracked in `outbox/.backoff`.

**G13.5 Inbox.** After posting, `pitboard sync` calls `GET <hub_url>/v1/inbox?after=<inbox.cursor>` and appends each returned event (always `origin: hub`) to the lane log that holds an `asked` event with the same `uid` ; when no log on this machine holds it, to the log of the event's `lane`. Event IDs already present are skipped (INV3). Then it saves the new cursor.

**G13.6 Bootstrap.** `pitboard sync --backfill` puts every event of every lane log into the outbox once (the hub drops duplicates), so a machine that joins late sends its whole history.

### G14 Hub

**G14.1 Process.** `pitboard hub serve [--bind ADDR] [--port 8765]` runs a `ThreadingHTTPServer` with a SQLite database at `~/.pitboard/hub/pitboard.sqlite` (WAL mode). Default bind `127.0.0.1`. Binding `0.0.0.0` or `::` is refused unless `--allow-all-interfaces` is passed (INV8). The intended setup is a private network address (for example a Tailscale or WireGuard address).

**G14.2 Tables.**

```sql
CREATE TABLE events (
  rowid INTEGER PRIMARY KEY,
  event_id TEXT UNIQUE NOT NULL,
  uid TEXT NOT NULL, type TEXT NOT NULL, ts TEXT NOT NULL,
  machine TEXT NOT NULL, lane TEXT NOT NULL, origin TEXT NOT NULL,
  body TEXT NOT NULL,            -- the event exactly as received
  received_at TEXT NOT NULL);
CREATE INDEX events_uid ON events(uid);
CREATE INDEX events_inbox ON events(origin, machine, rowid);
CREATE TABLE asks (              -- the fold of events, one row per uid
  uid TEXT PRIMARY KEY, ask TEXT, machine TEXT, lane TEXT, lane_name TEXT,
  kind TEXT, severity TEXT, title TEXT, detail TEXT, why TEXT, suggested TEXT,
  steps_json TEXT, deadline TEXT, source TEXT, where_json TEXT,
  status TEXT, asked_at TEXT, answered_at TEXT, answer TEXT, answered_by TEXT,
  answered_via TEXT, done_at TEXT, done_note TEXT, withdrawn_at TEXT,
  withdrawn_reason TEXT, updated_at TEXT);
CREATE INDEX asks_status ON asks(status, asked_at);
CREATE TABLE machines (name TEXT PRIMARY KEY, token_sha256 TEXT NOT NULL, created_at TEXT, last_seen TEXT);
CREATE TABLE viewers  (name TEXT PRIMARY KEY, token_sha256 TEXT NOT NULL, created_at TEXT, last_seen TEXT);
```

**G14.3 Folding on the hub** uses the same `contract.fold` code as the lanes (one implementation). After inserting new events, the hub re-folds only the affected `uid`s.

**G14.4 Endpoints.**

| Method and path | Who | Does |
|---|---|---|
| `GET /v1/health` | anyone | `{"ok": true, "version": "...", "events": N}` |
| `POST /v1/events` | machine token | Body `{"events": [...]}`, at most 200 events and at most 1 000 000 bytes; a larger body gets HTTP 413 and nothing in it is stored (G13.2 never sends one). Each event is rejected when: its envelope (G1.2) is broken; its `machine` is not the token's machine; its `origin` is `hub`; or its `uid` already has an `asked` event from a different machine. An event with a higher `v` or an unknown `type` is stored and `accepted`, and skipped only when folding (INV9, G21.11). Returns `{"accepted": [ids], "duplicate": [ids], "rejected": [{"event_id": id, "reason": text}]}`. |
| `GET /v1/inbox?after=N` | machine token | Hub-origin events for that machine with `rowid > N`, oldest first, at most 200: `{"events": [...], "cursor": M}`. |
| `GET /v1/asks?status=open\|all&sort=severity\|deadline\|age\|lane&machine=&lane=&kind=&q=&before=&limit=` | viewer token | Folded asks with a computed `flag` for each (G5 at request time). `limit` default 200, max 1000. Paging back in history: with `status=all&sort=age`, the hub returns the **newest** `limit` asks (those with `(asked_at, uid)` less than `before` when `before` is given), ordered oldest first; `before` has the form `<asked_at>|<uid>` taken from the first row of the previous page. `q` matches title, detail, suggested, lane name (case-insensitive substring). |
| `GET /v1/asks/<uid>` | viewer token | One ask with all its events. |
| `POST /v1/answers` | viewer token | G16. |
| `GET /` and `/static/*` | anyone | The page files (they hold no data). |

**G14.5 Tokens.** `pitboard hub add-machine NAME` and `add-viewer NAME` create a random 32-byte token, store only its SHA-256, and write the token to `~/.pitboard/hub/new-tokens/<name>.token` (mode 600), printing that path, never the token. The operator copies it to the machine (`~/.pitboard/machine.token`) or pastes it into the page once. Token comparison uses `hmac.compare_digest`.

**G14.6 Headers.** Every response: `Content-Security-Policy: default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` (API) or `max-age=300` (static).

**G14.7 Service.** `pitboard setup --hub --apply` installs it as a systemd user service or launchd agent, after showing the plan.

**G14.8** The hub is optional. Everything in the terminal works without it.

### G15 Master list page

**G15.1 Files.** `pitboard/hub/static/index.html`, `app.js`, `app.css`. No inline scripts or styles (G14.6 forbids them). No external fonts, scripts or images.

**G15.2 First visit.** The page asks for the viewer token once and keeps it in `localStorage` (wrapped in `try/catch`; when storage is unavailable, it asks again each visit). It sends it as `Authorization: Bearer`.

**G15.3 Two tabs.**
- **Open**: every open ask from every machine and lane. Default sort `severity`. Count in the tab label.
- **History**: every ask ever, sorted by `asked_at` with the newest at the bottom; the page scrolls to the bottom on load and loads 200 older asks each time the operator scrolls to the top (`before=`).

**G15.4 Each row** shows: flag symbol and colour, `machine · lane_name`, short ID, age, title, then `→ suggested` or numbered steps, deadline (display time zone), status word (History), and the answer (History). A row expands on click to show `detail`, `why`, `where` and the event list. When `where.tmux_session` is present and matches the G1.3 pattern (checked again in the page), it shows a copy button for `ssh <machine> -t tmux attach -t <tmux_session>`; otherwise no button.

**G15.5 Controls.** Sort: severity, deadline, age, lane. Filters: machine, lane, kind, text search. All controls keep their values in the URL query so a view can be bookmarked.

**G15.6 Refresh.** Every 15 s, and when the window gets focus. No WebSockets.

**G15.7 Float on top.** A "Pop out" button opens a compact Open list in a Document Picture-in-Picture window (`documentPictureInPicture.requestWindow({width: 420, height: 640})`), which stays above other windows. When that API is missing, it opens `?compact=1` in a small normal window instead.

**G15.8 Colours and motion.** Light and dark themes follow `prefers-color-scheme`. Blinking red uses a 1 s CSS animation; with `prefers-reduced-motion: reduce` it is solid red with a `⚠` mark instead.

**G15.9 Safety.** All ask text is inserted with `textContent`, never `innerHTML` (agents write this text; it must never run as code).

**G15.10 Small screens.** Works at phone width (one column, 16 px side margins, no sideways scrolling).

### G16 Answers from the page and waking a lane

This gene comes after the view-only page has proven itself (Milestone 4).

**G16.1** On the page, each open ask with a `suggested` answer gets **OK**; every open ask gets **No** and **Reply** (a text box). They call `POST /v1/answers` with `{"uid": ..., "answer": text, "via": "page"}`.

**G16.2** The hub writes an `answered` event (`origin: hub`, `by: operator`, `via: page`, new `event_id`, the ask's `lane`, `machine`, `ask`) into `events`, re-folds the ask, and returns it. The ask leaves the Open tab at once.

**G16.3** The ask's machine receives the event on its next sync (G13.5) and appends it to the lane log.

**G16.4 Busy and idle.** UserPromptSubmit writes `state/<key>.activity` = `busy <ts>`; Stop writes `idle <ts>`.

**G16.5 Waking.** Only when `config.wake` is `tmux`: after G16.3, if the lane is `idle` for at least 30 s, the `where.tmux_pane` of the lane's newest `asked` event still exists, runs Claude Code (`#{pane_current_command}` is `claude` or `node`) and is still this lane's (its `#{session_name}` equals `where.tmux_session` and its `#{pane_current_path}` equals `where.cwd`; no wake when either is missing), and `state/<key>.wake` shows no wake in the last 5 minutes, sync types into that pane (then writes the time to `state/<key>.wake`), with `tmux send-keys -l` for the text and a separate `Enter`. A tmux server that restarts, for example after a reboot, gives pane ids out again from the start, so a pane id saved before it can name another lane's pane (P3 in `PROMISES.json`); window names also change (one lane's went from `bash` to `claude`), so they are not compared:

```
Pit Board: the operator answered A12 on the master list. Run `pitboard inbox` and act on it.
```

Otherwise the lane learns of the answer at its next start (the reminder lists page answers, G7.7) or when it runs `pitboard inbox`. At its next UserPromptSubmit, G7.2 also adds the context line `Pit Board: answered on the master list, not done yet: A12 → "<answer>"` for each such ask, once per ask (tracked in `state/<key>.page-told`, one `uid` per line).

**G16.6** `pitboard inbox` lists asks of this lane that are `answered` with `via: page` and not yet `done`, with the answer text, and marks nothing.

### G17 Other harnesses: the matrix, MCP server and adapters

A harness is the program an agent runs in: Claude Code; a desktop app that drives Claude Code through the Claude Agent SDK (T3 Code); Codex CLI, Gemini CLI, Cursor, GitHub Copilot CLI, OpenCode and others. Pit Board is built on Claude Code's hooks, but an ask lives in the lane log, and any program that can run `pitboard` writes it the same way. G17.4 to G17.10 say what each harness gets, what takes the place of each missing piece, and how a harness is checked before anything relies on it.

**G17.1** `pitboard mcp` is a Model Context Protocol server over stdio (JSON-RPC 2.0, standard library only). Tools: `pitboard_add`, `pitboard_list`, `pitboard_answer`, `pitboard_done`, `pitboard_withdraw`, with the same fields and rules as the G6 commands, and the lane taken from a `lane` argument or `PITBOARD_LANE`.

**G17.2** `AGENTS.md` at the repository root explains, for any agent in any harness: record asks with `pitboard add`, start the chat question with the ID, close asks when answered. Harnesses that read `AGENTS.md` get the rules; harnesses that support MCP get the tools. It also says: run `pitboard list` when a session starts and whenever you find your conversation summarised; when `pitboard` asks which lane, pass `--lane` with the key G17.6 gives; when the operator's whole message is `pb`, run `pitboard board --plain` and show its output exactly, with no comment; when it is `ok A12` or `no A12`, run that same `pitboard` command first, then act on it. These lines stand in for the hooks a harness lacks (G17.6). The same text is what goes into a harness's own rules file (G17.6, H2).

**G17.3** Adapters for other harnesses' hook systems (Cursor, Codex and others) are written only after their hook contracts are checked the same way as [Part 7](#part-7-platform-contracts-to-check-before-coding), each in `adapters/<harness>/` with its own `CONTRACTS.md`.

**G17.4 The floor.** In any harness where the agent can run a shell command (H1) or call the MCP tools (G17.1), an ask reaches the operator in four ways that need no hook: the agent's chat question starts with the ask's ID (the rules); `pitboard board --lane KEY` in any terminal on that machine shows it; the master list page (G15) shows it once the hub runs; and, when the lane runs inside tmux, the tab badge (G12) shows the count, because the agent's own `pitboard` writes set it (Part 4, data flow step 2). A harness where the agent can do neither is `unsupported`: Pit Board does nothing there, and its `docs/HARNESSES.md` row says so.

**G17.5 Capabilities.** Each harness is described by these answers, each `yes`, `no` or `unchecked` (unchecked counts as no):

| ID | Capability | Claude Code 2.1.326 |
|---|---|---|
| H1 | The agent runs shell commands and reads their output. | yes |
| H2 | Standing rules load into every session: skills in the Agent Skills format (G9.4), `AGENTS.md`, or the harness's own rules file (which one is recorded). | yes, skills |
| H3 | A session ID, stable across resumes, reaches the agent's shell commands or the hooks. | yes (C2; hooks' `session_id`) |
| H4 | A hook at session start or resume whose output reaches the model. | yes (G7.1) |
| H5 | A hook after the harness compacts or trims the conversation whose output reaches the model. | yes (SessionStart `compact`) |
| H6a | A hook before each prompt that can add context for the model. | yes (G7.2) |
| H6b | The same hook can stop the prompt and show text to the operator, with no model turn. | yes (G7.2 step 1) |
| H7 | A turn-end hook that can make the agent continue with an instruction. | yes (G7.6) |
| H8 | Hooks for the harness's question boxes and permission prompts. | yes (G7.3 to G7.5) |
| H9 | A status line: a command whose output stays on screen. | yes (G10) |
| H10 | It runs in a terminal, so tmux and the tab badge are possible. | yes |

**G17.6 What takes the place of each missing piece.** Each part of Pit Board runs at the best rung the harness's answers allow:

| Part | Needs | Without it |
|---|---|---|
| Recording an ask (G6) | H1, or the MCP tools (G17.1) | `unsupported` (G17.4). |
| The rules | H2: the skill (G9.1) where skills load; else G17.2's text in the harness's own rules file, which its `docs/HARNESSES.md` row names | The start reminder (G7.7) carries the `Rules:` lines (H4). Without H4 as well: `unsupported`, because the agent never learns to record. |
| Lane identity (G3) | H3 | `PITBOARD_LANE` in the environment the harness starts with (its row says where to set it). If it is unset, G3.7 step 4 lists the lanes and the agent passes `--lane` with G3.1 applied to its working folder's name. Two sessions in one folder then share a lane, as in G3.5; the row says so. |
| Reminder at start (G7.1) | H4 | The rules tell the agent to run `pitboard list` when a session starts (G17.2). |
| Reminder after compaction | H5 | With H6a: the prompt hook adds G7.7's list of open asks on the first prompt that comes more than 60 minutes after the last one it added in that session (`state/<key>.reminded`), and only while asks are open. Without H6a: the rules tell the agent to run `pitboard list` whenever it finds its conversation summarised (G17.2). |
| `pb`, `ok`, `no` typed at the prompt (G7.2 steps 1 to 3) | H6b | They reach the agent as ordinary messages, and the rules (G17.2) tell it to show the board, or to run `pitboard ok` or `pitboard no` before acting: one model turn, as with the board skill (G9.3). Any other answer typed into the chat is written down by the agent with `pitboard answer` (G6.2, G7.7's rules line). The operator can also read the board with `pitboard board --lane KEY` in any terminal on that machine. |
| Mentions (G7.2 step 4) | H6a | G7.7's rules line alone. |
| The catcher (G8) | H7 | No catcher. Part 9's weekly read of lane endings samples these lanes on their own, and reports them by harness. |
| Question boxes and permission prompts (G7.3 to G7.5) | H8 | Not recorded. They show in the harness itself while they wait. |
| Status segment (G10) | H9 | The tab badge (G12) when H10 holds and the lane runs in tmux; otherwise the page in its pop-out window (G15) is the view that stays on screen. |
| Tab badge (G12) | H10 and tmux | None. |
| Self-update (G21) | nothing from the harness: timers, the stable copy and the launcher run outside every harness | Adapter commands call `$PITBOARD_HOME/bin/pitboard`, never a version folder (G21.4). |

**G17.7 One code path.** An adapter (G17.3) only turns a harness's hook input into the input the G7 handlers already read, and their output into the form the harness expects. It never decides anything about asks itself. A harness whose hooks have Claude Code's event names, input fields and output fields (each checked, G17.8) needs no adapter: it runs `pitboard hook <event>` through the stable copy, `$PITBOARD_HOME/bin/pitboard`.

**G17.8 Checking a harness.** Before any part relies on a harness, H1 to H10 are checked against an installed version the same way as [Part 7](#part-7-platform-contracts-to-check-before-coding) (read the harness's documentation, then run a throwaway hook or command that logs what it receives). The results go into `docs/HARNESSES.md`: one row per harness and version, with the date, the machine, each answer, and the rung each part of G17.6 runs at. One real input per hook event is saved as `tests/fixtures/harnesses/<harness>/<event>.json`, with personal data removed. A row older than 90 days is marked `stale` and checked again before the next release that touches its adapter.

**G17.9 The first harness: T3 Code.** T3 Code drives Claude Code through the Claude Agent SDK, and Codex and OpenCode through their own command-line tools; it never calls a model itself. Each provider is its own row. T3 Code is checked first: on a fixed test machine if the machines' owner rules the exception for it, else on another test machine booked for it, where the lane installs T3 Code itself, so the check never waits on one machine. The row records the T3 Code version used. The Claude provider comes first:
1. whether its sessions load the operator's plugins and their hooks (T3 Code's source hands the SDK only the plugin folders given as `--plugin-dir` launch arguments; which settings files its sessions load was not settled by reading the source on 2026-11-19);
2. whether SessionStart fires with `source: compact`;
3. how a UserPromptSubmit block's `reason` shows in T3 Code's window, and whether the prompt stays out of the conversation;
4. that H9 is `no`: a desktop app has no status line, so the page's pop-out is the view that stays on screen.
Its Codex provider comes next.

**G17.10 Tests.** `tests/test_g17_matrix.py` replays each harness's saved inputs (G17.8) through its adapter, or straight through `pitboard hook` for a harness that needs none, and checks that the lane log gets the same event types and fields, apart from IDs and times, as the Claude Code fixtures for the same action: an ask recorded, a reminder returned, an approval written. A rung of G17.6 that a harness row relies on and no saved input proves is a failing test.

### G18 Setup and doctor

**G18.1** `pitboard setup` prints a numbered plan of every file it would create or change, with paths, and changes nothing. `pitboard setup --apply` does it, keeping a `.bak-<timestamp>` copy of every file it changes. Items: config file, stable launcher copy (G21.4), marketplace auto-update (G21.2), update timer (G21.3), status line wrapper (G10.5), tmux lines (G12.2, only with `--tmux`), sync timer (G13.3, only when `hub_url` is set), hub service (G14.7, only with `--hub`). Every timer and service it installs calls `$PITBOARD_HOME/bin/pitboard`, never a version folder. `--minimal` limits the plan to the config file, the stable launcher copy and the status line wrapper (what Milestone 1 needs). From plan 1.28, `--apply` also writes `$PITBOARD_HOME/setup-record.json`: each settings file it changed, its bytes before (or that there was none), its bytes after, and what was set. `pitboard uninstall` (G18.3) reads it.

**The mode of a settings file setup changes** (plan 1.32). Setup writes a settings file it changes as private (mode 600), and `.bak-<timestamp>` keeps the mode the file had. From 0.1.3 (P25), the plan item for that file says so before anything changes, when the mode it has now is not 600: `the file is written private (mode 600; it is 664 now); its backup keeps 664; uninstall puts 664 back only when it puts the file back byte for byte`. The README says the same. From 0.1.4 (P26), setup keeps the mode the file had, and the plan item says nothing about the mode; for a file an earlier setup made private, uninstall puts the recorded mode back when the mode is still 600, and when the person changed it since, it leaves it and the census says so.

**The person's own eyes** (plan 1.32, P28, due 0.1.4; the family's rule 7). What a person must hear before `setup --apply` or `uninstall --apply` changes anything is printed by that command itself, at the person's own terminal, and it goes on only when they press a key. An agent's pasting of those lines is never the only road to the person. It waits only at a real terminal: run with no terminal (an agent's tool call) it does not wait and does not hang, and the must-hear block is still the last thing it prints (the maintainer's ruling, plan 1.32).

**G18.1 folder mode** (for M2a; promises P5, P6, P7 and P9). `pitboard setup --folder DIR` prints the plan for one folder and changes nothing; `--apply` does it. It never touches the user's own settings. Outside a session `pitboard` is not on the PATH. Run the stable launcher of an earlier install (`$PITBOARD_HOME/bin/pitboard`, which runs the newest installed version, G21.4). On a machine with no install, first run `claude plugin install … --scope local` in that folder, then run the plugin's own copy.
1. Refuses, changing nothing:
   - the home folder (local scope there reaches every session started from it);
   - a folder where more than one Claude Code session runs. Sessions are counted by the command each process was started as (`claude`, or a path ending in it), with its folder from `/proc/<pid>/cwd` on Linux and `lsof -a -p <pid> -d cwd` on macOS. Never by process name: on macOS a session's process name is its version file (P6);
   - a folder whose `.claude/settings.local.json` is not a JSON object, sets its own `statusLine` (the wrapper wraps only the shared one), already sets the plugin, or sets another `PITBOARD_HOME` in `env`;
   - a folder that already has a record.
2. Writes the record `.claude/pitboard-folder.json`: the plugin, the time, the folder's settings file exactly as it was (or that there was none), whether `.claude` existed, and the Pit Board home.
3. Runs `claude plugin install <plugin>@<marketplace> --scope local` in the folder (120 s limit, as G21.3), unless Claude Code's plugin registry already lists the plugin with local scope for that folder.
4. Makes the Pit Board home if it is missing: the `--minimal` items without the status line setting (the config file, the stable launcher copy and the wrapper file).
5. Sets the folder's `statusLine` to the home's wrapper (`padding` 0, `refreshInterval` 5). When the home is not the default one, it also sets `env.PITBOARD_HOME` there, so a session started in that folder, or brought back there by any tool, keeps its home.
6. If a step fails, it undoes the steps before it, and says what failed (P9). For a failed `claude plugin` command it shows Claude Code's error, not only its last line: from its first error line (the first line that starts with `✘`, or else the first line of its error output) to the end, at most 12 lines, without Claude Code's progress lines (`SSH not configured, cloning via HTTPS: …`, `HTTPS clone failed, retrying with SSH: …`), which it prints last. When that error shows the clone failed over SSH because GitHub accepted no key (`Host key verification failed` or `Permission denied (publickey)`), the message first says so in plain words, then what to do:
   - after `HTTPS clone failed, retrying with SSH`: "Claude Code could not clone the plugin from GitHub over HTTPS, and the retry over SSH failed: this account is not set up for GitHub over SSH (GitHub accepted no key from it). Check that this machine reaches github.com over HTTPS, or add a GitHub key to this account, then run the same command again."
   - otherwise (Claude Code 2.1.280 clones a `github` entry over SSH only): "Claude Code could not clone the plugin from GitHub over SSH; this account is not set up for GitHub over SSH (GitHub accepted no key from it). Update Claude Code (2.1.330 clones over HTTPS when SSH is not set up), or add a GitHub key to this account, then run the same command again."
   - These lines (the plain words and Claude Code's error) are wrapped to G6.8's 100 columns, never cut with `…`; a continued line starts with two spaces.

`pitboard uninstall --folder DIR` (G18.3; until plan 1.28 `setup --folder DIR --undo`, which stays for 0.1.3 only as the old spelling: it says so on its first line and does the same) runs `claude plugin uninstall <plugin>@<marketplace> --scope local` in the folder (a failure is shown as in step 6), then puts the folder's settings back:
- byte for byte, when what is left after removing Pit Board's entries equals the recorded file under the same rule;
- otherwise it removes only Pit Board's entries: `statusLine` when it is the home's wrapper, the plugin's key under `enabledPlugins`, and `env.PITBOARD_HOME` unless the person had set it before.
Last, it deletes the record, and removes `.claude` if setup made it and it is now empty. Tests: `test_G18_1_folder_*`.

**G18.3 `pitboard uninstall`** (plan 1.28, P17). Leaving is `uninstall`: one word that takes Pit Board, and everything it made, off this computer, however it was set up. `remove` stays free for an object of Pit Board's own. Like `setup`, it prints its numbered plan first and changes nothing; `--apply` does it. A person who wants to leave is never refused.
1. **What it finds.** Each folder install: Claude Code's registry entries for the plugin with local scope, and each `.claude/pitboard-folder.json` record (G18.1 folder mode). The user-scope install. Each Pit Board home: the default, `$PITBOARD_HOME`, and any home a folder record names. Each settings file a `setup-record.json` names, or, for a home set up before plan 1.28, `~/.claude/settings.json` when its `statusLine` runs that home's wrapper. `--folder DIR` limits all of this to one folder: G18.1's folder undo.
2. **Three answers.** Every read a step hangs on (the registry, a record, a settings file, the wrapper's recorded command, a lane log) answers yes, no, or could not be read. On the third answer nothing is deleted, emptied or reported gone. The census names what could not be read and the one next step, and the exit code is 11. One home's files go only after every read about that home has been made (its lane logs counted first). When a step before them was not finished (a read failed, or a plugin uninstall failed or found no `claude`), the home's copy stays, so its `uninstall` can run again (plan 1.30).
3. **A settings file** that Pit Board changed:
   - still exactly what setup wrote (its bytes equal the record's bytes after): put back byte for byte, or deleted when there was none before;
   - changed since: only Pit Board's entry changes. `statusLine.command` goes back to the person's own command, which the record or the wrapper (`# pitboard-original-command:`) holds; with none, the `statusLine` key is removed when its command is the home's wrapper. Every other key stays as it is. In a folder's settings, G18.1's rule (the folder undo moves into `leave.py` with the rest) (the plugin's key under `enabledPlugins`, and `env.PITBOARD_HOME` unless the person set it);
   - could not be read, or is not a JSON object: touched in no way. A settings file is never written when it could not be read.
   Claude Code itself writes `~/.claude/settings.json` on `plugin install` (`enabledPlugins`, the catalog) and rewrites it on its own `plugin uninstall`, as seen on a stock VM (plan 1.30, ruled by the skills' department head). So the promise is: the status line setting is back to exactly the value the person had (or absent when they had none), and nothing else in the file was changed by Pit Board. Byte for byte is claimed only where it can be shown: the bytes setup found, when nothing else wrote the file. When Claude Code's own uninstall rewrites the file later in the same run, the census row says so after `put back byte for byte`.
**The census names what is left, and counts only what is setup's** (plan 1.32, the family's rule 8). Setup records in `setup-record.json` the name of each backup it makes; the census counts only those as setup's (P29). Other tools write backups with the same form of name, so a name is never the test. A record that cannot be read gives no count and says so (rule 6); for a home set up before the record listed backups, the census says it cannot tell which are setup's. After Claude Code's own `plugin uninstall`, the census also names the version folder Claude Code left in its plugin cache, marked orphaned, and the kept Windstorm catalog with the command that removes it and what that does to another Windstorm plugin from the same catalog, each in the words a stock-VM round saw (P30).

4. **The plugin.** In each folder, as G18.1 folder mode. The user-scope install: `claude plugin uninstall windstorm-pit-board@<marketplace>` (120 s limit, a failure shown as in G18.1 step 6). When `claude` is not on the PATH, or it fails, the install is kept, and the census names the one command the person runs. A project-scope install lives in a repository's shared settings, so it is kept: the census names it and the command. The catalog (the marketplace) is kept, because it also lists other Windstorm skills.
5. **What is the person's stays.** The person's things are kept and counted:
   - every lane log under `lanes/` (open and closed asks) and `lanes.json`;
   - the record of what Pit Board did on the computer: `logs/`, and the `.bak-<timestamp>` copies setup kept of the person's settings files.
   Everything else Pit Board made in a home goes: the launcher copy and its `.prev` files, the wrapper, `config.json`, `update/`, `state/`, the lock files, and every timer, service and tmux line setup installed (G21.3, G13.3, G14.7, G12.2). Setup's own record, `setup-record.json`, is Pit Board's: once every step before it is done, it goes last, and then the home goes when it is empty and Pit Board made it (plan 1.34, P48, the family's rules 23 and 8). Setup records that it made the home before it writes anything there; the default `~/.pitboard` is Pit Board's by name; a folder `PITBOARD_HOME` named that was there before setup stays and is named as the person's. A leave that did not finish keeps the record for the next run. So on a computer where no asks were recorded, the whole-home listing after the leave equals the listing before setup, every difference a named line, with no step by hand. One census row counts what is kept, `kept: N asks (O open) in L lane logs, and the log of what Pit Board did in <path> (yours)`. No line `uninstall` prints is a delete, recursive or not (plan 1.34: a printed `rm -r <home>` names a folder a setting can name, to be run later, when anything may have landed in it). In the plan, while the home's copy is there, the line after the census offers Pit Board's own way, as the person's act: `They are yours. When you are sure, you can delete them yourself, at your own terminal: <home>/bin/pitboard uninstall --apply --delete-asks-and-log` (`~/` when it is under the home folder). After `--apply` it says only `They are yours, to keep or delete after you look at them.` Every command `uninstall` prints for a person has been run exactly as printed (the family's rule 7) and names this computer's way, never a bare `pitboard`, which is not on a person's PATH. The `cd DIR && claude plugin uninstall ...` lines for a folder or a project-scope install are printed the same way, quoted when a path needs it.
6. **Deleting what is kept** is a separate, explicit choice: `pitboard uninstall --apply --delete-asks-and-log`. It runs only when its standard input and output are both a terminal, and it names what it deletes and the count, then waits for the person to type that number, before anything changes (plan 1.30: asked after, a mistyped count left Pit Board off and its copy gone, so the right count had nothing left to run). A wrong count changes nothing at all. When the count has changed by the time the asks would be deleted (a session added one), nothing is deleted and the census says so. An agent cannot give it for the person: run from an agent's tool, or with any other answer, it deletes nothing and says why. The skill tells agents never to delete what `uninstall` kept, by the flag or by hand, unless the person asks in their own words.
   A momentary lock is a wait, not a refusal. When a lane's lock is held (a hook writing), `uninstall` waits as other commands do (G2.3). If the lock is still held after that, it says which lane holds it and the one next step (run it again in a moment), changes nothing in that home, and exits 7 (lane busy, G6.3).
7. **The order.** Settings files first, so a running session's status line goes back to the person's own. Then the plugin installs, then each home's files, the running launcher copy last.
8. **The census** is the last thing printed: one line per thing Pit Board made, `gone`, or `kept` and why; in the plan (no `--apply`), `would go` where `--apply` says `gone` (plan 1.30). Run again, it is safe: with nothing of Pit Board's left it says `nothing of Pit Board is here`, then the `kept` row for the asks when there are any. Exit code 0 when everything planned is gone or kept on purpose; 11 when a read or a removal failed.
9. **What stays can take itself off.** The whole of `uninstall` lives in one file, `pitboard/leave.py`, standard library only, importing nothing else of Pit Board. The plugin's `pitboard uninstall` and the stable copy both run that file, so there is one way of leaving. The stable copy (`$PITBOARD_HOME/bin/pitboard`, `pitboard/launch.py`, `pitboard/leave.py`) runs `uninstall` to the end with no plugin folder anywhere: after Claude Code's own uninstall, and after Claude Code has removed the orphaned folder too. It does points 1 to 8 (the folder records, the user-scope install when `claude` is there, the settings files with their three answers, the asks kept and counted, the census). A test runs the copy alone, in a home with no plugin folder and no registry row, to the end. A home whose copy is from before plan 1.28 has no `leave.py` until a session start refreshes it. Until then, the README names what to put back by hand: the `statusLine` the wrapper's `# pitboard-original-command:` line holds, then everything in the home but `lanes/`, `lanes.json` and `logs/` (plan 1.30: the record of what Pit Board did is the person's, point 5). Those lines are run once, exactly as the README writes them, on a stock VM with a home whose copy is from 0.1.2, before 0.1.3 is tagged.
10. **Seen, not only tested:** on a stock Linux VM first, including a home left behind by Claude Code's own uninstall, then in the clean test account on a Mac that carries Apple's developer tools, in place of the proof script's own removal. Then, if a box's own login allows it, one real Claude Code session whose status line is seen to come back as it was; otherwise that is written as not seen.

**G18.2** `pitboard doctor` checks and prints one line per check, `OK` or `PROBLEM: <what> · fix: <how>`: Python version, home folder modes, config valid, every lane log readable and its invalid-line count, state caches fresh, hooks installed (plugin enabled), status line wrapper in place, tmux badge format present (when in tmux), hub reachable and token accepted (when `hub_url` set), outbox size and oldest file, clock within 2 minutes of the hub's, running version vs newest installed vs newest released, marketplace auto-update on, last update check and its result, any pin or bad version, sessions running an older hook generation.

### G19 Secret masking

**G19.1** Before any text field is written, it is masked: each match below is replaced by `[masked]`.
- Private key blocks: `-----BEGIN [A-Z ]*PRIVATE KEY-----` through the matching `END` line; with no `END` line (cut text), through the end of the field.
- Credentials in URLs: `://[^/\s:@]+:[^@\s]+@` → `://[masked]@`.
- Known token shapes: `sk-[A-Za-z0-9_-]{20,}`, `sk-ant-[A-Za-z0-9_-]{20,}`, `gh[pousr]_[A-Za-z0-9]{30,}`, `github_pat_[A-Za-z0-9_]{30,}`, `xox[abprs]-[A-Za-z0-9-]{10,}`, `AKIA[0-9A-Z]{16}`, `AIza[0-9A-Za-z_-]{35}`, `glpat-[A-Za-z0-9_-]{20,}`, `npm_[A-Za-z0-9]{36}`.
- JWTs: `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`.
- Key-value secrets, including prefixed names (`DB_PASSWORD`, `AWS_SECRET_ACCESS_KEY`) and JSON (`"password": "x"`): `(?i)([A-Za-z0-9_.-]*(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key)["']?\s*[:=]\s*)["']?[^\s"',}]+["']?` → keeps group 1, masks the value: `DB_PASSWORD=[masked]`, `"password": [masked]`.
- Bearer headers: `(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}`.
- Long opaque strings: any run of 40 or more characters from `[A-Za-z0-9+=_-]` (no `/`, so file paths and URLs are left alone) that contains at least one digit, one lower-case and one upper-case letter. (Git commit hashes have no upper-case letters and are left alone.)

**G19.2** Masking is applied in `contract.py` on the way in, before validation (G1.9), so every path (command, hooks, MCP, hub answers) gets it. The rules run in the order listed above.

**G19.3** Tests build every fake secret from pieces at run time (`"sk-" + "a" * 24`), never as one string in the repository.

### G20 Tests and CI

**G20.1** `pytest` under `tests/`, one file per gene: `test_g1_contract.py`, `test_g2_store.py`, and so on. Each codon has at least one test named with its ID (rule 2).

**G20.2** Shared fixtures: a temporary `PITBOARD_HOME`; a fake transcript writer; recorded hook inputs in `tests/fixtures/hooks/<event>/*.json` (copied from real runs during the Part 7 checks, with personal data replaced).

**G20.3** Tests never touch the real home folder, the network beyond `127.0.0.1`, or tmux (tmux calls go through one function that tests replace).

**G20.4** The hub tests start a real server on `127.0.0.1` on a free port and call it with `urllib`.

**G20.5** The page gets a smoke test: a script that loads `index.html` with the hub running and checks that `app.js` and `app.css` load and that no inline script or style exists.

**G20.6 CI** runs the tests on Python 3.9 (the floor, G21.15), 3.10 and 3.13, on Linux (`ubuntu-24.04`) on every pull request and every push to `main` and `release-*` (a push to a pull request's branch runs through the pull request, so each job runs once). On macOS (`macos-26`), a pull request runs one job, the floor's Python, and a push to `main` or a `release-*` branch runs all three (plan 1.30, the family's rule 17: GitHub gives the account a few Mac runners for all its repositories together, and one afternoon 34 runs sat queued with none running). A newer push to a pull request cancels that pull request's older runs (a concurrency group per pull request, cancel in progress); a push to `main` or a release branch is never cancelled. The merge gate expects the reports of the event it runs on: 5 on a pull request (three Linux, one macOS, the skill gate), 7 on `main` and `release-*`. A `proven` line that leans on CI for macOS 3.10 or 3.13 names a run on `main`. Its log names every test and its outcome (`pytest -v`, without `-q`, which cancels it: one line per test with its outcome, and a skip's reason on its own test's line), so a reader can see that a given test ran, and passed, in each job; a count cannot show that. `-rA` is not enough: it folds skips that share a place and a reason into one line with a count and no names. This is a public repository, so CI uses GitHub-hosted runners, the same as Windstorm Pit Stop: public repositories do not use paid minutes, and self-hosted runners must never serve a public repository (anyone's pull request could run code on our machines).

**G20.7** `tests/smoke_hooks.sh` feeds every recorded hook input to `pitboard hook` and checks exit code 0 and the expected output shape.

**G20.8 CI rules** (ruled by the skill's owner, 2026-11-17): the workflow sets `permissions: contents: read` at workflow level, uses no repository secrets (only the automatic `GITHUB_TOKEN`, read-only, which `gh skill publish --dry-run` may need), never uses `pull_request_target`, and runs only on standard GitHub-hosted runners: every `runs-on` value (directly, or each value of the matrix entry it names, or of a matrix `include`) must name its runner image, `^(ubuntu|macos|windows)-[0-9]+(\.[0-9]+)?$`, never `latest` (plan 1.29, P22). Seen on 2026-11-23: `ubuntu-latest` moved to a new Ubuntu under the matrix, and setup-python had no 3.9 for it. Larger-runner labels (for example `ubuntu-latest-4-cores`, `macos-15-xlarge`), self-hosted labels and runner groups are refused: larger runners are billed even on public repositories, and an unpaid GitHub bill is why private repositories run on our own machines. A test reads `.github/workflows/*.yml` and fails if any of these four rules is broken. CI also runs the G9.5 gate.

### G21 Self-update: always the newest Pit Board

Every installation, for every person who installs Pit Board, must find new releases by itself, install them, move every running part onto them, and step back by itself if a release is bad. Nobody should ever have to touch a machine to get an update. This gene is as important as G1: a fix nobody receives is no fix.

**There are five running parts, and each one needs its own way onto a new version:**

| Running part | Started | How it gets the new version |
|---|---|---|
| Installed plugin files | by Claude Code | Claude Code's marketplace auto-update, plus our updater (G21.2, G21.3) |
| Hooks inside sessions that are already running | when the session started | the launcher runs the newest installed code (G21.4); a reload only when the hook list itself changes (G21.6) |
| `pitboard` commands agents run | each call | the launcher (G21.4) |
| Sync and update timers, status line | by the operating system / Claude Code | they call the stable launcher copy, never a version folder (G21.4) |
| Hub and the open page | by the service manager / the browser | the hub restarts itself onto the new version (G21.7); the page reloads itself (G21.8) |

**G21.1 What a release is.** A release is a commit on `main` that raises `version` in `.claude-plugin/plugin.json` (semantic versioning: `MAJOR.MINOR.PATCH`), with a matching `CHANGELOG.md` entry and a git tag `vMAJOR.MINOR.PATCH`. Releases are made on `main`: a merge that does not raise the version is not shipped to anyone. A release is made only when CI is green on that exact commit, which includes the promise gate (G21.14), and is published with `gh skill publish --tag vMAJOR.MINOR.PATCH`, which validates the skills again, creates the tag and a GitHub release with notes. The repository has the `agent-skills` topic, and GitHub secret scanning and push protection are on. These are repository settings, set once and checked again at each release. The marketplace entry (in `TheWindstorm/windstorm-pit-stop`'s `marketplace.json`) pins the release. Its source is `{"source": "url", "url": "https://github.com/TheWindstorm/windstorm-pit-board.git", "ref": "vMAJOR.MINOR.PATCH", "sha": "<the tag's full 40-character commit>"}`, so a machine that installs it later gets that release, not whatever `main` is that day. The source is a URL over HTTPS, not a `github` source: Claude Code fetches a `github` source over SSH when it updates (2.1.330) and even when it installs (2.1.280), which fails on a machine with no GitHub key; the URL form installs and updates there (seen on both versions, plan 1.25, P14). Each release moves the pin in the same hour as its tag, and Claude Code's marketplace update (G21.2) then brings it to installs (check C11 for how Claude Code decides an update exists: `version` in `plugin.json` comes first).

**One version in every place** (plan 1.23). The version is stated in `.claude-plugin/plugin.json`, in `pitboard/__init__.py` (`__version__`, which `pitboard version` prints) and in `CHANGELOG.md`'s top dated heading, `## X.Y.Z (YYYY-MM-DD)`. The suite fails when one of them differs. Above that heading, the list of changes not yet released has the heading `## X.Y.Z (not yet released)`, and it names a later version than the top dated one. The skill files state no version. A sister skill showed why, on 2026-11-22: its manifest named an old version through three releases, so `claude plugin update` said it was already at the latest version and kept the old code, and a person never got the fixes.

**A release step: the tag's fresh clone.** After the tag is made and before the marketplace pin moves to it, the suite runs in a fresh clone of the tag. It refuses the tag unless the tag's name, without its `v`, equals every version label in it: `plugin.json`, `__version__`, and each `CHANGELOG.md` heading above the previous release's. So a tag that kept an old label, or a not-yet-released heading, is refused, and the pin does not move to it. It also refuses the tag while a `PROMISES.json` row due in that version has an empty `proven` (plan 1.29, P18). A row stands in for its proof on a real machine only in the one case the row names: a row that can only be proven after its release (a count over days, say) carries `proven_after_release` with the reason, and the check lists such rows by id instead of refusing. It is never a blanket rule that would force a false `proven` line.

**G21.2 Switch on Claude Code's own auto-update.** Claude Code leaves auto-update off for marketplaces other than Anthropic's. `pitboard setup --apply` (and the first SessionStart after install, if `self_update` is true and the operator has not written a choice) sets `"autoUpdate": true` on the marketplace's entry under `extraKnownMarketplaces` in `~/.claude/settings.json`, keeping a backup, exactly as Windstorm Pit Stop does. An explicit `"autoUpdate": false` written by the operator is never changed; `pitboard doctor` reports it. Where auto-update is off, the README's two update lines (`claude plugin marketplace update thewindstorm`, then `claude plugin update windstorm-pit-board@thewindstorm`) do the same by hand, and they must move a stock install with no GitHub key and no sign-in to the newest release (P14, plan 1.25). The README names the Claude Code versions they were seen to work on and, for an install made before the catalog's entry changed form, the way back: uninstall, then install again.

**G21.3 Our own updater**, because Claude Code checks marketplaces when it starts, and sessions that run for weeks rarely start. `pitboard self-update` (run by a user timer every `update_check_hours`, at a random minute fixed per machine so a fleet does not update all at once):
0. The timer fires every hour at this machine's fixed minute (`update/minute`, a random 0 to 59 chosen once by `setup`).
1. Exit at once if `self_update` is false, or if the last check was less than `update_check_hours` ago (unless `--now`).
2. Run `claude plugin marketplace update <marketplace>` then `claude plugin update windstorm-pit-board@<marketplace>`, each with a 120 s limit (check C12 for the exact commands; Windstorm Pit Stop runs these same two).
3. For every installed version folder that is in neither `update/good-versions` nor `update/bad-versions` (including ones Claude Code installed by itself at start-up), run its self-check (G21.5). Pass: add it to `update/good-versions`, and remove `update/pin` if the pin was set by a rollback and this version is newer. Fail: add it to `update/bad-versions` (G21.10).
4. Write `update/last-check.json`: `{"checked_at", "before", "after", "result": "up-to-date" | "updated" | "rolled-back" | "failed", "detail"}`.
5. A failure leaves the running version unchanged, is one log line, and shows in `pitboard doctor` (exit code 9).

`pitboard self-update --check` only reports whether a newer release exists (by running the marketplace update and comparing versions), and installs nothing.

**G21.4 The launcher: running code follows the newest install.** Claude Code keeps each version in its own folder (`~/.claude/plugins/cache/<marketplace>/windstorm-pit-board/<version>/`) and a running session keeps calling the folder it started with. So nothing Pit Board runs uses that folder's code directly. Every entry point (hooks, `bin/pitboard`, timers, the status line, the hub) goes through `pitboard/launch.py`, which picks the version to run, in this order:
1. The pinned version, if `update/pin` names one and its folder exists. Not for `pitboard self-update`: it always starts at step 2, so a home pinned to a version that has no `self-update` (0.1.1 or older) can still be released with `--unpin` or pinned again. With a home pinned to such a version, `pitboard self-update --unpin` through the stable copy works and prints the `version` line of what it then runs.
2. If `self_update` is false: the install path recorded for `windstorm-pit-board` in `~/.claude/plugins/installed_plugins.json` (the user-scope install first), whatever its version.
3. The install path recorded in `installed_plugins.json`, if its version is in `update/good-versions`.
4. The highest version folder in the plugin cache that is in `update/good-versions`, has no `.orphaned_at` marker, and contains `pitboard/cli.py`.
5. Its own plugin folder, if `launch.py` is running from a plugin version folder (it has `pitboard/cli.py` beside it) and that folder has no `.orphaned_at` marker. No step picks a folder that carries that marker (plan 1.28, P17).
6. Of the install paths recorded in `installed_plugins.json`, the one with the highest version, whatever `update/good-versions` holds (this is how the stable copy runs before any version has passed a self-check). Never the first one listed: on a machine where folders have different versions, the first entry can be the oldest (P8).
7. Nothing found: print `pitboard: no installed version found` to stderr and exit 1 (hooks exit 0, INV6).

**Three answers for the launcher's reads** (plan 1.29, P19). Each read the choice hangs on (`update/bad-versions`, `update/pin`, `update/good-versions` and `installed_plugins.json`) answers yes, no, or could not be read. A missing file is no. A file that exists but cannot be opened, cannot be decoded or (for the registry) is not a JSON object is could not be read. On could not be read, the launcher does not move to another version on this pass. It runs only its own folder (step 5), when that folder is a runnable version folder with no `.orphaned_at` marker. Otherwise (the stable copy has no version folder of its own) it runs nothing:
- `status` prints one short true line and exits 0: `Pit Board cannot read its files · run ~/.pitboard/bin/pitboard version` (the copy's own path; that command names the file and the error). An empty status line would tell the person that nobody is asking them anything, an absence shown for an error, in the one place they look (rule 6; plan 1.31);
- a hook exits 0;
- any other command prints `pitboard: could not read <path> (<error>); nothing run` and exits 1.

A hook's log line names the read that failed. An unreadable `bad-versions` could otherwise have run a version marked bad: the same fault sits in sister skills already released. One test fails each read in turn.

**After Claude Code's own uninstall** (plan 1.28, P17). `claude plugin uninstall` removes the plugin's row from `installed_plugins.json`, but it leaves the version folder, marked `.orphaned_at`, and it leaves the status line setting and the Pit Board home. Seen on 2026-11-23 on a stock Linux machine with Claude Code 2.1.280 and 2.1.330, with 0.1.2:
- the stable copy's `status` and `version` exited 1 with `no installed version found`, which the wrapper hides, so the status line showed nothing of Pit Board;
- the person's `statusLine` still ran the wrapper;
- a SessionStart hook from a session still running ran the orphaned folder's code in full (step 5): the reminder and a log line.

So, when the registry was read and has no row for the plugin, and step 1 to 6 pick nothing:
- `status` prints one short true line, `Pit Board was removed by Claude Code · run ~/.pitboard/bin/pitboard uninstall`, and exits 0. That command works alone (G18.3 point 9). The line names it only while that copy is there; with none it says `Pit Board was removed by Claude Code` (plan 1.30);
- a hook does nothing and exits 0. It writes one log line, `<hook>: Pit Board was removed by Claude Code; nothing done`, and no line that looks like a working Pit Board;
- `uninstall` runs the stable copy's own `leave.py` (G18.3 point 9). No code from an orphaned folder runs: an orphaned folder's own launcher runs the home's `leave.py`, never its own, and with no home copy left it runs nothing (plan 1.30);
- any other command prints step 7's line and adds the same `uninstall` line.

When the registry could not be read, that is not "removed": nothing of this paragraph applies (G18.3 point 2). Nor is a registry that is missing (Claude Code never installed Pit Board on this account): "removed" needs a registry that exists, was read and has no row for the plugin (plan 1.30). The README says what still shows after Claude Code's own uninstall, and the one command that takes it off.

A version that is installed but not yet in `update/good-versions` is self-checked by the next `pitboard self-update` run (G21.3), so new releases are used within `update_check_hours`. It then puts the chosen folder first on `sys.path` and calls that version's `pitboard.cli.main()`. `launch.py` itself must stay tiny and must never change in a way that an older copy of it cannot still run the newest code. It only picks a folder and calls `cli.main()`, with one exception (plan 1.28): for `uninstall`, it runs `leave.py` beside itself, so what stays on the computer can take itself off.

**The stable copy.** `pitboard setup --apply` copies `bin/pitboard` to `$PITBOARD_HOME/bin/pitboard`, `pitboard/launch.py` to `$PITBOARD_HOME/pitboard/launch.py` and, from plan 1.28, `pitboard/leave.py` to `$PITBOARD_HOME/pitboard/leave.py` (the same relative layout as the plugin, G6.1), and points timers, services and the status line wrapper at `$PITBOARD_HOME/bin/pitboard`, writing `PITBOARD_HOME` into each of them (timers do not inherit the shell's environment). They never name a version folder. Every `~/.pitboard/bin/pitboard` in this plan means `$PITBOARD_HOME/bin/pitboard`. Each `pitboard self-update` run refreshes the copy from the chosen version. Until the updater exists, the session-start hook refreshes it instead (G7.1 step 5), so a launcher fix such as P8's reaches a home made by an earlier release.

**Refreshing the stable copy from a session start.** The hook acts only when it runs from an installed version folder in the plugin cache whose version is not in `update/bad-versions`, only when the stable copy exists (it never makes one), and not when `self_update` is false (G21.12). It refreshes when its version is newer than the one the copy came from (`$PITBOARD_HOME/pitboard/copied-from`, one line, which `setup --apply` writes too; a copy without it came from a release before 0.1.2), or when that line names its own version but the copy's files differ from its own (a torn copy). It never writes an older copy over a newer one. A broken launcher never replaces a working one:
1. Write its `bin/pitboard`, `pitboard/launch.py` and (from plan 1.28) `pitboard/leave.py` whole into a new temporary folder in `$PITBOARD_HOME`, in the stable copy's layout.
2. Run that folder's `bin/pitboard version` against this home (3 s limit), so the check runs the same code the copy will run. Unless it exits 0 with a `version` line (G6.2), stop and keep the old copy.
3. Keep the current copy as the one backup (`.prev` beside each file, replacing any older backup), then rename the checked files over the copy and write `copied-from` last. There is no moment without a launcher.
4. Write one log line that names both versions (`stable launcher 0.1.1 -> 0.1.2, backup kept`), or, when it stopped, one that says what this hook did and what it read, and why (`stable launcher: this hook left the copy as it was (it read 0.1.1 when it started): the 0.1.2 launcher did not answer in 3 s`). By then another hook may already have refreshed the copy, so the line never says the copy is old.

Any number of hooks refreshing the same home at the same second leave one whole copy: each writes whole files under its own temporary names and renames them, all with the same content, and the last rename wins. If two versions race, the next session start of the newer one refreshes again, because `copied-from` or the torn-copy check then shows it. A failure leaves the old copy, is one log line, and the hook still exits 0 (INV6). On a very busy machine every hook of a restore may miss the 3 s check. That start then leaves the launcher as it was, which is the safe side, and the next session start tries again. The limit is not raised: a session start never waits longer for Pit Board. Until a start succeeds, `pitboard version` shows that the copy is older (G6.2), so a person can see it. The README says in one sentence that a session start may refresh the home's launcher, when it does, and how to switch that off (`self_update` false), and in one more that on a very busy machine a start may leave the launcher as it was and the next start tries again.

**G21.5 Self-check.** `pitboard doctor --quick` runs from the new version's folder, in a temporary `PITBOARD_HOME` with a copy of the machine's largest lane log (or the built-in fixture `tests/fixtures/selfcheck.jsonl` when the machine has none), and must: import every module; fold the copied log with the same result as the running version; run `add`, `ok`, `done`, `board`, `status` against the temporary home; finish in under 20 s. Any failure is a fail.

**G21.6 Hook generation.** `hooks/generation.json` holds one integer. It is raised only when `hooks/hooks.json` changes (an event, a matcher, a command shape): those are the only changes a running session cannot pick up through the launcher. A test fails when `hooks/hooks.json` changes without `generation.json` changing (same rule as Windstorm Pit Stop). A session's loaded generation is the one in `$CLAUDE_PLUGIN_ROOT/hooks/generation.json` (the folder its hooks were loaded from); the running generation is the one in the folder the launcher chose. When they differ, the session gets one line, once per generation (tracked in `update/generation-shown/<session_id>`), shown to the operator (Stop hook `systemMessage`, G7.6 step 6): `Pit Board updated its hooks. Type /reload-plugins at a break (no turn starts).` When Windstorm Pit Stop's fleet mode is installed with `reload_plugins` on, it does this by itself at a break.

**G21.7 Hub update.** The hub service runs `~/.pitboard/bin/pitboard hub serve`. Every 10 minutes the hub asks the launcher which version it would pick now. If that differs from the running version, the hub stops accepting new connections, finishes the requests in flight (at most 10 s), and exits with code 0. The service manager (`Restart=always` on systemd, `KeepAlive` on launchd) starts it again on the new version. Database changes: a `schema_version` table; each release's migrations run in order at start-up, after copying the database to `hub/backup/pitboard-<old version>.sqlite`. **Migrations are additive only**: they add tables, columns and indexes, and never drop, rename or change the meaning of one, so an older hub version can always run on a newer database (it ignores what it does not know). A migration that fails restores the copy, writes its own version into `update/bad-versions`, and exits; the service manager then starts it again and the launcher picks the last good version (G21.4). Because the `events` table is the truth and `asks` can be rebuilt from it (INV2), `pitboard hub status --refold` rebuilds `asks` after any doubt.

**G21.8 Page update.** `/v1/health` returns the hub's `version`. The page remembers the version it loaded with; when a refresh (G15.6) sees a different version, it reloads itself, keeping its tab, sort and filters (they are in the URL, G15.5).

**G21.9 Telling the operator.** After a version change on a machine, the first SessionStart there shows one line to the operator (not to the model): `Pit Board updated to 0.3.1: <the first line of that version's CHANGELOG entry>`. Once per machine per version, never in every lane. `pitboard version` and the page footer show the running version.

**G21.10 Rolling back.** When a version fails its self-check (G21.5) or a hub migration (G21.7), or when its hook errors on one machine pass 20 in an hour (each handler's exception is counted in `logs/pitboard.log`; `pitboard self-update` reads the count), that version goes into `update/bad-versions` on that machine. The launcher never picks a bad version (G21.4), so the machine is back on its newest good version at the next call; if the bad version was the pinned one, the pin is removed. A rollback by itself writes no pin. When a newer release passes its self-check, the machine moves to it as usual. `pitboard self-update --pin VER` and `--unpin` let the operator choose by hand, and they come before the rest of the updater (P10): `--pin VER` refuses a version with no runnable folder in the plugin cache or one in `update/bad-versions` (exit 2, nothing changed), and otherwise writes `update/pin` (G21.4 step 1); `--unpin` removes it. Both work on this Pit Board home only, and print the `version` line, which names the pin; the status line and the hooks follow at their next call.

**G21.11 Compatibility across versions** (INV11). Every release must:
- read every lane log every earlier release wrote (G1.13);
- keep the hub API at `/v1` working: a change that would break a `/v1` caller goes to a new `/v2` path, and `/v1` stays for at least 90 days and at least two releases;
- accept events from machines one minor version older and newer;
- keep every config key's meaning; a renamed key is still read under its old name for at least two releases.
A test replays the fixtures of every earlier release (`tests/fixtures/releases/<version>/`, saved at each release) against the current code.

**G21.12 Opting out.** `self_update: false` (or `PITBOARD_SELF_UPDATE=0`) turns off G21.2 and G21.3, and makes the launcher use G21.4 step 2: the install path recorded in `installed_plugins.json`, whatever its version (so the operator's own `claude plugin update` still takes effect). Pins still work. Nothing else changes.

**G21.13 Never during the operator's work.** Updating installs files only. It never restarts or types into a session, except G21.6's one-line note and, if the operator has Pit Stop's fleet mode, Pit Stop's own reload at a break.

**G21.14 Promises: a lesson from real use is a gate.** `PROMISES.json` at the repository root holds what real use showed must change or must stay true, and the version each is due in. The same mechanism is used by the other Windstorm skills.
- **A row** has these fields:
  - `id` (`P1`, `P2`, ...), `seen` (what happened, with its date) and `promise`.
  - `codon`: a codon or invariant of this plan.
  - `owner`: `person` when the person Pit Board is for saw it on their own machine, else `maintainer`.
  - `first_ship_in` and `ship_in` (versions), `test` (the name of a test), `proven` (which machine, which version and when it was seen to work; a proof that leans on CI names the run and the test, as its log shows them) and `issue`.
  - `moved_why` and `moved_by_person`.
  - `kind` (optional, plan 1.23): `guard` for a promise taken from a fault seen in a sister skill, not in this one. Its `seen` says where it was seen. A guard row is held like any other: test, `ship_in` and `proven`.
  - `proven_after_release` (optional, plan 1.29): the reason this row can only be proven after its version is released. The tag's fresh-clone check (G21.1) lists the row instead of refusing the tag. The gate below still refuses the next version while `proven` is empty.
- **A lesson heard and not taken** goes under `declined`, with `heard` and `why`, so nothing is dropped without a word.
- **A row is never deleted.** A promise that proves wrong is closed by a new row that says why.

`tests/test_g21_promises.py` refuses the version in `.claude-plugin/plugin.json`, so CI goes red:
- while a row due in that version or earlier has no test, or names a test that is not named with the row's codon (rule 2), or that the test runner does not collect and run to a pass in this checkout. A name found as text is not enough: a skipped test, a test the runner cannot collect (under a helper after its `return`, inside a string, renamed), and a test whose name is defined twice in one file, where only the last definition runs, do not count. Every row that names a test is checked so at every version, due or not. A row's test skipped on a condition of the machine, with a reason written in the skip (another system, a program missing), is listed as not run here, with that reason, and is not a pass. A skip with no reason fails, and so does an unconditional skip (a `skip` mark, or a `pytest.skip` that is not under a condition), whatever its reason, because that test runs on no machine. The gate runs the rows' tests itself and reads the runner's own report, leaves itself out of what it runs, has a time limit, and leaves nothing behind when it is stopped part-way;
- once the version is past a row's `ship_in`, while that row has no `proven`;
- when a row's `ship_in` differs from its `first_ship_in` with no `moved_why`, or, for a `person` row, with no `moved_by_person`: only that person's word moves their row, restated there;
- when a row is not whole, its codon is not in this plan, two rows share an id, or a declined lesson has no reason.

**G21.15 The Python floor** (plan 1.26, P16). Pit Board runs on Python 3.9 or newer, and that floor is checked, not only written. 3.9 is the `python3` that comes with Apple's developer tools (3.9.6 on macOS 13; `/usr/bin/python3` is Apple's shim to it), and the whole suite passes there unchanged. The floor is one value, `FLOOR = (3, 9)` in `pitboard/launch.py`. Part 0 rule 4, the README and the lowest Python in CI (G20.6) name the same version, and a test fails when one place differs.
1. **The first act.** Before it reads or writes anything, `launch.py` compares `sys.version_info` with `FLOOR`. Below the floor, Pit Board makes nothing (no folder, no log line, no lock, no launcher refresh) and stops:
   - `pitboard hook <event>`: one line on stderr, `Pit Board needs Python 3.9 or newer; found <X.Y.Z> at <the interpreter's path>`, nothing on stdout, exit 0. A hook never breaks the session (Part 0 rule 6).
   - `pitboard status`: the segment is `Pit Board needs Python 3.9 or newer, found <X.Y.Z>`, with no newline at the end, exit 0 (the exception in G10.4).
   - any other command, `setup` included: the hook's line on stderr, then where Pit Board does run (`install Python 3.9 or newer, or put one first on PATH as python3`), exit code 10, nothing written.
2. **The older grammar.** `launch.py` stays readable by Python 3.6's grammar, so an older interpreter reaches the check instead of stopping on a syntax error. A test parses it with that grammar. `pitboard.cli.main()` makes the same check first, because a launcher copy from before 0.1.3 calls a newer folder's `main()` without checking.
3. **Why 3.8 is refused, though most tests pass there.** Python 3.8 has no `zoneinfo`, so G4 falls back without an error and shows wrong times. Seen on 2026-11-23: an ask at 16:00Z on 4 July was shown as `11:00 AM ET`, not `12:00 PM ET`, and the CT, MT, PT and London labels were wrong. Showing what is not true is worse than stopping. A sister skill showed the other way it goes wrong: it named "Python 3.10+" without checking it, and on a stock machine with Python 3.8 it registered and started a service before it crashed on newer grammar.
4. **Seen, not only tested.** Before 0.1.3 is tagged, the refusal is seen once on a real machine whose own interpreter is 3.8 (a stock Ubuntu 20.04.6). Pit Board is also run once on a Mac with the `python3` that comes with Apple's developer tools named explicitly: `setup`, one hook and the status line, with the times right.
5. Changing the floor is a plan change. It is looked at again when the Python that macOS ships moves.

---

## Part 6. Repository layout

```
windstorm-pit-board/
  .claude-plugin/plugin.json      name "windstorm-pit-board", version, description, author, homepage, license, keywords
  .github/workflows/tests.yml     G20.6
  bin/pitboard                    G6.1
  pitboard/__init__.py            __version__ (must equal plugin.json's version; a test checks)
  pitboard/launch.py              G21.4 the launcher: picks the version folder, calls its cli.main()
  pitboard/cli.py                 G6 argument parsing and dispatch only
  pitboard/update.py              G21 updater, self-check, pin and rollback
  pitboard/contract.py            G1 validation and fold, G19 masking
  pitboard/store.py               G2 files, locks, cache, config
  pitboard/lane.py                G3
  pitboard/timefmt.py             G4
  pitboard/flags.py               G5
  pitboard/render.py              G10, G11 text output
  pitboard/hooks.py               G7
  pitboard/catcher.py             G8
  pitboard/badge.py               G12
  pitboard/sync.py                G13, G16 lane side
  pitboard/setup.py               G18
  pitboard/mcp.py                 G17
  pitboard/hub/server.py          G14
  pitboard/hub/db.py              G14.2, G14.3
  pitboard/hub/static/index.html  G15
  pitboard/hub/static/app.js      G15
  pitboard/hub/static/app.css     G15
  hooks/hooks.json                G7
  hooks/generation.json           G21.6
  skills/pit-board/SKILL.md       G9.1
  skills/board/SKILL.md           G9.3
  skills/<name>/references/       G9.4, longer material a skill links to
  evals/<name>/triggers.json      G9.6
  evals/<name>/tasks/             G9.7
  docs/EVALS.md                   G9.6, G9.7 results
  adapters/                       G17.3, empty until then
  tests/                          G20
  tests/fixtures/releases/        G21.11, one folder per released version
  tests/fixtures/harnesses/       G17.8, one folder per harness, one real input per hook event
  docs/CONTRACTS.md               Part 7 results
  docs/HARNESSES.md               G17.8, one row per harness and version (H1 to H10, the rung of each part)
  docs/PILOT.md                   Part 9 measurements
  PROMISES.json                   G21.14, lessons from real use and the version each is due in
  AGENTS.md                       G17.2
  DNA-STRAND-MASTER-PLAN.md       this plan
  README.md  TODO.md  CHANGELOG.md  LICENSE  NOTICE
```

The plugin is listed in The Windstorm's marketplace (the `TheWindstorm/windstorm-pit-stop` repository's `marketplace.json`) from 0.1.0, for M2a, pinned to the release tag (G21.1); announcing it and the README for strangers stay at Milestone 5. It installs with:

```
/plugin marketplace add TheWindstorm/windstorm-pit-stop
/plugin install windstorm-pit-board@thewindstorm
```

---

## Part 7. Platform contracts to check before coding

Claude Code changes often. These are the facts the hooks depend on. Before writing G7, G8, G9 or G10, check each one against the installed version (read the documentation and run a throwaway hook that logs its stdin), write the result and the version number into `docs/CONTRACTS.md`, and save one real input per hook event (personal data removed) into `tests/fixtures/hooks/`. If a check fails, use its fallback; do not invent a third way.

**Already confirmed from the Claude Code documentation on 2026-11-17** (installed version 2.1.326). These still get one recorded real input each, but the design relies on them:
- SessionStart: `source` is `startup`, `resume`, `clear`, `compact` or `fork`; stdout or `hookSpecificOutput.additionalContext` reaches the model. `CLAUDE_ENV_FILE` is given to SessionStart (also Setup, CwdChanged, FileChanged), its `export` lines run before each later Bash command, and CwdChanged clears them.
- UserPromptSubmit: `decision: "block"` with `reason` shows the reason to the operator and the prompt never reaches the model; `suppressOriginalPrompt: true` keeps the prompt text out of the message; `additionalContext` is supported. Skill and plugin commands go through the separate UserPromptExpansion event (`command_name`, `command_args`).
- Stop: input has `stop_hook_active`, `last_assistant_message`, `transcript_path`; `decision: "block"` with `reason` makes the agent continue; at most 8 blocks in a row.
- PreToolUse input has `tool_name`, `tool_input`, `tool_use_id`; `AskUserQuestion` is a valid matcher.
- PermissionRequest exists (input `tool_name`, `tool_input`, no `tool_use_id`). Notification has `notification_type` (including `permission_prompt`, `idle_prompt`, `agent_needs_input`) and cannot block.
- Plugin commands and skills are named `/<plugin>:<name>`. A plugin's `bin/` is on the Bash tool's `PATH` while the plugin is enabled. Plugin environment variables (`CLAUDE_PLUGIN_ROOT` and others) are given to hooks but not to the agent's Bash commands. `CLAUDE_PLUGIN_DATA` exists.
- A plugin cannot set `statusLine`. The status line input has `session_name`.
- Hooks inherit the parent environment.

**Still to check:**

| ID | Fact to check | Used by | Fallback if it fails |
|---|---|---|---|
| C1 | One real SessionStart input per `source`, recorded as fixtures. | G7.1 | (documented) |
| C2 | `CLAUDE_CODE_SESSION_ID` is set in the agent's Bash commands (seen on 2.1.326, not documented). | G3.7 | `PITBOARD_LANE` from `CLAUDE_ENV_FILE` (G7.1); else the reminder names the lane key and the skill says to pass `--lane KEY`. |
| C3 | What SessionStart's `session_title` holds; the transcript's `{"type": "custom-title", "customTitle": ...}` record after `/rename` (seen, not documented). | G3.2 | The status line's `session_name`; else the `session-` key. |
| C4 | Whether a typed `/board` (not a registered command) reaches UserPromptSubmit; whether UserPromptExpansion can block like UserPromptSubmit; whether ANSI colours in a block reason are shown. | G7.2, G7.9 | `pb` only; the board skill (G9.3); `--plain` output. |
| C5 | One real Stop input with `last_assistant_message`, recorded as a fixture. | G8 | Read the transcript. |
| C6 | The shapes of `tool_input.questions` and of PostToolUse's `tool_response` for `AskUserQuestion`. | G7.3, G7.4 | If PostToolUse has no answers, record `answer: "answered in the question box"`. |
| C7 | A PermissionRequest hook that returns nothing leaves the normal prompt unchanged. Also record which tools fire it (2.1.326: `AskUserQuestion` does, so G7.5 skips it). | G7.5 | Use Notification with `notification_type: permission_prompt` instead. |
| C8 | The exact name of the board skill (`/windstorm-pit-board:board`) and that `$ARGUMENTS` reaches it. | G9.3, G7.9 | Whatever name the platform gives. |
| C9 | Removed in plan 1.1: the documentation settles it (a plugin cannot set `statusLine`, G10.5). | | |
| C10 | `TMUX_PANE` reaches hooks in a tmux session. | G12, G1.3 `where` | Leave `where.tmux_*` empty; badge only from commands the agent runs. |
| C11 | How Claude Code decides a plugin from a marketplace has an update: a raised `version` in `plugin.json`, or any new commit. | G21.1 | If any commit counts, every merge to `main` must be a release (version raised each time). |
| C12 | The exact commands `claude plugin marketplace update <name>` and `claude plugin update <plugin>@<marketplace>`, their exit codes, and that they work while sessions are running. | G21.3 | Pit Stop's tested calls; else only Claude Code's own auto-update at start-up (G21.2). |
| C13 | `installed_plugins.json` layout, the version folder layout, and the `.orphaned_at` marker on old folders (seen; Pit Stop relies on them). | G21.4 | Highest version folder only. |
| C15 | `gh skill publish --dry-run` (GitHub CLI 2.104 or newer, preview) exists on the CI runners, and what it needs (auth, network). | G9.5 | Install a pinned `gh` release in the workflow; if it still cannot run, the standard-library check in `tests/test_g9_skills.py` alone gates, and the gap is reported to the skill's owner. |
| C16 | Where an installed plugin's code runs from, by catalog source: for a `github` or git-URL source, its version folder in `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` (the hooks' `CLAUDE_PLUGIN_ROOT`); for a directory source, the cache copy that `installed_plugins.json` names, or the catalog folder in place. | G21.4 (version folders, refreshing the stable copy) | An install whose code runs outside the cache is treated like a checkout: the session-start refresh does not act for it. A check of cache behavior uses a git source. |
| C14 | `command -v pitboard` works in an agent's Bash command while the plugin is enabled (plugin `bin/` on `PATH`). | G9.2, G6.1 | The skill and the reminder name `$PITBOARD_HOME/bin/pitboard`. |

---

## Part 8. Milestones and acceptance

Each milestone ends with a release, a `CHANGELOG.md` entry and a short note in `docs/PILOT.md`.

### M0 Plan (this commit)
- This plan, `README.md`, `TODO.md`, `LICENSE`, `NOTICE` in `TheWindstorm/windstorm-pit-board`.

### M1 One lane (0.1.0): G1, G2, G3, G4, G5, G6 (all but `sync`, `inbox`, `hub`, `mcp`, `self-update`), G7.0, G7.1 (steps 1 to 3), G7.2, G7.7, G7.8, G9, G10, G11, G16.4, G18.1 `--minimal`, G19, G21.1, G21.4, G21.6, G21.11, G21.14, G20 for those
The launcher (G21.4) ships in the very first release, so that every later release reaches the first installs without anyone reinstalling.
Build order: G1 → G19 → G4 → G5 → G2 → G3 → G21.4 launcher → G6 → G11 → Part 7 checks → G10 → G18.1 `--minimal` → G7.0 → G7.1 → G7.7 → G7.2 → G16.4 → G7.8 → G9.
Accepted when, in one pilot lane:
1. All tests pass on Python 3.10 and 3.13, and the skill format gate (G9.5) is green.
2. The agent records its asks with `pitboard add` without being reminded, for 2 days. *Moved to M2a* by a ruling of the skill's owner on 2026-11-22. It was shown on 1 of the 2 days. It could not be shown on 2, because the pilot lane's decisions go to its owner, not to the operator, and a made-up ask would be a false proof.
3. After a `/compact`, the reminder appears and lists the open asks.
4. The status segment shows the count, and nothing when none are open.
5. `pb` prints the board at the bottom of the screen in under 1 s, with no model turn.
6. `ok A1` records the operator's approval and the agent acts on it.
7. A second build installed beside the first (version raised) and listed in `update/good-versions` by hand (the updater that does this comes in M2) is picked up by the running session's next hook call without a restart.
8. The operator samples it and says to keep it.

### M2 Every lane, updating itself (0.2.0): G9.6, G9.7, G7.1 step 4, G7.3 to G7.6, G7.9, G8, G12, G18 (all of `setup`, and `doctor`), G21 (all)
Accepted when: the trigger evals (G9.6) pass for every skill and the with-skill vs. without-skill evals (G9.7) are recorded; question boxes and permission prompts are recorded and closed by themselves; the catcher meets G8.5 over one week on the pilot lanes; tab badges show; `setup` and `doctor` work on Linux and macOS; a release published on GitHub reaches every machine within `update_check_hours` + 1 hour with nobody touching them; a deliberately broken test release is rolled back by itself on a test machine. Then it is rolled out to all lanes one machine at a time.

M2 is rolled out in two stages, because the status line wrapper sits in front of every lane's own status line:
- **M2a** starts the hour 0.1.0 is tagged. 0.1.0 goes into the lanes of the skill family itself, each in its own folder only: the plugin with local scope, and the status line wrapper set in that folder's settings. One command installs it in a lane and one command undoes it (`pitboard setup --folder DIR --apply` and `--undo`, G18.1 folder mode); the undo is tested before the first lane gets it.
  M2a is accepted when the agent records its asks to the operator without being reminded, on two calendar days, each with at least one real ask recorded unprompted in an M2a lane (M1's item 2, moved; promise P4 in `PROMISES.json`).
- **M2b** is every lane on the machine. It starts only after M2a has run 3 days with no needless block and no broken status line, and after the owners of those lanes have each said go.

### M3 Master list, view only (0.3.0): G13 (no inbox), G14 (no `/v1/answers`), G15, G21.7, G21.8, G17.2, G17.4 to G17.10 (T3 Code's rows)
The page is the floor every harness lands on (G17.4), so the harness matrix comes with it.
Accepted when: every lane's asks from every machine are on the page within 90 s of being recorded; the page pops out on top; History scrolls back to the first ask; a hub restart and a machine offline for a day lose nothing; a new release moves the hub and the open page onto it by themselves; `docs/HARNESSES.md` holds checked rows for T3 Code's Claude and Codex providers (on a fixed test machine if the machines' owner rules the exception, else on another booked test machine, where the lane installs T3 Code itself), and an ask recorded in a T3 Code lane there is on the page within 90 s.

### M4 Answers from the page (0.4.0): G13.5, G14 `/v1/answers`, G16
Accepted when: an OK on the page reaches the lane log within 90 s; with `wake: tmux`, an idle lane wakes and acts, and a busy lane is never typed into.

### M5 Public release and other harnesses (1.0.0): G17.1, G17.3 and the rows of G17.8 for other harnesses, announcing the marketplace listing, README for strangers
Accepted when: a person outside The Windstorm installs it from the marketplace on a clean machine and gets an ask on their status line in under 10 minutes, using only the README.

---

## Part 9. How we know it works

Measured in the pilot and written into `docs/PILOT.md` weekly:

| Measure | Target |
|---|---|
| Real asks that were recorded (sampled by reading 20 lane endings a week) | ≥ 90% |
| Needless catcher blocks per lane per day | ≤ 1 |
| Open asks older than 3 days, across all lanes | trending to 0 |
| Median time from ask to answer | falling week on week |
| Time from `pb` typed to the board shown, over remote desktop | < 1 s |
| Status segment time | < 50 ms |
| Lost events (lane logs vs hub, compared by `pitboard export`) | 0 |
| Machines on the newest release, `update_check_hours` + 1 hour after it ships | 100% (except pinned ones, each with its reason in `doctor`) |
| Releases rolled back somewhere by G21.10 | each one gets a fix and a test before the next release |

---

## Part 10. Decisions already made, and why

| Decision | Why |
|---|---|
| Name: **Windstorm Pit Board** | The pit board is the sign the crew holds out to a driver going past at speed: short, big, readable in a second. It pairs with Windstorm Pit Stop. |
| Python standard library, plain HTML/JS page | Runs on every machine that runs Claude Code without installing anything; agents can read and change it directly; it matches Pit Stop. Speed is not the limit here (a few writes an hour per lane). The data format, not the language, is what keeps it future-proof. |
| Append-only JSON Lines per lane | Nothing is ever lost, history is free, any language can read it, and syncing is copying events. |
| Status order is one-way except `reopened` | Clock differences between machines cannot undo an answer. |
| One hub on the operator's private network, pulled by a browser page | No cloud, no accounts, works from a phone, no app to install on every machine. |
| Document Picture-in-Picture for "always on top" | A real floating window from a web page, no Electron app to build and update. An app wrapper can come later if this falls short. |
| Agents write the ask; hooks only catch what they miss | The agent knows what it needs and can suggest the answer; text scanning alone cannot. |
| Short IDs per lane (`A12`) plus global `uid` | Short IDs are easy to type in `ok A12`; the `uid` keeps them unique across lanes and machines. |
| Nothing shows when nothing waits | A view that always shows something becomes clutter and gets ignored. |
| GitHub-hosted CI | Public repository: free, and no stranger's pull request can run on our machines. |
| Self-update built in from the first release | A fix that never reaches an install is no fix. Claude Code's own auto-update is off for non-Anthropic marketplaces and only runs at start-up, and sessions run for weeks; so Pit Board switches it on, checks by itself, and routes every running part through a launcher that always runs the newest good version. |
| Roll back by machine, by itself | A bad release must not need a person at each of a dozen machines to undo it. |
| The Windstorm skill standard (G9.4 to G9.7, G21.1) | Set by the skills' owner for every Windstorm skill on 2026-11-17: the open Agent Skills format so any harness that reads skills can use them, a CI gate so a broken description never ships (an unquoted colon broke one), and evals that prove a skill fires when it should and earns its place. |
| `pb` as the board shortcut | Plugin commands are always prefixed (`/windstorm-pit-board:board`), too long to type many times a day over a slow connection. Two letters, intercepted before the model, cost nothing. |

---

## Part 11. Open questions

These are not in the build. Each needs a decision (and a plan change) before any code.

1. **Herdr and other lane managers:** how each reads the tmux `@pitboard` option or a lane's state, so the badge shows in their own view.
2. **Pit Stop link:** should Windstorm Pit Stop's "waiting for you" list read Pit Board's state caches?
3. **Notifications:** a push to the operator's phone when a `blinking-red` ask appears. Which channel?
4. **Operator's own items:** adding personal to-do items on the page (an `asked` event with `source: operator`, `by: operator`, written by the hub). The format allows it already; the page does not offer it yet.
5. **Several operators:** each ask could name who it waits on. Out of scope until someone needs it.
6. **Desktop app wrapper** around the page, only if the pop-out falls short in daily use.
7. **Marketplace catalog:** confirm with the skill's owner, before M5, which repository's `marketplace.json` lists Pit Board (today Part 6 says Windstorm Pit Stop's).
8. **One harness matrix for the skill family. Answered by the skill's owner on 2026-11-20: yes, one matrix (P6), and it grows by division.** H1 to H10 and the `docs/HARNESSES.md` row shape live in this plan for now. Windstorm Pit Stop's harness verdict table reuses H1 to H10 and adds its own capabilities from H11 up (for example PreCompact, the auto-compact window, its updater). When a third skill needs the matrix, it moves to a shared home, by a plan change.
9. **A Mac without Apple's developer tools.** There `/usr/bin/python3` is a shim with no interpreter behind it, and there is no `python`. What the first `python3` call shows there has not been seen, so this plan does not describe it. Whether the hooks' command line reaches the G21.15 check there is not known either. Look at it on a Mac test machine without those tools; what a hook does there is a decision for the skill's owner.

---

## Appendix A. Worked examples

### A.1 Three lines of a lane log

```json
{"v":1,"event_id":"0f5c2b8e9a7d4e61b3c2a1f0e9d8c7b6","type":"asked","uid":"6a1e4c2b9d8f4a7e8c3b2a1d0e9f8c7b","ask":"A12","lane":"api-server","lane_name":"API Server","machine":"studio-1","session_id":"0e7a5c11-2f4b-4c8e-9d3a-6b1f2e8c4a90","ts":"2026-11-15T13:00:00.000Z","origin":"lane","by":"agent","data":{"kind":"decision","severity":"blocking","title":"Merge #651 now or wait for review?","why":"The release branch is waiting on it.","suggested":"Merge now: CI is green and no files are shared with open work.","deadline":null,"source":"agent","where":{"cwd":"/home/dev/api","tmux_session":"api-server"}}}
{"v":1,"event_id":"1a2b3c4d5e6f40718293a4b5c6d7e8f9","type":"answered","uid":"6a1e4c2b9d8f4a7e8c3b2a1d0e9f8c7b","ask":"A12","lane":"api-server","lane_name":"API Server","machine":"studio-1","session_id":"0e7a5c11-2f4b-4c8e-9d3a-6b1f2e8c4a90","ts":"2026-11-17T19:04:05.123Z","origin":"lane","by":"operator","data":{"answer":"Merge now: CI is green and no files are shared with open work.","via":"ok"}}
{"v":1,"event_id":"2b3c4d5e6f7081929a3b4c5d6e7f8091","type":"done","uid":"6a1e4c2b9d8f4a7e8c3b2a1d0e9f8c7b","ask":"A12","lane":"api-server","lane_name":"API Server","machine":"studio-1","session_id":"0e7a5c11-2f4b-4c8e-9d3a-6b1f2e8c4a90","ts":"2026-11-17T19:06:41.002Z","origin":"lane","by":"agent","data":{"note":"Merged as 4f1e2d3."}}
```

### A.2 An agent recording a hand item

```
$ pitboard add --kind hand --severity blocking --title "Create a Stripe account for test payments" \
    --why "Checkout tests cannot run without a test key." \
    --step "Go to dashboard.stripe.com/register" --step "Sign up with the company email" \
    --step "Tell me when done; I will set up the test key myself" --deadline +3d
A14 recorded (BLUE). Ask it in chat as: "A14: Create a Stripe account for test payments"
```

### A.3 The status line

```
Opus 5.5 · 41% context · 🔴 3 asks · oldest 2d
```

### A.4 The operator answering

```
> ok A12 A15
```

The hook records both approvals; the agent sees: `Pit Board: the operator approved A12: "Merge now: ..."; A15: "No, redirect it to /pricing". Carry them out now. When each is finished, run: pitboard done <ID>.`

### A.5 The skill body

```markdown
# Pit Board

You keep a list of everything you need from the operator (the person you work for), so nothing you ask gets lost in the scroll, a compaction or a restart.

If `command -v pitboard` finds nothing, use `~/.pitboard/bin/pitboard` wherever this skill says `pitboard`.

## When you need the operator

Before you ask the operator anything that you need an answer or an action for (a decision, an approval, a login, a payment, a signature, an account, a purchase, information only they have):

1. Record it: `pitboard add --title '<the question or action, one line>' --suggested '<the answer you recommend and why, short>'`.
   - The ask's words go in single quotes, as above, with no backtick and no dollar sign in them; name a command in plain words. Inside double quotes a shell runs what a pair of backticks holds before pitboard even starts, and an ask is often about a risky command. An apostrophe ends single quotes: leave it out or say it another way.
   - Something only they can do with their own hands (pay, sign, log in, create an account, buy): add `--kind hand` and one `--step '...'` per step, and no `--suggested`.
   - It truly cannot wait (a deadline today, something breaking): `--severity urgent`. You can carry on without it for now: `--severity can-wait`. Otherwise leave the default (blocking).
   - A real deadline: `--deadline "YYYY-MM-DD HH:MM"` or `--deadline +2d`.
2. Ask in chat, starting with the ID it printed: "A12: Merge #651 now? I suggest merging now because ..."
3. One ask per decision. Do not bundle three questions into one.
4. If the answer is the operator's to give but you send the ask somewhere else instead of the chat (another agent, such as a coordinator or a reviewer, or a shared board), record it first all the same, and put its ID and this line in your message: "A12 is recorded on the Pit Board for the operator. Answer under A12, or say 'not mine to answer' under A12."
   - They answer under the ID: `pitboard answer A12 --by agent --answer '<who>: <their answer>'`.
   - They say it is not theirs to answer: the ask stays open for the operator. Ask the operator in chat, starting with A12.

Do not record: questions to yourself, questions to other agents that they can answer themselves, rhetorical questions, status updates.

## When it is answered or no longer needed

- The operator answers in chat: `pitboard answer A12 --by operator --answer '<their answer, a few words>'`.
- The operator types `ok A12` or `no A12`: it is already recorded; just act on it.
- The work is finished: `pitboard done A12 --note '<what you did, one line>'`.
- It no longer matters: `pitboard withdraw A12 --reason '<why>'`.

## Never

- Never put a password, key or token in an ask. Name it instead ("the Stripe test key").
- Never mark an ask answered for the operator unless they answered it.
- Never delete what `pitboard uninstall` kept (the asks and the log), with `--delete-asks-and-log` or by hand, unless the operator asks for it in their own words in this conversation.

## Showing the list

The operator types `pb` for the open asks and `pb all` for the history. You can show them with `pitboard board` and `pitboard board --all`.
```

---

## Appendix B. Changing this plan

1. A change to the plan is its own pull request, titled `Plan: <what changes>`, touching only this file (and `CHANGELOG.md`).
2. Its description says which codons change, why, and which existing tests change with them.
3. Raise the plan version: `1.x` for additions and clarifications; `2.0` for any change to G1 that is not an addition.
4. Never renumber codons. A removed codon stays in place as `**G6.9 Removed in plan 1.3:** <reason>.`; new codons get the next free number in their gene.
5. Code that follows a plan change is a separate pull request.

---

*Windstorm Pit Board and The Windstorm are names of The Windstorm. The DNA Strand Master Plan is The Windstorm's way of building: the blueprint first, complete enough that any builder can follow it exactly.*
