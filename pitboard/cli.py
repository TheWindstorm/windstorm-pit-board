"""The pitboard command (plan G6): argument parsing and dispatch.

Exit codes (G6.3): 0 ok, 1 unexpected error, 2 bad usage, 3 lane unknown, 4 ask not found,
5 transition not allowed, 6 invalid field, 7 lane busy, 8 hub unreachable, 9 update failed.
Standard library only.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from . import __version__, contract, flags, lane, launch, render, stablecopy, store, timefmt

WIDTH = 100


class Fail(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _NeedFull(Exception):
    """A target ask is not in the live cache: run the build again with every ask (G2.11)."""


class Out:
    def __init__(self, message="", ids=None, asks=None, data=None, code=0):
        self.message, self.ids, self.asks, self.data, self.code = message, ids or [], asks or [], data or {}, code


def fit(text, width=WIDTH):
    """G6.8: every line fits in `width` columns; longer lines end with '…'."""
    return "\n".join(ln if len(ln) <= width else ln[: width - 1] + contract.CUT_MARK
                     for ln in text.split("\n"))


# ---------------------------------------------------------------- argument parsing (G6.2)

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Fail(2, f"pitboard: {message}")


def _common(p):
    p.add_argument("--lane", metavar="KEY")
    p.add_argument("--json", action="store_true")


def _fields(p, kind=True):
    if kind:
        p.add_argument("--kind", choices=contract.KINDS, default="question")
        p.add_argument("--severity", choices=contract.SEVERITIES, default="blocking")
    else:
        p.add_argument("--severity", choices=contract.SEVERITIES)
    p.add_argument("--suggested")
    p.add_argument("--why")
    p.add_argument("--detail")
    p.add_argument("--step", action="append", dest="steps", metavar="STEP")
    p.add_argument("--deadline")


def parser():
    top = _Parser(prog="pitboard", description="Windstorm Pit Board: what waits on a person.")
    sub = top.add_subparsers(dest="command", parser_class=_Parser)
    sub.required = True

    p = sub.add_parser("add", help="record an ask")
    _common(p)
    p.add_argument("--title", required=True)
    _fields(p)

    p = sub.add_parser("update", help="change an open ask (Pit Board itself: self-update)")
    _common(p)
    p.add_argument("id", nargs="?")
    p.add_argument("--title")
    _fields(p, kind=False)
    for flag in UPDATER_FLAGS:                     # refused with a line that names self-update (G6.2)
        p.add_argument(flag, nargs="?", const=True, default=None, help=argparse.SUPPRESS)

    p = sub.add_parser("self-update", help="Pit Board's own updater: --pin VER and --unpin so far (G21.10)")
    _common(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--pin", metavar="VER")
    g.add_argument("--unpin", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--now", action="store_true")

    p = sub.add_parser("answer", help="write down an answer")
    _common(p)
    p.add_argument("id")
    p.add_argument("--answer", required=True)
    p.add_argument("--by", choices=("operator", "agent"), default="agent")

    for name in ("ok", "no"):
        p = sub.add_parser(name, help="approve the suggested answer" if name == "ok" else "decline")
        _common(p)
        p.add_argument("ids", nargs="+", metavar="ID")

    p = sub.add_parser("done", help="mark an ask done")
    _common(p)
    p.add_argument("id")
    p.add_argument("--note", default="")

    for name in ("withdraw", "reopen"):
        p = sub.add_parser(name, help=f"{name} an ask")
        _common(p)
        p.add_argument("id")
        p.add_argument("--reason", required=True)

    p = sub.add_parser("list", help="one line per ask")
    _common(p)
    p.add_argument("--all", action="store_true")
    p.add_argument("--sort", choices=("severity", "deadline", "age", "lane"), default="severity")

    p = sub.add_parser("board", help="the board: open asks, or history with --all")
    _common(p)
    p.add_argument("--all", action="store_true")
    p.add_argument("--limit", type=int, default=render.HISTORY_LIMIT)
    p.add_argument("--width", type=int)
    p.add_argument("--plain", action="store_true")

    p = sub.add_parser("status", help="the status line segment (reads the status line JSON on stdin)")
    _common(p)
    p.add_argument("--plain", action="store_true")

    p = sub.add_parser("setup", help="show the setup plan; --apply does it")
    _common(p)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--minimal", action="store_true")
    p.add_argument("--folder", metavar="DIR", help="one folder only (G18.1 folder mode): its own settings, never the user's")
    p.add_argument("--undo", action="store_true", help="with --folder: take it out of that folder again")
    p.add_argument("--plugin", default=None, help="with --folder: the plugin@marketplace to install")

    p = sub.add_parser("uninstall", help="take Pit Board off this computer: a plan; --apply does it (G18.3)")
    _common(p)                                         # main() hands uninstall to leave.py before this parser
    p.add_argument("--apply", action="store_true")
    p.add_argument("--folder", metavar="DIR")
    p.add_argument("--delete-asks-and-log", action="store_true", help="only at your own terminal: you type the count")
    p = sub.add_parser("hook", help="hook entry point (reads the hook JSON on stdin)")
    _common(p)
    p.add_argument("event")

    p = sub.add_parser("show", help="every field and event of one ask")
    _common(p)
    p.add_argument("id")

    p = sub.add_parser("lane", help="this session's lane")
    _common(p)

    p = sub.add_parser("export", help="every event (jsonl) or every ask (csv)")
    _common(p)
    p.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    p.add_argument("--all-lanes", action="store_true")

    p = sub.add_parser("version", help="running, installed and pinned versions")
    _common(p)
    return top


def _status_parser():
    """G10.3: the status line runs often, so status builds only its own parser."""
    top = _Parser(prog="pitboard")
    sub = top.add_subparsers(dest="command", parser_class=_Parser)
    p = sub.add_parser("status")
    _common(p)
    p.add_argument("--plain", action="store_true")
    return top


# ---------------------------------------------------------------- helpers

def _ask_id(text):
    t = (text or "").strip().upper()
    if not contract.ASK_ID.match(t):
        raise Fail(2, f"pitboard: not an ask ID: {text} (they look like A12)")
    return t


def _session_id():
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def _lane_name(key):
    sid = _session_id()
    if sid:
        row = lane.read_map().get(sid)
        if isinstance(row, dict) and row.get("lane") == key and row.get("lane_name"):
            return row["lane_name"]
    st = store.read_json(store.state_path(key))
    if isinstance(st, dict) and st.get("lane_name"):
        return st["lane_name"]
    return key


def _tmux(pane, fmt):
    import subprocess
    try:
        r = subprocess.run(["tmux", "display", "-p", "-t", pane, fmt], capture_output=True, text=True,
                           timeout=1)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def where():
    """G6.7: where the ask was made; values failing the G1.3 pattern are dropped."""
    import socket
    w = {"host": socket.gethostname().split(".")[0]}
    try:
        w["cwd"] = os.getcwd()
    except OSError:
        pass
    pane = os.environ.get("TMUX_PANE")
    if pane:
        w["tmux_pane"] = pane
        w["tmux_session"] = _tmux(pane, "#{session_name}")
        w["tmux_window"] = _tmux(pane, "#{window_name}")
    return contract.clean_where(w)


def _deadline(text, cfg):
    if text is None:
        return None
    try:
        return timefmt.parse_deadline(text, timefmt.zone(cfg["display_tz"]))
    except timefmt.DeadlineError as e:
        raise Fail(6, f"pitboard: {e}")


class _Ctx:
    """The lane a command writes to. Hooks pass key, name and session_id from their input."""

    def __init__(self, args=None, key=None, name=None, session_id=None, cfg=None,
                 lock_timeout=store.LOCK_WAIT_COMMAND):
        self.cfg = cfg or store.config()
        self.lock_timeout = lock_timeout
        if key:
            self.key = key
        else:
            try:
                self.key = lane.find(getattr(args, "lane", None))
            except lane.NoLane as e:
                raise Fail(3, str(e))
        self.name = name or _lane_name(self.key)
        self.session_id = session_id if key else _session_id()

    def event(self, etype, target, by, data):
        return contract.make_event(etype, uid=target["uid"], ask=target["ask"], lane=self.key,
                                   lane_name=self.name, machine=self.cfg["machine"],
                                   session_id=self.session_id, by=by, data=data)


def _target(view, ask_id, allowed, action):
    a = view.find(ask_id)
    if a is None:
        if not view.full:
            raise _NeedFull()
        raise Fail(4, f"pitboard: {ask_id} not found in this lane")
    if a["status"] not in allowed:
        raise Fail(5, f"pitboard: {ask_id} is {a['status']}; {action} needs it {' or '.join(allowed)}")
    return a


def _write(ctx, build, full=False):
    """store.append with the G6.3 exit codes; retries with every ask when a target is closed."""
    try:
        try:
            return store.append(ctx.key, build, mode="refuse", cfg=ctx.cfg, full=full,
                                lock_timeout=ctx.lock_timeout)
        except _NeedFull:
            return store.append(ctx.key, build, mode="refuse", cfg=ctx.cfg, full=True,
                                lock_timeout=ctx.lock_timeout)
    except contract.ContractError as e:
        raise Fail(6, f"pitboard: {e}")
    except store.LaneBusy:
        raise Fail(7, f"pitboard: lane busy: {ctx.key} (try again)")


def _asks_of(state, ids):
    by_id = {a["ask"]: a for a in state["asks"]}
    return [by_id[i] for i in ids if i in by_id]


def _can_answer(a, by, ask_id):
    """G1.11: an answered ask takes a new answer only from the operator over an agent's answer."""
    if a["status"] == "answered" and not (by == "operator" and a.get("answered_by") == "agent"):
        raise Fail(5, f"pitboard: {ask_id} is answered (by {a.get('answered_by')}); "
                      "only the operator can replace an agent's answer")


