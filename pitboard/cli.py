"""The pitboard command (plan G6): argument parsing and dispatch.

Exit codes (G6.3): 0 ok, 1 unexpected error, 2 bad usage, 3 lane unknown, 4 ask not found,
5 transition not allowed, 6 invalid field, 7 lane busy, 8 hub unreachable, 9 update failed.
Standard library only.
"""
import argparse
import csv
import io
import json
import os
import socket
import subprocess
import sys

from . import __version__, contract, flags, lane, launch, store, timefmt

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

    p = sub.add_parser("update", help="change an open ask")
    _common(p)
    p.add_argument("id")
    p.add_argument("--title")
    _fields(p, kind=False)

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
    try:
        r = subprocess.run(["tmux", "display", "-p", "-t", pane, fmt], capture_output=True, text=True,
                           timeout=1)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def where():
    """G6.7: where the ask was made; values failing the G1.3 pattern are dropped."""
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
    def __init__(self, args):
        self.cfg = store.config()
        try:
            self.key = lane.find(getattr(args, "lane", None))
        except lane.NoLane as e:
            raise Fail(3, str(e))
        self.name = _lane_name(self.key)

    def event(self, etype, target, by, data):
        return contract.make_event(etype, uid=target["uid"], ask=target["ask"], lane=self.key,
                                   lane_name=self.name, machine=self.cfg["machine"],
                                   session_id=_session_id(), by=by, data=data)


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
            return store.append(ctx.key, build, mode="refuse", cfg=ctx.cfg, full=full)
        except _NeedFull:
            return store.append(ctx.key, build, mode="refuse", cfg=ctx.cfg, full=True)
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
                                   session_id=_session_id(), by="agent", data=data)
    written, state = _write(ctx, build)
    ev = written[0]
    ask = _asks_of(state, [ev["ask"]])
    f = flags.flag(ask[0], escalate_after_hours=ctx.cfg["escalate_after_hours"],
                   urgent_deadline_hours=ctx.cfg["urgent_deadline_hours"]) if ask else flags.RED
    msg = f'{ev["ask"]} recorded ({flags.word(f)}). Ask it in chat as: "{ev["ask"]}: {ev["data"]["title"]}"'
    return Out(msg, [ev["ask"]], ask)


def cmd_update(args):
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
    every = [r.lower() for r in args.ids] == ["all"]
    ids = [] if every else _ids(args.ids)
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
    parts = [f"Approved: {', '.join(picked)}." if picked else "Nothing approved."]
    if skipped:
        parts.append(f"Skipped (no suggested answer): {', '.join(skipped)}.")
    return Out(" ".join(parts), picked, _asks_of(state, picked), {"skipped": skipped})


def cmd_no(args):
    ctx = _Ctx(args)
    ids = _ids(args.ids)

    def build(view):
        events = []
        for i in ids:
            a = _target(view, i, ("open", "answered"), "no")
            _can_answer(a, "operator", i)
            events.append(ctx.event("answered", a, "operator", {"answer": "No.", "via": "no"}))
        return events
    _, state = _write(ctx, build)
    return Out(f"Declined: {', '.join(ids)}.", ids, _asks_of(state, ids))


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
    return Out(f"{__version__} ({', '.join(parts)})", data=data)


COMMANDS = {"add": cmd_add, "update": cmd_update, "answer": cmd_answer, "ok": cmd_ok, "no": cmd_no,
            "done": cmd_done, "withdraw": cmd_withdraw, "reopen": cmd_reopen, "show": cmd_show,
            "lane": cmd_lane, "export": cmd_export, "version": cmd_version}


# ---------------------------------------------------------------- main

def _emit(out, as_json, code, stdout, stderr):
    if as_json:
        stdout.write(json.dumps({"ok": code == 0, "exit": code, "message": out.message, "ids": out.ids,
                                 "asks": out.asks, "data": out.data}, ensure_ascii=False) + "\n")
        return
    if not out.message:
        return
    text = out.message if getattr(out, "raw", False) else fit(out.message)
    (stdout if code == 0 else stderr).write(text if text.endswith("\n") else text + "\n")


def main(argv=None, stdout=None, stderr=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    stdout, stderr = stdout or sys.stdout, stderr or sys.stderr
    as_json = "--json" in argv
    try:
        try:
            args = parser().parse_args(argv)
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
