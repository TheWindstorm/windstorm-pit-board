"""P99 (G18.1): the status line setting is one shell word. Claude Code hands statusLine.command to /bin/sh -c as it
stands (read on 2.1.331 and 2.1.332), so a home whose path holds a space, a dollar sign, a double quote or a backslash
must be written so that a shell still takes it as one path; setup reads the setting back that way before it says Done,
`pitboard version` makes the same read, and uninstall and a later setup still know the forms older versions wrote."""
import io
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest

from conftest import NO_CLAUDE_PATH
from pitboard import __version__, cli, leave, setup as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLANTED = {"a space": "pb home", "a percent sign": "pb%home%s", "a dollar sign": "pb$HOME$x", "a double quote": 'pb"home',
           "a backslash": "pb\\home"}
INPUT = b'{"session_id":"s-p99","cwd":"/"}'


@pytest.fixture
def made(monkeypatch, request):
    """A person's home and a Pit Board home whose own folder name holds the planted character, under a short folder:
    a printed step with a path in it is then not cut at the CLI's width (pytest's own paths are long)."""
    top = pathlib.Path(tempfile.mkdtemp(prefix="pb", dir="/tmp"))
    home, pb = top / "home", top / request.param
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "NO_COLOR"):
        monkeypatch.delenv(k, raising=False)
    os.chmod(home / ".claude", 0o755)
    old = os.umask(os.umask(0) | 0o022)
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"theme": "dark", "statusLine": {"type": "command", "command": "printf mine", "padding": 0}}))
    yield home, pb
    os.umask(old)
    shutil.rmtree(top)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    return cli.main(list(argv), stdout=out, stderr=err), out.getvalue(), err.getvalue()


def command(home):
    return json.loads((home / ".claude" / "settings.json").read_text())["statusLine"]["command"]


def as_claude_code_runs_it(cmd, home):
    """/bin/sh -c with the setting as one string and the status line's input on stdin."""
    return subprocess.run(["/bin/sh", "-c", cmd], input=INPUT, capture_output=True, timeout=30, cwd=str(home),
                          env={"PATH": os.environ["PATH"], "HOME": str(home)})


@pytest.mark.parametrize("made", list(PLANTED.values()), ids=list(PLANTED), indirect=True)
def test_G18_1_P99_the_status_line_setting_is_read_as_one_path_whatever_the_homes_path_holds(made):
    """Setup, then the setting run exactly as Claude Code runs it: the wrapper runs, and the person's own status line,
    which the wrapper carries on, is shown. One planted character at a time."""
    home, pb = made
    code, out, err = run("setup", "--minimal", "--apply")
    assert code == 0 and "Done: " in out, (out, err)
    r = as_claude_code_runs_it(command(home), home)
    assert r.returncode == 0 and r.stdout.decode().endswith("mine"), (command(home), r.returncode, r.stdout, r.stderr)
    assert S.reads_as(command(home), S.wrapper_path(str(pb))) is True       # setup's own read-back agrees with the shell
    code, out, _ = run("setup", "--minimal")                                # a second setup knows its own line
    assert "status line setting: " in out and "keep (already points at the wrapper)" in out, out
    code, out, _ = run("version")                                           # the same read: nothing to say
    assert code == 0 and "status line setting" not in out, out


def older(home, pb):
    """The setting as every version before 0.1.4 wrote it: the wrapper's full path as plain text."""
    p = home / ".claude" / "settings.json"
    d = json.loads(p.read_text())
    d["statusLine"]["command"] = S.wrapper_path(str(pb))
    p.write_text(json.dumps(d))


@pytest.mark.parametrize("made", ["pb home"], indirect=True)
def test_G18_1_P99_setup_says_done_only_after_it_read_the_setting_back(made, monkeypatch):
    """(b) Three answers. Read back as the wrapper's path: Done. Written in a form a shell does not take as one path
    (planted: the writer made to write the path plain): NOT done, exit 6. The file unreadable after the write
    (planted): could not be read back, exit 6, never Done."""
    home, pb = made
    monkeypatch.setattr(leave, "one_word", lambda path: path)               # the fault 0.1.3 had, planted
    monkeypatch.setattr(S, "plan_minimal", _no_guard(S.plan_minimal))
    with pytest.raises(cli.Fail) as e:
        cli.cmd_setup(_args(apply=True))
    assert e.value.code == 6 and "NOT done" in str(e.value) and "is not taken as the path" in str(e.value), str(e.value)
    assert "Done: " not in str(e.value)
    monkeypatch.undo()
    monkeypatch.setenv("HOME", str(home)); monkeypatch.setenv("PITBOARD_HOME", str(pb))
    monkeypatch.setattr(S, "read_back", lambda *a: None)                    # the read that could not be made
    older(home, pb)
    with pytest.raises(cli.Fail) as e:
        cli.cmd_setup(_args(apply=True))
    assert e.value.code == 6 and "could not be read back" in str(e.value) and "Done: " not in str(e.value)