# ---------------------------------------------------------------- write commands

def cmd_add(args):
    ctx = _Ctx(args)
    if args.kind == "hand" and not args.steps:
        raise Fail(6, "pitboard: --kind hand needs at least one --step")
    if args.kind in ("question", "decision") and not args.suggested:
        raise Fail(6, f"pitboard: --kind {args.kind} needs --suggested (the answer you recommend)")
    data = {"kind": args.kind, "severity": args.severity, "title": args.title, "source": "agent",
            "where": where()}
    for k in ("suggested", "why", "detail", "steps"):
        if getattr(args, k) is not None:
            data[k] = getattr(args, k)
    deadline = _deadline(args.deadline, ctx.cfg)
    if deadline:
        data["deadline"] = deadline

    def build(view):
        return contract.make_event("asked", uid=contract.new_id(), ask=view.next_ask_id(), lane=ctx.key,
                                   lane_name=ctx.name, machine=ctx.cfg["machine"],
                                   session_id=ctx.session_id, by="agent", data=data)
    written, state = _write(ctx, build)
    ev = written[0]
    ask = _asks_of(state, [ev["ask"]])
    f = flags.flag(ask[0], escalate_after_hours=ctx.cfg["escalate_after_hours"],
                   urgent_deadline_hours=ctx.cfg["urgent_deadline_hours"]) if ask else flags.RED
    msg = f'{ev["ask"]} recorded ({flags.word(f)}). Ask it in chat as: "{ev["ask"]}: {ev["data"]["title"]}"'
    return Out(msg, [ev["ask"]], ask)


