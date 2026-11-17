"""G21.11: every release reads what every earlier release wrote (INV11, G1.13).

Each released version keeps a folder tests/fixtures/releases/<version>/:
  home/           a PITBOARD_HOME that version wrote: config.json, lanes.json,
                  lanes/<key>.jsonl and its state/<key>.json cache
  expected.json   what that version folded from it: every ask of every lane, and
                  the config values it read
The tests copy each folder's home and check the current code folds the same asks
(fields the old version had keep their values; new fields may be added), reads
the old cache, keeps every config key's meaning, and runs the read commands.

Saving a release's folder (part of every release, G21.1), from the repo root:
    python3 -I tests/test_g21_compat.py save <version>
"""
import copy
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RELEASES = os.path.join(HERE, "fixtures", "releases")
ENV = {"PITBOARD_MACHINE": "fixture-box", "PITBOARD_TZ": "America/New_York"}
CONFIG = {"operator_name": "Sam", "escalate_after_hours": 12, "urgent_deadline_hours": 6,
          "reminder_max_items": 5, "display_tz": "America/New_York"}
SID = "00000000-0000-4000-8000-0000000000c1"

if __name__ != "__main__":
    import pytest

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pitboard import cli, contract, lane as L, store  # noqa: E402


def plugin_version():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def versions():
    if not os.path.isdir(RELEASES):
        return []
    return sorted(v for v in os.listdir(RELEASES) if os.path.isfile(os.path.join(RELEASES, v, "expected.json")))


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------- saving a release's folder