def _args(apply=False):
    import argparse
    return argparse.Namespace(folder=None, undo=False, minimal=True, apply=apply, plugin=None, lane=None, json=False)


def _no_guard(plan):
    """plan_minimal with its own first check taken out, so that the planted writer's line reaches the file."""
    def planted(*a, **k):
        real = leave.reads_as
        leave.reads_as = lambda *x, **y: True
        try:
            return plan(*a, **k)
        finally:
            leave.reads_as = real
    return planted


@pytest.mark.parametrize("made", ["pb home"], indirect=True)
def test_G18_1_P99_an_older_setups_line_is_known_and_written_again_as_one_word(made):
    """(c) A home with a space that 0.1.3 set up: the setting is the plain path. version says it is not read as one
    path and prints the step; the step, run as printed, writes it as one word; uninstall knew it as its own before."""
    home, pb = made
    reg = home / ".claude" / "plugins" / "installed_plugins.json"           # the install, as Claude Code records it
    reg.parent.mkdir()
    reg.write_text(json.dumps({"version": 2, "plugins": {"windstorm-pit-board@thewindstorm": [
        {"scope": "user", "version": __version__, "installPath": ROOT}]}}))
    assert run("setup", "--minimal", "--apply")[0] == 0
    older(home, pb)
    assert as_claude_code_runs_it(command(home), home).returncode != 0      # the fault, as a person meets it
    code, out, _ = run("version")
    lines = out.splitlines()
    at = lines.index("status line setting: written by an older setup, and not read as one path here")
    step = lines[at + 1].split("to write it as one word: ", 1)[1]
    assert step.endswith(" setup --minimal --apply"), step
    code, out, _ = run("setup", "--minimal")
    assert "an older setup wrote it in a form that is not read as one path here" in out and "printf mine" not in out
    r = subprocess.run(["/bin/sh", "-c", step], capture_output=True, text=True, timeout=60, cwd=str(home),
                       env={"PATH": NO_CLAUDE_PATH, "HOME": str(home), "PITBOARD_HOME": str(pb),
                            "PITBOARD_MACHINE": "studio-1"})
    assert r.returncode == 0, (r.stdout, r.stderr)
    r = as_claude_code_runs_it(command(home), home)
    assert r.returncode == 0 and r.stdout.decode().endswith("mine"), (command(home), r.stdout, r.stderr)
    assert leave._original_from_wrapper(S.wrapper_path(str(pb))) == "printf mine"     # the person's own line, kept


# ---------------------------------------------------------------- (c) uninstall's three answers; the person's own words

@pytest.fixture
def lived(monkeypatch):
    """A person's home whose own path holds a space, Pit Board's home in its default place under it, set up by this
    version; the person's own status line command was there before."""
    top = pathlib.Path(tempfile.mkdtemp(prefix="pb", dir="/tmp"))
    home = top / "ho me"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PITBOARD_MACHINE", "studio-1")
    monkeypatch.setenv("PATH", NO_CLAUDE_PATH)
    for k in ("PITBOARD_HOME", "PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "NO_COLOR"):
        monkeypatch.delenv(k, raising=False)
    os.chmod(home / ".claude", 0o755)
    old = os.umask(os.umask(0) | 0o022)
    yield home, home / ".pitboard"
    os.umask(old)
    shutil.rmtree(top)


def own(home, cmd="printf mine"):
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"theme": "dark", "statusLine": {"type": "command", "command": cmd, "padding": 0}}))


def put(home, value):
    p = home / ".claude" / "settings.json"
    d = json.loads(p.read_text())
    d["statusLine"]["command"] = value
    p.write_text(json.dumps(d))
    return p.read_bytes()


def leave_run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = leave.main(list(argv), stdin=io.StringIO(""), stdout=out, stderr=err,
                      run=lambda args, **kw: subprocess.CompletedProcess(args, 0, "", ""))
    return code, out.getvalue() + err.getvalue()


@pytest.mark.parametrize("form", ["the plain path an older setup wrote", "one word, as this version writes it",
                                  "the tilde form"])