UPDATER_FLAGS = ("--check", "--now", "--pin", "--unpin")
NOT_SELF_UPDATE = "pitboard: update changes an ask: update A12 --title ... (Pit Board itself: self-update)"


def cmd_update(args):
    if args.id is None or any(getattr(args, f[2:]) is not None for f in UPDATER_FLAGS):
        raise Fail(2, NOT_SELF_UPDATE)                # G6.2: one meaning, never updates Pit Board
    ctx = _Ctx(args)
    ask_id = _ask_id(args.id)
    data = {k: getattr(args, k) for k in ("severity", "title", "suggested", "why", "detail", "steps")
            if getattr(args, k) is not None}
    if args.deadline is not None:
        data["deadline"] = _deadline(args.deadline, ctx.cfg)
    if not data:
        raise Fail(2, "pitboard: update needs at least one field (--title, --severity, ...)")

    def build(view):
        a = _target(view, ask_id, ("open", "answered"), "update")
        return ctx.event("updated", a, "agent", data)
    _, state = _write(ctx, build)
    return Out(f"{ask_id} updated.", [ask_id], _asks_of(state, [ask_id]))


def cmd_answer(args):
    ctx = _Ctx(args)
    ask_id = _ask_id(args.id)

    def build(view):
        a = _target(view, ask_id, ("open", "answered"), "answer")
        _can_answer(a, args.by, ask_id)
        return ctx.event("answered", a, args.by, {"answer": args.answer, "via": "text"})
    _, state = _write(ctx, build)
    return Out(f"{ask_id} answered.", [ask_id], _asks_of(state, [ask_id]))


def _ids(raw):
    out = []
    for r in raw:
        i = _ask_id(r)
        if i not in out:
            out.append(i)
    return out


def cmd_ok(args):
    ctx = _Ctx(args)
    picked, skipped, state = approve(ctx, args.ids)
    parts = [f"Approved: {', '.join(picked)}." if picked else "Nothing approved."]
    if skipped:
        parts.append(f"Skipped (no suggested answer): {', '.join(skipped)}.")
    return Out(" ".join(parts), picked, _asks_of(state, picked), {"skipped": skipped})


def approve(ctx, raw_ids):
    """The ok logic (G6.2), shared with the UserPromptSubmit hook (G7.2 step 2).
    Returns (approved IDs, skipped IDs, state)."""
    every = [r.lower() for r in raw_ids] == ["all"]
    ids = [] if every else _ids(raw_ids)
    picked, skipped = [], []

    def build(view):
        picked.clear()
        skipped.clear()
        targets = (sorted((a for a in view.asks.values() if a["status"] == "open"),
                          key=lambda a: contract.ask_number(a["ask"]))
                   if every else [_target(view, i, ("open", "answered"), "ok") for i in ids])
        events = []
        for a in targets:
            if not a.get("suggested"):
                skipped.append(a["ask"])
                continue
            _can_answer(a, "operator", a["ask"])
            picked.append(a["ask"])
            events.append(ctx.event("answered", a, "operator", {"answer": a["suggested"], "via": "ok"}))
        return events
    _, state = _write(ctx, build)
    return list(picked), list(skipped), state


