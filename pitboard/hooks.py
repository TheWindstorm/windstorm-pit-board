"""Pit Board hooks (plan G7): `pitboard hook <name>` with the hook JSON on stdin.

Every handler is wrapped so that any exception means no output and exit 0 (INV6).
Each handler appends one line to logs/pitboard.log: time, hook name, lane key, what it
did (never ask text). Milestone 1 handles session-start (G7.1 steps 1 to 3),
user-prompt-submit (G7.2), stop (only the idle mark, G16.4) and cwd-changed (G7.8).
Standard library only.
"""
import json
import os
import re

from . import contract, lane, render, store, timefmt

BOARD_PROMPTS = {"pb": False, "pb all": True, "/board": False, "/board all": True}
APPROVE = re.compile(r"^\s*(ok|yes|approve|approved)\s+(all|(A\d+)([\s,]+A\d+)*)\s*[.!]?\s*$", re.I)
DECLINE = re.compile(r"^\s*(no|decline|declined)\s+(A\d+)([\s,]+A\d+)*\s*[.!]?\s*$", re.I)
ASK_IDS = re.compile(r"\bA([1-9][0-9]*)\b", re.I)
MENTION = re.compile(r"\bA[1-9][0-9]*\b")
STALE_SOURCES = ("permission", "question-box")


# ---------------------------------------------------------------- plumbing

def log(hook, key, what):
    """One line per handler run in logs/pitboard.log (no ask text)."""
    try:
        path = os.path.join(store.home(), "logs", "pitboard.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, f"{contract.now_ts()} {hook} {key or '-'} {what}\n".encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass


def _lane(inp, refresh=False):
    """(key, lane_name) for the hook's session: lanes.json, else first sight (G3.4)."""
    sid = inp.get("session_id")
    if not isinstance(sid, str) or not sid:
        return None, None
    row = lane.read_map().get(sid)
    if refresh or not (isinstance(row, dict) and contract.LANE_KEY.match(str(row.get("lane", "")))):
        name = lane.lane_name(inp.get("session_title"), inp.get("transcript_path"))
        row = lane.resolve(sid, name, lock_timeout=store.LOCK_WAIT_HOOK)
    return row["lane"], row.get("lane_name") or row["lane"]


def _ctx(key, name, sid, cfg):
    from . import cli
    return cli._Ctx(key=key, name=name, session_id=sid, cfg=cfg, lock_timeout=store.LOCK_WAIT_HOOK)


def env_line(key):
    return f"export PITBOARD_LANE={key}"


def add_env_line(key):
    """G7.1 step 2 / G7.8: append the export line to CLAUDE_ENV_FILE unless it is already there.
    Never overwrite the file: other plugins write to it too."""
    path = os.environ.get("CLAUDE_ENV_FILE")
    if not path:
        return "no env file"
    line = env_line(key)
    try:
        with open(path, encoding="utf-8") as f:
            if line in (ln.rstrip("\n") for ln in f):
                return "env line already there"
    except FileNotFoundError:
        pass
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return "env line added"


def mark_activity(key, word):
    """G16.4: state/<key>.activity = 'busy <ts>' or 'idle <ts>'."""
    path = os.path.join(store.home(), "state", key + ".activity")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"{word} {contract.now_ts()}\n")
    os.replace(tmp, path)


def _context(event, lines):
    if not lines:
        return None
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": "\n".join(lines)}}


# ---------------------------------------------------------------- G7.1 SessionStart

def session_start(inp, cfg):
    key, name = _lane(inp, refresh=True)
    if key is None:
        log("session-start", None, "no session id")
        return None
    env = add_env_line(key)
    try:
        st = store.read_state(key, cfg, lock_timeout=store.LOCK_WAIT_HOOK)
        asks = st["asks"]
    except store.LaneBusy:
        asks = []
    text = render.reminder_text(key, name, cfg["machine"], asks, timefmt.zone(cfg["display_tz"]), cfg=cfg)
    log("session-start", key, f"source={inp.get('source')} {env} reminder={sum(a['status'] == 'open' for a in asks)} open")
    return _context("SessionStart", [text])


# ---------------------------------------------------------------- G7.2 UserPromptSubmit

def _board(key, name, every, cfg):
    tz = timefmt.zone(cfg["display_tz"])
    plain = render.plain_wanted()
    if every:
        return render.board_history(list(store.all_asks(key).values()), name, tz, plain=plain, cfg=cfg)
    st = store.read_state(key, cfg, lock_timeout=store.LOCK_WAIT_HOOK)
    return render.board_open(st["asks"], name, tz, plain=plain, cfg=cfg)


