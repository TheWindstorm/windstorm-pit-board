"""G21.14: PROMISES.json, a lesson from real use is a gate.

These tests refuse the version in .claude-plugin/plugin.json while a promise due in it is not built,
and the version after it until the promise was seen to work on a real machine. Each test checks the
real file, and also that a planted bad copy is refused, so the gate itself cannot go soft.
"""
import copy
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WHOLE = ("id", "seen", "promise", "codon", "owner", "first_ship_in", "ship_in")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _v(s):
    return tuple(int(x) for x in s.split("."))


def _world():
    """The real promises, version, plan text and test names."""
    tests = set()
    for name in os.listdir(os.path.join(ROOT, "tests")):
        if name.startswith("test_") and name.endswith(".py"):
            tests |= set(re.findall(r"^def (test_[A-Za-z0-9_]+)\(", _read("tests", name), re.M))
    return {
        "doc": json.loads(_read("PROMISES.json")),
        "version": _v(json.loads(_read(".claude-plugin", "plugin.json"))["version"]),
        "plan": _read("DNA-STRAND-MASTER-PLAN.md"),
        "tests": tests,
    }


def whole_problems(w):
    out, ids = [], [r.get("id") for r in w["doc"]["rows"]]
    if len(ids) != len(set(ids)):
        out.append("two rows share an id")
    for r in w["doc"]["rows"]:
        out += [f"{r.get('id')}: '{k}' is empty" for k in WHOLE if not r.get(k)]
        if r.get("owner") not in ("person", "maintainer"):
            out.append(f"{r.get('id')}: owner must be 'person' or 'maintainer'")
        for k in ("first_ship_in", "ship_in"):
            if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(r.get(k, ""))):
                out.append(f"{r.get('id')}: {k} is not MAJOR.MINOR.PATCH")
        if r.get("codon") and not re.search(r"\*\*" + re.escape(r["codon"]) + r"(?![0-9])", w["plan"]):
            out.append(f"{r['id']}: codon {r['codon']} is not in the plan")
    return out


def declined_problems(w):
    return ["a declined lesson needs what was heard and why it was not taken"
            for d in w["doc"].get("declined", []) if not (d.get("heard") and d.get("why"))]


def unbuilt_problems(w):
    out = []
    for r in w["doc"]["rows"]:
        if _v(r["ship_in"]) <= w["version"]:
            t = r.get("test") or ""
            if t not in w["tests"]:
                out.append(f"{r['id']} ({r['promise'][:60]}...) is due in {r['ship_in']} and has no test that exists. "
                           "Build it, or have its date moved (see how_to_use in PROMISES.json).")
            elif not t.startswith("test_" + r["codon"].replace(".", "_") + "_"):
                out.append(f"{r['id']}: its test {t} is not named with its codon {r['codon']}")
    return out


def unproven_problems(w):
    return [f"{r['id']} was due in {r['ship_in']} and no real machine has proven it yet"
            for r in w["doc"]["rows"] if _v(r["ship_in"]) < w["version"] and not r.get("proven")]


def moved_problems(w):
    out = []
    for r in w["doc"]["rows"]:
        if r["ship_in"] != r["first_ship_in"]:
            if not r.get("moved_why"):
                out.append(f"{r['id']}: its date moved with no reason written")
            if r["owner"] == "person" and not r.get("moved_by_person"):
                out.append(f"{r['id']}: only the person who saw it can move its date")
    return out


def _planted(w, **row):
    """A copy of the real world with one more row (whole unless the caller says otherwise)."""
    p = copy.deepcopy(w)
    base = {"id": "PX", "seen": "planted", "promise": "planted promise", "codon": "G10.5", "owner": "person",
            "first_ship_in": "0.1.0", "ship_in": "0.1.0", "test": "test_G10_5_wrapper_joins_the_operator_line_and_the_segment",
            "proven": "planted", "moved_why": "", "moved_by_person": ""}
    base.update(row)
    p["doc"]["rows"].append(base)
    return p


def test_G21_14_every_row_is_whole_and_its_codon_is_in_the_plan():
    w = _world()
    assert whole_problems(w) == []
    assert whole_problems(_planted(w, seen="")) == ["PX: 'seen' is empty"]
    assert whole_problems(_planted(w, codon="G99.1")) == ["PX: codon G99.1 is not in the plan"]
    assert whole_problems(_planted(w, id=w["doc"]["rows"][0]["id"])) == ["two rows share an id"]


def test_G21_14_a_lesson_not_taken_is_written_down_with_its_reason():
    w = _world()
    assert declined_problems(w) == []
    p = copy.deepcopy(w)
    p["doc"].setdefault("declined", []).append({"heard": "something", "why": ""})
    assert len(declined_problems(p)) == 1


def test_G21_14_no_version_ships_while_a_promise_due_in_it_is_not_built():
    w = _world()
    assert unbuilt_problems(w) == []
    assert len(unbuilt_problems(_planted(w, test=""))) == 1                       # due now, no test
    assert len(unbuilt_problems(_planted(w, test="test_G10_5_does_not_exist"))) == 1
    assert len(unbuilt_problems(_planted(w, test="test_INV2_cache_can_be_deleted_without_loss"))) == 1  # wrong codon
    assert unbuilt_problems(_planted(w, test="", first_ship_in="99.0.0", ship_in="99.0.0")) == []   # not due yet


def test_G21_14_the_version_after_needs_proof_on_a_real_machine():
    w = _world()
    assert unproven_problems(w) == []
    after = dict(w, version=(w["version"][0], w["version"][1], w["version"][2] + 1))
    planted = [x for x in unproven_problems(_planted(after, proven="")) if x.startswith("PX ")]
    assert len(planted) == 1                                                     # the next version is refused
    assert unproven_problems(_planted(w, proven="")) == []                       # its own version is not


def test_G21_14_a_date_moves_only_with_a_reason_and_a_persons_row_only_by_their_word():
    w = _world()
    assert moved_problems(w) == []
    assert moved_problems(_planted(w, ship_in="0.2.0")) == [
        "PX: its date moved with no reason written", "PX: only the person who saw it can move its date"]
    assert moved_problems(_planted(w, ship_in="0.2.0", moved_why="late")) == [
        "PX: only the person who saw it can move its date"]
    assert moved_problems(_planted(w, owner="maintainer", ship_in="0.2.0", moved_why="late")) == []