def cmd_no(args):
    ctx = _Ctx(args)
    ids, state = decline(ctx, args.ids)
    return Out(f"Declined: {', '.join(ids)}.", ids, _asks_of(state, ids))


def decline(ctx, raw_ids):
    """The no logic (G6.2), shared with the UserPromptSubmit hook (G7.2 step 3)."""
    ids = _ids(raw_ids)

    def build(view):
        events = []
        for i in ids:
            a = _target(view, i, ("open", "answered"), "no")
            _can_answer(a, "operator", i)
            events.append(ctx.event("answered", a, "operator", {"answer": "No.", "via": "no"}))
        return events
    _, state = _write(ctx, build)
    return ids, state


def _close(etype, word, allowed, data_of):
    def cmd(args):
        ctx = _Ctx(args)
        ask_id = _ask_id(args.id)

        def build(view):
            a = _target(view, ask_id, allowed, args.command)
            return ctx.event(etype, a, "agent", data_of(args))
        _, state = _write(ctx, build, full=(etype == "reopened"))
        asks = _asks_of(state, [ask_id])
        return Out(f"{ask_id} {word}.", [ask_id], asks)
    return cmd


cmd_done = _close("done", "done", ("open", "answered"), lambda a: {"note": a.note})
cmd_withdraw = _close("withdrawn", "withdrawn", ("open", "answered"), lambda a: {"reason": a.reason})
cmd_reopen = _close("reopened", "reopened", ("answered", "done", "withdrawn"), lambda a: {"reason": a.reason})


# ---------------------------------------------------------------- read commands

def _events_of(key, uid):
    events, _ = store.read_log(key)
    seen, out = set(), []
    for e in sorted((e for e in events if contract.is_valid(e) and e["uid"] == uid),
                    key=lambda e: (e["ts"], e["event_id"])):
        if e["event_id"] not in seen:
            seen.add(e["event_id"])
            out.append(e)
    return out


def _lane_asks(ctx, every):
    if every:
        return sorted(store.all_asks(ctx.key).values(), key=lambda a: contract.ask_number(a["ask"]))
    try:
        st = store.read_state(ctx.key, ctx.cfg)
    except store.LaneBusy:
        raise Fail(7, f"pitboard: lane busy: {ctx.key} (try again)")
    return [a for a in st["asks"] if a["status"] == "open"]


def cmd_list(args):
    ctx = _Ctx(args)
    asks = _lane_asks(ctx, args.all)
    text = render.list_lines(asks, timefmt.zone(ctx.cfg["display_tz"]), width=render.width_of(),
                             plain=render.plain_wanted(), order=args.sort, cfg=ctx.cfg)
    out = Out(text, [a["ask"] for a in asks], asks)
    out.raw = True  # render cut it to the terminal width already
    return out


def cmd_board(args):
    ctx = _Ctx(args)
    if args.limit < 0:
        raise Fail(2, "pitboard: --limit must be 0 (all) or more")
    tz = timefmt.zone(ctx.cfg["display_tz"])
    width, plain = render.width_of(args.width), render.plain_wanted(args.plain)
    asks = _lane_asks(ctx, args.all)
    if args.all:
        text = render.board_history(asks, ctx.name, tz, width=width, plain=plain, limit=args.limit, cfg=ctx.cfg)
    else:
        text = render.board_open(asks, ctx.name, tz, width=width, plain=plain, cfg=ctx.cfg)
    out = Out(text, [a["ask"] for a in asks], asks)
    out.raw = True
    return out


STATUSLINE_SEEN_SECONDS = 60


def _status_input(stdin):
    try:
        if stdin is None or stdin.isatty():
            return {}
        obj = json.loads(stdin.read() or "{}")
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


SEG_MARK = "pitboard-seg 1"
SEG_KEEP_DAYS = 7
_SEG_SID = re.compile(r"[a-z0-9-]{1,64}")


def segment_path(sid):
    return os.path.join(store.home(), "state", sid + ".seg")


