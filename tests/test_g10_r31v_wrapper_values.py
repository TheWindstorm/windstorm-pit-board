"""P97 (G10.5, the family's rule 31 (v.2)): the status line wrapper is a shell script that holds two values Pit Board did not
write, the person's own status line command and Pit Board's home folder. Each goes in quoted for the shell, whole: the
person's command runs exactly as it runs alone, and the home folder's name runs nothing, whatever characters they hold."""
import os
import shutil
import subprocess

import pytest

from pitboard import setup as S

OWN = [
    "printf 'mine'",
    "printf '%s' \"it's\"; printf ' $HOME'",              # quotes of both kinds, a variable the person meant
    "printf '%s' \"$(printf sub)\" `printf tick`",       # the person's own command substitutions
    "echo L1\necho L2",                                   # a command of two lines
    "printf 'x\rCR'",                                     # a carriage return
    "printf 'a\\\\b'",                                    # a backslash
    "printf '%s' '%d %% \\n \\c'",                         # prints a format's own characters, as plain text
]
HOMES = [
    "pb home 'q' $(touch HOMESUB) `touch HOMETICK`",
    "pb;home&&touch HOMESEMI|x",
    "nl\nhome",
    "cr\rhome",
    'dq"home\\$x',
]


def _shells():
    return [s for s in ("/bin/sh", shutil.which("bash"), shutil.which("dash")) if s]


def _home(base, name):
    home = os.path.join(base, name)
    os.makedirs(os.path.join(home, "bin"))
    launcher = os.path.join(home, "bin", "pitboard")
    with open(launcher, "w") as f:                       # a stand-in launcher: reads the input, prints a segment
        f.write("#!/bin/sh\ncat >/dev/null; printf 'SEG'\n")
    os.chmod(launcher, 0o755)
    return home


def _expected(own_out):
    own_out = own_out.rstrip("\n")                       # $( ) drops trailing newlines, as the wrapper's own= does
    if not own_out:
        return "SEG"
    return f"SEG\n{own_out}" if "\n" in own_out else f"SEG · {own_out}"


@pytest.mark.parametrize("shell", _shells())
@pytest.mark.parametrize("where,value", [("own", v) for v in OWN] + [("home", v) for v in HOMES])
def test_G10_5_P97_values_the_wrapper_did_not_write_stay_whole_and_run_nothing(tmp_path, where, value, shell):
    """The person's command gives the output it gives alone and is kept whole for uninstall; a home folder's name
    makes no file and runs nothing, while the launcher in that very folder still runs."""
    own, name = (value, "pb") if where == "own" else ("printf mine", value)
    home = _home(str(tmp_path), name)
    wrap = tmp_path / "statusline.sh"
    wrap.write_text(S.wrapper_text(own, home))
    inp = b'{"session_id":"abc"}'
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}
    alone = subprocess.run(["/bin/sh", "-c", own], input=inp, capture_output=True, cwd=home, env=env, timeout=30)
    before = sorted(os.listdir(tmp_path))
    r = subprocess.run([shell, str(wrap)], input=inp, capture_output=True, cwd=tmp_path, env=env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode() == _expected(alone.stdout.decode()), (r.stdout, alone.stdout, r.stderr)
    assert S.original_from_wrapper(str(wrap)) == own      # the command is kept whole for uninstall
    assert sorted(os.listdir(tmp_path)) == before         # nothing in a value made a file