def _make_home():
    """Two lanes that use every event type this version writes."""
    store.ensure_home()
    with open(os.path.join(store.home(), "config.json"), "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, indent=2)
    L.resolve(SID, "Fixture Lane")
    steps = []

    def do(*argv):
        code, out, err = run(*argv)
        if code != 0:
            raise SystemExit(f"pitboard {' '.join(argv)} failed ({code}): {err.strip()}")
        steps.append(list(argv))

    a = ("--lane", "fixture-lane")
    do("add", *a, "--title", "Merge #12 now?", "--suggested", "merge now", "--why", "CI green")
    do("add", *a, "--title", "create a test account", "--kind", "hand", "--step", "Open the page",
       "--step", "Paste the key name here", "--deadline", "2026-11-20T22:00:00.000Z", "--severity", "can-wait")
    do("add", *a, "--title", "Keep the old page?", "--kind", "decision", "--severity", "urgent",
       "--suggested", "no, redirect it")
    do("add", *a, "--title", "Use staging first?", "--suggested", "yes", "--detail", "two lines\nof detail")
    do("add", *a, "--title", "Old idea?", "--severity", "can-wait", "--suggested", "drop it")
    do("add", *a, "--title", "Run the long job?", "--kind", "permission", "--suggested", "yes")
    do("update", *a, "A1", "--suggested", "merge now (CI green)")
    do("ok", *a, "A1")
    do("done", *a, "A1", "--note", "merged")
    do("no", *a, "A3")
    do("answer", *a, "A4", "--answer", "Yes, staging first", "--by", "operator")
    do("withdraw", *a, "A5", "--reason", "moot")
    do("done", *a, "A4")
    do("reopen", *a, "A4", "--reason", "staging broke")
    b = ("--lane", "second-lane")
    do("add", *b, "--title", "Plug in the phone", "--kind", "hand", "--step", "Plug it in")
    do("answer", *b, "A1", "--answer", "done it", "--by", "agent")
    for key in ("fixture-lane", "second-lane"):
        store.read_state(key)                      # leave this version's cache next to the log
    return steps


def save(version):
    dest = os.path.join(RELEASES, version)
    if os.path.exists(dest):
        raise SystemExit(f"already saved: {dest} (a release's folder never changes)")
    if version != plugin_version():
        raise SystemExit(f"plugin.json says {plugin_version()}, not {version}")
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.environ.update(ENV, PITBOARD_HOME=home, CLAUDE_CODE_SESSION_ID=SID)
        for k in ("PITBOARD_LANE", "TMUX_PANE", "NO_COLOR", "PITBOARD_SELF_UPDATE"):
            os.environ.pop(k, None)
        cli.where = lambda: {"host": "fixture-host", "cwd": "/home/user/project"}   # nothing of the saving machine
        steps = _make_home()
        lanes = {}
        for key in sorted(store.lane_keys()):
            lanes[key] = {"asks": list(store.all_asks(key).values())}
        cfg = store.config()
        expected = {"version": version, "made_with": steps, "lanes": lanes,
                    "config": {k: cfg[k] for k in CONFIG}}
        keep = shutil.ignore_patterns("*.lock", "*.tmp", "logs", "env.sh")
        shutil.copytree(home, os.path.join(dest, "home"), ignore=keep)
    with open(os.path.join(dest, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(expected, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"saved {dest}")


# ---------------------------------------------------------------- the tests

def _subset_diff(old, new, path=""):
    """Fields the old release had must keep their values; new fields are fine."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for k, v in old.items():
            if k not in new:
                out.append(f"{path}.{k} missing")
            else:
                out += _subset_diff(v, new[k], f"{path}.{k}")
        return out
    return [] if old == new else [f"{path}: {old!r} -> {new!r}"]


if __name__ != "__main__":

    @pytest.fixture(params=versions() or [None])
    def release(request, tmp_path, monkeypatch):
        v = request.param
        if v is None:
            pytest.skip("no released version saved yet")
        shutil.copytree(os.path.join(RELEASES, v, "home"), tmp_path / "home")
        monkeypatch.setenv("PITBOARD_HOME", str(tmp_path / "home"))
        for k, val in ENV.items():
            monkeypatch.setenv(k, val)
        for k in ("PITBOARD_LANE", "CLAUDE_CODE_SESSION_ID", "TMUX_PANE", "PITBOARD_SELF_UPDATE", "NO_COLOR"):
            monkeypatch.delenv(k, raising=False)
        with open(os.path.join(RELEASES, v, "expected.json"), encoding="utf-8") as f:
            return v, json.load(f), tmp_path / "home"

    def test_G21_11_the_current_version_has_its_release_folder():
        # saved at each release (G21.1): plugin.json's version is always a released one or the next release
        assert plugin_version() in versions(), \
            f"run: python3 -I tests/test_g21_compat.py save {plugin_version()}"

    def test_G21_11_every_old_lane_log_folds_the_same(release):
        v, exp, _ = release
        assert sorted(store.lane_keys()) == sorted(exp["lanes"])
        for key, want in exp["lanes"].items():
            got = list(store.all_asks(key).values())
            assert [a["ask"] for a in got] == [a["ask"] for a in want["asks"]], (v, key)
            for old, new in zip(want["asks"], got):
                assert _subset_diff(old, new) == [], (v, key, old["ask"])

    def test_G21_11_old_cache_is_read_or_rebuilt(release):
        v, exp, home = release
        for key, want in exp["lanes"].items():
            live = {a["ask"]: a["status"] for a in want["asks"] if a["status"] in ("open", "answered")}
            st = store.read_state(key)
            assert {a["ask"]: a["status"] for a in st["asks"]} == live, (v, key)
            os.remove(home / "state" / f"{key}.json")
            assert {a["ask"]: a["status"] for a in store.read_state(key)["asks"]} == live, (v, key)

    def test_G21_11_config_keys_keep_their_meaning(release):
        v, exp, _ = release
        cfg = store.config()
        for k, val in exp["config"].items():
            assert cfg.get(k) == val, (v, k)

    def test_G21_11_lane_map_still_resolves(release):
        v, exp, _ = release
        assert L.read_map()[SID]["lane"] == "fixture-lane"
        assert L.resolve(SID, "Renamed Later")["lane"] == "fixture-lane"   # G3.4: the key never changes

    def test_G21_11_read_commands_run_on_old_data(release):
        v, exp, _ = release
        for key in exp["lanes"]:
            for argv in (("board", "--plain"), ("board", "--all", "--plain", "--limit", "0"), ("list", "--all"),
                         ("show", "A1"), ("export", "--format", "jsonl")):
                code, out, err = run(*argv, "--lane", key)
                assert code == 0 and out and not err, (v, key, argv, err)

    def test_G21_11_events_from_a_newer_machine(release):
        # one minor version newer: extra fields on the envelope and in data are ignored (G1.13),
        # and an unknown event type at the same format version is skipped, not an error
        v, exp, home = release
        for key, want in exp["lanes"].items():
            path = home / "lanes" / f"{key}.jsonl"
            events = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            newer = []
            for ev in events:
                ev = copy.deepcopy(ev)
                ev["x_future"] = {"from": "a newer release"}
                if isinstance(ev.get("data"), dict):
                    ev["data"]["x_future"] = 1
                newer.append(ev)
            unknown = copy.deepcopy(events[0])
            unknown.update(event_id=contract.new_id(), type="x_future_event", data={})
            newer.append(unknown)
            asks, stats = contract.fold(newer)
            assert stats["invalid"] == 0 and stats["skipped"] == 1, (v, key, stats)
            for old, new in zip(want["asks"], asks.values()):
                assert _subset_diff(old, new) == [], (v, key, old["ask"])


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "save":
        save(sys.argv[2])
    else:
        raise SystemExit("usage: python3 -I tests/test_g21_compat.py save <version>")