def _keep_segment(t0_ns, sid, key, segment, until, plain):
    """P54: the finished segment for the status line wrapper to show without starting Python. Kept only when the
    wrapper handed over the session id and session name it found in the input (PITBOARD_WRAPPER_SID and
    PITBOARD_WRAPPER_NAME; the file stores exactly that name, so one text decides) and its id is this session's. It
    holds the version that wrote it, the time its text stays true until, the moment the launcher started, NO_COLOR as
    the wrapper reads it, and every file whose change can change the segment, each with whether it was there. Its
    own file time is the moment the launcher started, before it read anything: a file changed after that is newer, and
    the wrapper runs Pit Board again, so a count read before a change is never shown after it. It holds the count and
    the age the segment shows, never an ask's words."""
    envb = getattr(os, "environb", None)                # the name's bytes as the shell had them, whatever the locale
    if envb is None or os.environ.get("PITBOARD_WRAPPER_SID") != sid or b"PITBOARD_WRAPPER_NAME" not in envb:
        return
    name = envb[b"PITBOARD_WRAPPER_NAME"]
    if until is None or not _SEG_SID.fullmatch(sid or ""):
        return
    h = store.home()
    deps = [lane.map_path(), os.path.join(h, "config.json"), store.log_path(key),
            os.path.join(launch._claude_dir(), "plugins", "installed_plugins.json"),
            os.path.join(h, "update"), os.path.join(h, "pitboard", "launch.py"), os.path.join(h, "bin", "pitboard")]
    lines = [f"{SEG_MARK} {__version__} {until} {t0_ns // 10**9} {1 if plain else 0} {len(deps)}".encode(), name,
             segment.encode("utf-8")]
    lines += [(b"+ " if os.path.exists(d) else b"- ") + os.fsencode(d) for d in deps]
    if any(b"\n" in x or b"\r" in x for x in lines):
        return
    from . import leave
    path = segment_path(sid)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    leave.write_new(tmp, b"\n".join(lines) + b"\n", 0o600)
    os.utime(tmp, ns=(t0_ns, t0_ns))                  # set before the rename: never seen newer than the read
    os.replace(tmp, path)
    _prune_segments(os.path.dirname(path), t0_ns)


def _prune_segments(folder, now_ns):
    """P54: a session's segment file goes when another version wrote it, or when it is older than SEG_KEEP_DAYS (its
    session is long over; if it is not, the next redraw writes it again). So the folder holds about one small file per
    session of the last week. Only files of the name and first line Pit Board gives them (rule 23); one that cannot be
    read stays."""
    cut = now_ns - SEG_KEEP_DAYS * 86400 * 10**9
    for n in os.listdir(folder):
        if not n.endswith(".seg") or not _SEG_SID.fullmatch(n[:-4]):
            continue
        p = os.path.join(folder, n)
        try:
            if os.path.islink(p):
                continue
            with open(p, encoding="utf-8", errors="replace") as f:
                first = f.readline()
            if not first.startswith(SEG_MARK + " "):
                continue                              # not ours by its first line: never removed
            if os.lstat(p).st_mtime_ns >= cut and first.split(" ")[2:3] == [__version__]:
                continue
            os.unlink(p)
        except OSError:
            continue


def _launch_ns():
    """P54: when the launcher started, from its own marker; None from a launcher before 0.1.3 (no file is kept)."""
    v = os.environ.get("PITBOARD_LAUNCH_NS") or ""
    return int(v) if v.isdigit() and int(v) <= time.time_ns() else None


def _note_session_name(sid, name, row):
    """G10.6: session_name sets lane_name only, at most once a minute per session. Returns None when nothing is left to
    note, else the time (seconds since 1970) the name is due to be noted (P54: the kept segment ends then)."""
    if not name or not isinstance(name, str) or row.get("lane_name") == name:
        return None
    seen_path = os.path.join(store.home(), "state", "statusline-seen.json")
    seen = store.read_json(seen_path, {})
    seen = seen if isinstance(seen, dict) else {}
    now = contract.now_ts()
    last = seen.get(sid)
    if isinstance(last, str) and contract.TS.match(last):
        if (contract.parse_ts(now) - contract.parse_ts(last)).total_seconds() < STATUSLINE_SEEN_SECONDS:
            return int(contract.parse_ts(last).timestamp()) + STATUSLINE_SEEN_SECONDS
    lane.resolve(sid, name.strip()[: contract.LANE_NAME_MAX], lock_timeout=0.05)
    seen[sid] = now
    os.makedirs(os.path.dirname(seen_path), exist_ok=True)
    store.write_json_atomic(seen_path, seen)
    return None


def cmd_status(args, stdin=None):
    """G10: one line, no newline, nothing when nothing is open; never fails loudly (G10.4)."""
    out = Out("")
    out.raw, out.nonl = True, True
    try:
        t0 = _launch_ns()
        inp = _status_input(sys.stdin if stdin is None else stdin)
        sid = inp.get("session_id") if isinstance(inp.get("session_id"), str) else None
        key, mapped = None, False
        if sid and not args.lane:
            row = lane.read_map().get(sid)
            if isinstance(row, dict) and contract.LANE_KEY.match(str(row.get("lane", ""))):
                key, mapped, name_due = row["lane"], True, None
                try:
                    name_due = _note_session_name(sid, inp.get("session_name"), row)
                except Exception:  # noqa: BLE001 - the segment still prints; no segment is kept
                    mapped = False
        if key is None:
            try:
                key = lane.find(args.lane)
            except lane.NoLane:
                return out
        cfg = store.config()
        st = store.read_state(key, cfg, lock_timeout=0.05)
        now = datetime.now(timezone.utc)
        plain = render.plain_wanted(args.plain)
        out.message = render.status_segment(st, now=now, plain=plain, cfg=cfg)
        out.asks = [a for a in st["asks"] if a["status"] == "open"]
        out.ids = [a["ask"] for a in out.asks]
        if mapped and t0 is not None and not args.plain:
            try:
                until = render.segment_until(st, now, cfg)
                if until is not None and name_due is not None:
                    until = min(until, name_due)          # a rename waiting for its minute is noted when it is due
                _keep_segment(t0, sid, key, out.message, until, plain)
            except Exception:  # noqa: BLE001 - the segment still prints; the next redraw runs Pit Board again
                pass
    except Exception:  # noqa: BLE001
        out.message, out.ids, out.asks = "", [], []
    return out