def _close_stale(ctx, sid):
    """G7.2 step 5: this session's open permission and question-box asks are withdrawn."""
    def build(view):
        return [ctx.event("withdrawn", a, "hook", {"reason": "prompt closed"})
                for a in sorted(view.asks.values(), key=lambda a: contract.ask_number(a["ask"]))
                if a["status"] == "open" and a.get("source") in STALE_SOURCES and a.get("session_id") == sid]
    written, _ = store.append(ctx.key, build, mode="cut", cfg=ctx.cfg, lock_timeout=store.LOCK_WAIT_HOOK)
    return [e["ask"] for e in written]


def user_prompt_submit(inp, cfg):
    from . import cli
    key, name = _lane(inp)
    if key is None:
        log("user-prompt-submit", None, "no session id")
        return None
    prompt = inp.get("prompt") if isinstance(inp.get("prompt"), str) else ""
    sid = inp.get("session_id")

    every = BOARD_PROMPTS.get(prompt.strip().lower())
    if every is not None:                                                   # step 1
        log("user-prompt-submit", key, "board" + (" all" if every else ""))
        return {"decision": "block", "reason": _board(key, name, every, cfg),
                "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}}

    ctx = _ctx(key, name, sid, cfg)
    lines, did = [], []
    try:
        m = APPROVE.match(prompt)
        d = DECLINE.match(prompt) if not m else None
        if m:                                                               # step 2
            ids = ["all"] if m.group(2).lower() == "all" else ["A" + n for n in ASK_IDS.findall(m.group(2))]
            try:
                picked, _, state = cli.approve(ctx, ids)
            except cli.Fail as e:
                if e.code == 7:
                    raise store.LaneBusy(str(e))
                picked, state = [], None
            if picked:
                by = {a["ask"]: a for a in state["asks"]}
                said = "; ".join(f'{i}: "{by[i]["answer"]}"' for i in picked if i in by)
                lines.append(f"Pit Board: the operator approved {said}. Carry them out now. "
                             f"When each is finished, run: pitboard done <ID>.")
                did.append("approved " + ",".join(picked))
        elif d:                                                             # step 3
            ids = ["A" + n for n in ASK_IDS.findall(prompt)]
            try:
                done_ids, _ = cli.decline(ctx, ids)
            except cli.Fail as e:
                if e.code == 7:
                    raise store.LaneBusy(str(e))
                done_ids = []
            if done_ids:
                lines.append(f"Pit Board: the operator declined {', '.join(done_ids)}. Do not do them. "
                             "Ask what to do instead only if you are blocked.")
                did.append("declined " + ",".join(done_ids))

        st = store.read_state(key, cfg, lock_timeout=store.LOCK_WAIT_HOOK)    # step 4
        open_ids = {a["ask"] for a in st["asks"] if a["status"] == "open"}
        mentioned = []
        for i in MENTION.findall(prompt):
            if i in open_ids and i not in mentioned:
                mentioned.append(i)
        if mentioned:
            lines.append(f"Pit Board: this message answers or mentions {', '.join(mentioned)}. If it answers one, "
                         "run: pitboard answer <ID> --by operator --answer \"<the operator's answer in a few words>\".")
            did.append("mentions " + ",".join(mentioned))

        closed = _close_stale(ctx, sid)                                     # step 5
        if closed:
            did.append("closed " + ",".join(closed))
    except store.LaneBusy:
        log("user-prompt-submit", key, f"lane-busy user-prompt-submit {key}")
        mark_activity(key, "busy")
        return _context("UserPromptSubmit", lines)
    mark_activity(key, "busy")                                              # step 6
    log("user-prompt-submit", key, " ".join(did) or "nothing")
    return _context("UserPromptSubmit", lines)


# ---------------------------------------------------------------- G7.6 (M1 part) and G7.8

def stop(inp, cfg):
    """Milestone 1: only the idle mark (G16.4). The catcher and the rest of G7.6 come in M2."""
    key, _ = _lane(inp)
    if key is None:
        return None
    mark_activity(key, "idle")
    log("stop", key, "idle")
    return None


def cwd_changed(inp, cfg):
    key, _ = _lane(inp)
    if key is None:
        return None
    log("cwd-changed", key, add_env_line(key))
    return None


HANDLERS = {"session-start": session_start, "user-prompt-submit": user_prompt_submit, "stop": stop,
            "cwd-changed": cwd_changed}


def handle(name, raw):
    """Run one hook. Returns the JSON object to print, or None. Never raises (INV6)."""
    try:
        fn = HANDLERS.get(name)
        if fn is None:
            return None
        inp = json.loads(raw or "{}")
        if not isinstance(inp, dict):
            return None
        out = fn(inp, store.config())
        return out if isinstance(out, dict) else None
    except Exception as e:  # noqa: BLE001 - INV6
        try:
            log(name, None, f"error {type(e).__name__}")
        except Exception:  # noqa: BLE001
            pass
        return None