def test_G18_1_P99_uninstall_knows_its_own_line_in_every_form(lived, form):
    """Ours, in a form a known version wrote or the tilde form: taken out, and the person's own line is back."""
    home, pb = lived
    own(home)
    assert run("setup", "--minimal", "--apply")[0] == 0
    wpath = S.wrapper_path(str(pb))
    if form.startswith("the plain"):
        put(home, wpath)
    elif form.startswith("the tilde"):
        put(home, "~/.pitboard/statusline.sh")
    else:
        assert command(home) == leave.one_word(wpath) != wpath
    code, out = leave_run("--apply")
    assert code == 0 and "gone: status line setting in ~/.claude/settings.json" in out, out
    assert command(home) == "printf mine"
    assert not pb.exists()


@pytest.mark.parametrize("value,words", [
    ("~/.pitboard/statusline.sh --mine", "in a form setup did not write, so you changed it: left as it is"),
    (7, "statusLine.command could not be read; the file was not touched"),
    ("'~/.pitboard/statusline.sh", "statusLine.command could not be read; the file was not touched")],
    ids=["changed by the person", "not text", "a quote left open"])
def test_G18_1_P99_a_line_the_person_changed_or_that_cannot_be_read_is_kept_and_named(lived, value, words):
    """The other two answers: the file is not touched, the line says which answer it is and where, the wrapper the
    setting still runs stays, the run ends as not complete (exit 11), and the setting's own text is never printed."""
    home, pb = lived
    own(home)
    assert run("setup", "--minimal", "--apply")[0] == 0
    raw = put(home, value)
    for argv in ((), ("--apply",)):
        code, out = leave_run(*argv)
        assert words in " ".join(out.split()), out
        assert "--mine" not in out
        assert (home / ".claude" / "settings.json").read_bytes() == raw
    assert code == leave.INCOMPLETE and (pb / "statusline.sh").exists()
    code, out, err = run("version")
    assert "status line setting: " in out and "--mine" not in out, out
    if isinstance(value, str) and "--mine" in value:
        code, out, err = run("setup", "--minimal")
        assert "keep (it names the wrapper in a form setup did not write: yours, left as it is)" in out, out
    else:
        code, out, err = run("setup", "--minimal", "--apply")
        assert code == 6 and "could not be read" in err and "Nothing changed." in err, (out, err)
        assert (home / ".claude" / "settings.json").read_bytes() == raw


def test_G18_1_P99_no_line_printed_or_logged_holds_the_persons_own_status_line_command(lived):
    """The read-back's own words (the maintainer's ruling, 2026-11-25): a status line command can hold a secret as a
    value can. Setup says that a command of the person's own is there and where it is kept, never the command. A
    made-up secret inside it reaches no printed or logged line of setup, status, version or uninstall; it stays where
    it is kept: the wrapper, setup's record and the settings file's backup."""
    home, pb = lived
    secret = "p99" + "-made-" + "up-" + "word"
    own(home, f"printf mine; : KEEP={secret}")
    said = []
    for argv in (("setup", "--minimal"), ("setup", "--minimal", "--apply"), ("setup", "--minimal", "--apply"),
                 ("version",), ("setup", "--minimal")):
        code, out, err = run(*argv)
        assert code == 0, (argv, out, err)
        said.append(out + err)
    plan, done = said[0], said[1]
    assert "your own status line command is kept" in plan and "the backup made beside this file" in plan, plan
    bak = [n for n in os.listdir(home / ".claude") if n.startswith("settings.json.bak-")]
    assert len(bak) == 1 and f"the backup ~/.claude/{bak[0]}" in done, (bak, done)
    r = subprocess.run(["/bin/sh", str(pb / "statusline.sh")], input=INPUT, capture_output=True, timeout=30,
                       cwd=str(home), env={"PATH": os.environ["PATH"], "HOME": str(home)})
    said.append(r.stdout.decode() + r.stderr.decode())                      # the status line itself
    assert r.stdout.decode().endswith("mine")
    kept = [pb / "statusline.sh", pb / "setup-record.json", home / ".claude" / bak[0]]
    assert all(secret in p.read_text() for p in kept), [p.name for p in kept if secret not in p.read_text()]
    logged = "".join(p.read_text(errors="replace") for p in (pb / "logs").glob("*")) if (pb / "logs").is_dir() else ""
    for argv in ((), ("--apply",)):
        code, out = leave_run(*argv)
        said.append(out)
    assert code == 0 and command(home) == f"printf mine; : KEEP={secret}"   # put back whole
    for text in said + [logged]:
        assert secret not in text and "KEEP=" not in text, text