def cmd_setup(args):
    """G18.1: a numbered plan; nothing changes without --apply. Milestone 1 has --minimal only."""
    from . import leave, setup as setup_mod
    if not (args.folder and args.undo):                       # P40: a home for Pit Board alone, before any write
        h = store.home()
        why = "it is your home folder" if leave.is_home_folder(h) else (
            "it holds things that are not Pit Board's: " + leave.foreign_text(leave.foreign(h)) if leave.foreign(h) else "")
        if why:                                               # short lines: the reason is never cut off
            raise Fail(2, "pitboard: setup refused: Pit Board's home is not a folder for Pit Board alone.\n"
                          f"  why: {why}\n  home: {leave._short(h)}\n"
                          "Unset PITBOARD_HOME, or set it to a new, empty folder. Nothing changed.")
    if args.folder:
        return _setup_folder(args)
    if args.undo:
        raise Fail(2, "pitboard: setup --undo goes with --folder DIR")
    if not args.minimal:
        raise Fail(2, "pitboard: this release has setup --minimal only (config, stable launcher, "
                      "status line); the full setup comes in 0.2.0")
    try:
        items = setup_mod.plan_minimal()
    except (OSError, ValueError) as e:
        raise Fail(6, f"pitboard: setup: {e}")
    applied = None
    if args.apply:
        _make_home(setup_mod)
        applied = setup_mod.apply(items)
    return Out(setup_mod.describe(items, applied), data={"items": [i.as_dict() for i in items],
                                                         "applied": args.apply})


def _make_home(setup_mod):
    """P48 (the family's rules 23 and 8): setup records that it made the home, before its first write in it, so the
    leave takes away only a home Pit Board made; a folder that was there before setup is the person's."""
    fresh = not os.path.lexists(store.home())
    h = store.ensure_home()
    if fresh:
        setup_mod.note(h, made_home=True)
    return h


def _setup_folder(args):
    """G18.1 folder mode: plan (default), --apply, or --undo, for one folder."""
    from . import folder as folder_mod
    plugin = args.plugin or folder_mod.PLUGIN           # --undo with --folder: main() hands it to uninstall
    try:
        if args.apply:
            from . import setup as setup_mod
            _make_home(setup_mod)
            lines = folder_mod.apply(args.folder, plugin=plugin)
        else:
            lines = folder_mod.plan(args.folder, plugin=plugin) + ["Nothing changed. Run again with --apply to do it."]
    except folder_mod.Refused as e:
        raise Fail(2, f"pitboard: setup --folder refused:\n{e}")
    except (OSError, ValueError, RuntimeError) as e:
        raise Fail(6, f"pitboard: setup --folder: {e}")
    return Out("\n".join(lines), data={"folder": args.folder, "applied": bool(args.apply), "undo": bool(args.undo)})


def cmd_hook(args, stdin=None):
    """G7: one JSON object or nothing on stdout; always exit 0 (INV6)."""
    from . import hooks
    out = Out("")
    out.raw, out.nonl = True, True
    try:
        raw = (sys.stdin if stdin is None else stdin).read()
        obj = hooks.handle(args.event, raw)
        if obj is not None:
            out.message = json.dumps(obj, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        out.message = ""
    return out


def cmd_show(args):
    ctx = _Ctx(args)
    ask_id = _ask_id(args.id)
    a = next((x for x in store.all_asks(ctx.key).values() if x["ask"] == ask_id), None)
    if a is None:
        raise Fail(4, f"pitboard: {ask_id} not found in this lane")
    tz = timefmt.zone(ctx.cfg["display_tz"])
    events = _events_of(ctx.key, a["uid"])
    lines = []
    for k, v in a.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, str) and contract.TS.match(v):
            v = timefmt.show(v, tz)
        elif isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        lines.append(f"{k}: {v}")
    lines.append("events:")
    for e in events:
        lines.append(f"  {timefmt.show(e['ts'], tz)}  {e['type']} by {e['by']}  "
                     f"{json.dumps(e['data'], ensure_ascii=False)}")
    return Out("\n".join(lines), [ask_id], [a], {"events": events})


def cmd_lane(args):
    ctx = _Ctx(args)
    return Out(f"{ctx.key} ({ctx.name})", [], [], {"lane": ctx.key, "lane_name": ctx.name})


CSV_COLUMNS = ("lane", "lane_name", "machine", "ask", "uid", "status", "kind", "severity", "title",
               "suggested", "steps", "deadline", "detail", "why", "asked_at", "answered_at", "answer",
               "answered_by", "answered_via", "done_at", "done_note", "withdrawn_at", "withdrawn_reason",
               "updated_at", "source", "where", "session_id", "events")


def cmd_export(args):
    keys = store.lane_keys() if args.all_lanes else [_Ctx(args).key]
    if args.format == "jsonl":
        events = []
        for k in keys:
            events += [e for e in store.read_log(k)[0] if contract.is_valid(e)]
        return _raw("".join(contract.serialize(e).decode("utf-8") for e in events), data={"events": events})
    import csv
    import io
    asks = []
    for k in keys:
        asks += sorted(store.all_asks(k).values(), key=lambda a: contract.ask_number(a["ask"]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for a in asks:
        w.writerow([json.dumps(a.get(c), ensure_ascii=False) if isinstance(a.get(c), (list, dict))
                    else ("" if a.get(c) is None else a.get(c)) for c in CSV_COLUMNS])
    return _raw(buf.getvalue(), asks=asks)


def _raw(text, asks=None, data=None):
    out = Out(text, [], asks, data)
    out.raw = True  # printed as is: G6.8 does not cut exported data
    return out


def _generation(root):
    try:
        with open(os.path.join(root, "hooks", "generation.json"), encoding="utf-8") as f:
            g = json.load(f)
        return g if isinstance(g, int) else None
    except (OSError, ValueError):
        return None


def cmd_version(args):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    installed = [v for _, v in launch._installed(launch._claude_dir()) if launch._vkey(v)]
    newest = max(installed, key=launch._vkey) if installed else None
    pin = (launch._lines(os.path.join(store.home(), "update", "pin")) or [None])[0]
    gen = _generation(root)
    data = {"running": __version__, "installed": newest, "pinned": pin, "generation": gen}
    parts = [f"installed {newest or 'none'}"]
    if pin:
        parts.append(f"pinned {pin}")
    parts.append(f"hooks gen {gen if gen is not None else '?'}")
    try:                                         # the refresh's own check runs `version`: this line never fails it
        copy = _copy_line(store.home(), pin)
    except Exception:  # noqa: BLE001
        copy = None
    status = _status_line(store.home())
    return Out(f"{__version__} ({', '.join(parts)})" + (f"\n{copy}" if copy else "")
               + "".join(f"\n{ln}" for ln in _open_lines(store.home())) + f"\n{status}", data=data)  # P15: status last


def _open_lines(home):
    """P41: said again while it stays open: a folder on the way (with its command), Pit Board's own entries."""
    from . import setup as setup_mod
    try:
        lines = [ln for w, m, why, fix in setup_mod.way_open(home, setup_mod.claude_settings_path())
                 for ln in [f"open to other accounts: {w}" + (f" ({m:o})" if m else ""), f"  {why}"] + ([f"  to close it: {fix}"] if fix else [])]
        own = setup_mod.own_open(home)
    except Exception:  # noqa: BLE001                  # never fails `version`
        return []
    from . import leave                                      # P49 (rule 7): a line run exactly as printed works
    copy = leave._shell(os.path.join(home, "bin", "pitboard"))
    return lines + ([f"Pit Board's own, open to other accounts: {len(own)}",          # short lines: never cut
                     f"  to close them: {copy} setup --minimal --apply"] if own else [])


def _status_line(home):
    """P15 (plan 1.25): what the status line runs. It calls the home's launcher copy, which writes no log line, so
    this asks that copy's own choose() which folder it picks now and by which G21.4 step. Never fails `version`."""
    path = os.path.join(home, "pitboard", "launch.py")
    if not os.path.isfile(path):
        return "status line runs: no launcher copy in this home"
    try:
        spec = importlib.util.spec_from_file_location("_pitboard_home_launch_copy", path)
        copy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(copy)
        root, step = copy.choose(home=home, own_root=home)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - an old or broken copy
        return f"status line runs: unknown ({type(e).__name__})"
    if root is None:
        return "status line runs nothing: the launcher copy finds no installed version"
    try:
        with open(os.path.join(root, "pitboard", "__init__.py"), encoding="utf-8") as f:
            m = re.search(r'^__version__ = "([^"]*)"$', f.read(), re.M)
    except OSError:
        m = None
    return f"status line runs {m.group(1) if m else '?'} (step {step})"


def _copy_line(home, pin):
    """G6.2 (plan 1.19): the second version line, when the home's launcher copy came from a version older than
    the newest installed one that is not bad, and no pin holds the home (in either case no start refreshes it)."""
    if pin or not all(os.path.isfile(os.path.join(home, rel)) for rel, _ in stablecopy.LAUNCHER):
        return None
    bad = set(launch._lines(os.path.join(home, "update", "bad-versions")))
    good = [v for _, v in launch._installed(launch._claude_dir()) if launch._vkey(v) and v not in bad]
    newest = max(good, key=launch._vkey) if good else None
    if newest is None or launch._vkey(newest) < (0, 1, 2):      # no release before 0.1.2 refreshes a copy
        return None
    was = stablecopy.copied_from(home)
    if was is not None and launch._vkey(was) >= launch._vkey(newest):
        return None
    how = ("self_update is off, so no start refreshes it" if store.config().get("self_update") is False
           else "the next session start refreshes it")
    return f"launcher copy from {was or 'before-0.1.2'}; {how}"


def _write_whole(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    from . import leave                                  # P41: opened new at its mode
    leave.write_atomic(path, text, 0o600)


def cmd_self_update(args):
    """G21.10, before the rest of the updater (P10): --pin VER holds this home on a version, --unpin releases it.
    The status line and the hooks follow at their next call (G21.4 step 1)."""
    if args.check or args.now or not (args.pin or args.unpin):
        raise Fail(2, "pitboard: the updater itself comes in 0.2.0 (G21.3); self-update has only --pin VER and --unpin")
    pin_path = os.path.join(store.home(), "update", "pin")
    if args.unpin:
        if os.path.exists(pin_path):
            os.remove(pin_path)
        return cmd_version(args)
    ver = args.pin.strip()
    if not launch._vkey(ver):
        raise Fail(2, f"pitboard: not a version: {args.pin} (they look like 0.1.2). Nothing changed.")
    if ver in launch._lines(os.path.join(store.home(), "update", "bad-versions")):
        raise Fail(2, f"pitboard: {ver} is in update/bad-versions, so it is not pinned. Nothing changed.")
    if not launch._runnable(launch._cached(launch._claude_dir()).get(ver)):
        raise Fail(2, f"pitboard: no runnable {ver} in the plugin cache, so it is not pinned. Nothing changed.")
    _write_whole(pin_path, ver + "\n")
    return cmd_version(args)


COMMANDS = {"add": cmd_add, "update": cmd_update, "answer": cmd_answer, "ok": cmd_ok, "no": cmd_no,
            "done": cmd_done, "withdraw": cmd_withdraw, "reopen": cmd_reopen, "list": cmd_list,
            "board": cmd_board, "status": cmd_status, "setup": cmd_setup, "hook": cmd_hook, "show": cmd_show,
            "lane": cmd_lane, "export": cmd_export, "version": cmd_version,
            "self-update": cmd_self_update}


# ---------------------------------------------------------------- main

def _emit(out, as_json, code, stdout, stderr):
    if as_json:
        stdout.write(json.dumps({"ok": code == 0, "exit": code, "message": out.message, "ids": out.ids,
                                 "asks": out.asks, "data": out.data}, ensure_ascii=False) + "\n")
        return
    if not out.message:
        return
    text = out.message if getattr(out, "raw", False) else fit(out.message)
    if not getattr(out, "nonl", False) and not text.endswith("\n"):
        text += "\n"
    (stdout if code == 0 else stderr).write(text)


def main(argv=None, stdout=None, stderr=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    refusal = launch.floor_refusal(argv)               # G21.15: also first here, for a launcher copy before 0.1.3
    if refusal:
        return launch.floor_stop(refusal, stdout, stderr)
    if argv[:1] == ["uninstall"]:                      # G18.3: the one way of leaving, also for a launcher copy
        from . import leave                            # from before 0.1.3, which calls cli.main() for every command
        return leave.main(argv[1:], stdout=stdout, stderr=stderr)
    if argv[:1] == ["setup"] and "--undo" in argv:     # G18.3 point 1: the old spelling, for 0.1.3 only
        try:
            a = parser().parse_args(argv)
        except SystemExit as e:
            return int(e.code or 0)
        if a.folder:
            from . import leave
            stderr.write("pitboard: `setup --folder DIR --undo` is the old spelling of `pitboard uninstall --folder "
                         "DIR --apply`; it does the same, and goes after 0.1.3.\n")
            return leave.main(["--folder", a.folder, "--apply"] + (["--json"] if a.json else []), stdout=stdout,
                              stderr=stderr)
    as_json = "--json" in argv
    if argv[:1] == ["hook"]:
        try:
            args = parser().parse_args(argv)
            out = cmd_hook(args)
            if out.message:
                stdout.write(out.message)
        except BaseException:  # noqa: BLE001 - INV6: a hook never fails loudly
            pass
        return 0
    try:
        try:
            args = (_status_parser() if argv[:1] == ["status"] else parser()).parse_args(argv)
        except SystemExit as e:  # --help
            return int(e.code or 0)
        out = COMMANDS[args.command](args)
        code = out.code
    except Fail as e:
        out, code = Out(str(e)), e.code
    except Exception as e:  # noqa: BLE001 - G6.3 exit 1, one line, no traceback
        out, code = Out(f"pitboard: unexpected error: {type(e).__name__}: {e}"), 1
    _emit(out, as_json, code, stdout, stderr)
    return code
