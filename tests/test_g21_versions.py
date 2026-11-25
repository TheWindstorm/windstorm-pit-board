"""G21.1 (plan 1.23): one version in every place, and a tag's fresh clone is refused unless its name is every label.

A sister skill's manifest named an old version through three releases, so `claude plugin update` said it was already
at the latest version and kept the old code. Here the version is stated in .claude-plugin/plugin.json, in
pitboard/__init__.py (__version__, which `pitboard version` prints) and in CHANGELOG.md's top dated heading."""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADING = re.compile(r"^## ([0-9]+\.[0-9]+\.[0-9]+) \((.*)\)\s*$", re.M)
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
UNRELEASED = "not yet released"
TAG = re.compile(r"v([0-9]+\.[0-9]+\.[0-9]+)")


def _vkey(v):
    return tuple(int(x) for x in v.split("."))


def _read(root, *parts):
    with open(os.path.join(root, *parts), encoding="utf-8") as f:
        return f.read()


def manifest_version(root):
    return json.loads(_read(root, ".claude-plugin", "plugin.json"))["version"]


def package_version(root):
    m = re.search(r'^__version__ = "([^"]*)"$', _read(root, "pitboard", "__init__.py"), re.M)
    return m.group(1) if m else None


def headings(root):
    """CHANGELOG.md's release headings, top first: (version, what is in the brackets). Plan headings are not these."""
    return HEADING.findall(_read(root, "CHANGELOG.md"))


def _top_dated(heads):
    return next((i for i, (_, when) in enumerate(heads) if DATE.fullmatch(when)), None)


CLONE = re.compile(r"git clone\b(.*)$", re.M)


def clone_problems(root, want):
    """P36 (the family's rule 15, at the tag): every `git clone` line README.md prints names the release a person can
    paste: `--branch v<want>`, where want is the version this tree states. A placeholder, an older or newer tag, a
    branch, or a bare clone of the default branch fails. A README that cannot be read is a problem, not "no lines"."""
    try:
        text = _read(root, "README.md")
    except OSError as e:
        return [f"README.md could not be read: {type(e).__name__}"]
    out = []
    for rest in CLONE.findall(text):
        m = re.search(r"--branch\s+(\S+)", rest)
        if not m:
            out.append(f"README.md clone line has no --branch: git clone{rest}")
        elif m.group(1) != f"v{want}":
            out.append(f"README.md clone line names {m.group(1)}, not v{want}")
    return out


def version_problems(root):
    """Every place that states the version names the same one, on main and in every release."""
    man, pkg, heads = manifest_version(root), package_version(root), headings(root)
    out = [] if pkg == man else [f"pitboard/__init__.py says {pkg}, plugin.json says {man}"]
    out += clone_problems(root, man)
    out += heading_shape_problems(root)
    top = _top_dated(heads)
    if top is None:
        return out + ["CHANGELOG.md has no dated release heading"]
    if heads[top][0] != man:
        out.append(f"CHANGELOG.md's top dated heading is {heads[top][0]}, plugin.json says {man}")
    for v, when in heads[:top]:
        if when != UNRELEASED:
            out.append(f"CHANGELOG.md heading {v} ({when}) above the top dated one is not '{UNRELEASED}'")
        elif _vkey(v) <= _vkey(man):
            out.append(f"CHANGELOG.md's not-yet-released heading names {v}, not later than {man}")
    return out


def tag_problems(root, tag):
    """A tag's clone: the tag's name, without its v, equals every version label in it: plugin.json, __version__,
    and each CHANGELOG.md heading down to the top dated one (so an old label or a not-yet-released heading fails)."""
    want = TAG.fullmatch(tag).group(1)
    out = [f"{where} says {v}, the tag says {want}"
           for where, v in (("plugin.json", manifest_version(root)), ("pitboard/__init__.py", package_version(root)))
           if v != want]
    out += clone_problems(root, want) + heading_shape_problems(root)
    heads = headings(root)
    top = _top_dated(heads)
    for v, when in heads[:(len(heads) if top is None else top + 1)]:
        if v != want or not DATE.fullmatch(when):
            out.append(f"CHANGELOG.md heading {v} ({when}): the tag says {want}")
    return out


def promise_problems_at_tag(root, tag):
    """P18 (plan 1.29): the tag is refused while a row due in its version has an empty `proven`, unless the row
    names why it can only be proven after the release (`proven_after_release`). Returns (problems, listed ids)."""
    want = TAG.fullmatch(tag).group(1)
    try:
        rows = json.loads(_read(root, "PROMISES.json"))["rows"]
    except (OSError, ValueError, KeyError, TypeError) as e:          # could not be read is not "no rows" (rule 6)
        return [f"PROMISES.json could not be read: {type(e).__name__}"], []
    due = [r for r in rows if r.get("ship_in") == want and not r.get("proven")]
    listed = [r["id"] for r in due if str(r.get("proven_after_release") or "").strip()]
    return [f"{r['id']} is due in {want} and has no proven line" for r in due if r["id"] not in listed], listed


def release_tags_at_head(root):
    """The release tags on the checked-out commit; none on a branch, or where this is not a git checkout."""
    if not shutil.which("git") or not os.path.exists(os.path.join(root, ".git")):
        return []
    p = subprocess.run(["git", "-C", root, "tag", "--points-at", "HEAD"], capture_output=True, text=True, timeout=30)
    return [t for t in p.stdout.split() if TAG.fullmatch(t)]


LIKE_A_HEADING = re.compile(r"^##\s*[vV]?[0-9].*$", re.M)
LIKE_A_TAG = re.compile(r"[vV]?[0-9]")


def heading_shape_problems(root):
    """P100: a CHANGELOG.md heading that begins like a version and is not a release heading HEADING reads. Without
    this, the checks above pass such a heading by not seeing it (0.1.2.1, v0.1.3, 0.1.3-rc1, a heading with no day)."""
    return [f"CHANGELOG.md heading '{line.rstrip()}' begins like a version and is not "
            "'## MAJOR.MINOR.PATCH (a day, or not yet released)'"
            for line in LIKE_A_HEADING.findall(_read(root, "CHANGELOG.md")) if not HEADING.fullmatch(line)]


def tag_shape_problems(root):
    """P100: a tag on the checked-out commit that begins like a version and is not v and three numbers. Without this,
    release_tags_at_head() passes such a tag by not seeing it, and its clone is never checked."""
    if not shutil.which("git") or not os.path.exists(os.path.join(root, ".git")):
        return []
    p = subprocess.run(["git", "-C", root, "tag", "--points-at", "HEAD"], capture_output=True, text=True, timeout=30)
    return [f"tag {t} begins like a version and is not vMAJOR.MINOR.PATCH"
            for t in p.stdout.split() if LIKE_A_TAG.match(t) and not TAG.fullmatch(t)]


GOOD_CLONE = "git clone --depth 1 --branch v0.1.2 https://github.com/TheWindstorm/windstorm-pit-board"


def _tree(tmp_path, manifest="0.1.2", package="0.1.2", changelog=("## 0.1.2 (2026-11-24)", "## 0.1.1 (2026-11-22)"),
          clone=GOOD_CLONE):
    root = tmp_path / "tree"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / "pitboard").mkdir()
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "windstorm-pit-board", "version": manifest}))
    (root / "pitboard" / "__init__.py").write_text(f'"""Pit Board."""\n__version__ = "{package}"\n')
    if clone is not None:
        (root / "README.md").write_text(f"# Pit Board\n\n```\n{clone}\nwindstorm-pit-board/bin/pitboard setup\n```\n")
    (root / "CHANGELOG.md").write_text("# Changelog\n\n" + "\n- a change\n\n".join(changelog)
                                       + "\n- a change\n\n## Plan 1.23 (2026-11-22)\n- a plan line\n")
    return str(root)


def test_G21_1_one_version_in_every_place(tmp_path):
    """P12 (a guard): the real tree names one version in every place, and each way a place can differ fails."""
    assert version_problems(ROOT) == []
    assert manifest_version(ROOT) == package_version(ROOT)
    assert version_problems(_tree(tmp_path)) == []
    shutil.rmtree(tmp_path / "tree")
    unreleased = ("## 0.1.3 (not yet released)", "## 0.1.2 (2026-11-24)")
    assert version_problems(_tree(tmp_path, changelog=unreleased)) == []
    for kw, want in [
        (dict(package="0.1.1"), "pitboard/__init__.py says 0.1.1, plugin.json says 0.1.2"),
        (dict(manifest="0.1.1", package="0.1.1"), "CHANGELOG.md's top dated heading is 0.1.2, plugin.json says 0.1.1"),
        (dict(changelog=("## 0.1.2 (not yet released)", "## 0.1.2 (2026-11-24)")),
         "CHANGELOG.md's not-yet-released heading names 0.1.2, not later than 0.1.2"),
        (dict(changelog=("## 0.1.3 (soon)", "## 0.1.2 (2026-11-24)")),
         "CHANGELOG.md heading 0.1.3 (soon) above the top dated one is not 'not yet released'"),
        (dict(changelog=("## 0.1.2 (not yet released)",)), "CHANGELOG.md has no dated release heading"),
    ]:
        shutil.rmtree(tmp_path / "tree")
        assert want in version_problems(_tree(tmp_path, **kw)), kw


def test_G21_1_the_readme_clone_line_names_the_release_a_person_can_paste(tmp_path):
    """P36: the README's clone line names the tag of the version this tree states; each way it can be wrong fails."""
    assert clone_problems(ROOT, manifest_version(ROOT)) == []
    assert CLONE.findall(_read(ROOT, "README.md")), "the README prints a clone line"
    for clone, want in [
        (GOOD_CLONE.replace("v0.1.2", "vX.Y.Z"), "README.md clone line names vX.Y.Z, not v0.1.2"),
        (GOOD_CLONE.replace("v0.1.2", "v0.1.1"), "README.md clone line names v0.1.1, not v0.1.2"),
        (GOOD_CLONE.replace("v0.1.2", "main"), "README.md clone line names main, not v0.1.2"),
        ("git clone https://github.com/TheWindstorm/windstorm-pit-board", "README.md clone line has no --branch"),
    ]:
        shutil.rmtree(tmp_path / "tree", ignore_errors=True)
        root = _tree(tmp_path, clone=clone)
        assert any(want in x for x in version_problems(root)), clone
        assert any(want in x for x in tag_problems(root, "v0.1.2")), clone
    shutil.rmtree(tmp_path / "tree")
    assert "README.md could not be read: FileNotFoundError" in version_problems(_tree(tmp_path, clone=None))


def test_G21_1_a_tags_clone_is_refused_unless_its_name_is_every_version_label(tmp_path, monkeypatch):
    """The release step (plan 1.23): run in a fresh clone of a tag, this refuses it unless the tag names every label."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))                       # P51: git runs with the test's home
    assert tag_shape_problems(ROOT) == []                                    # P100: no tag here is passed over
    for tag in release_tags_at_head(ROOT):                                   # only in a tag's checkout
        assert tag_problems(ROOT, tag) == [], tag
        problems, listed = promise_problems_at_tag(ROOT, tag)
        assert problems == [], (tag, problems)
        print(f"{tag}: rows proven only after the release: {listed or 'none'}")
    assert tag_problems(_tree(tmp_path), "v0.1.2") == []
    shutil.rmtree(tmp_path / "tree")
    old = _tree(tmp_path, manifest="0.1.1", package="0.1.1")                 # the sister skill's fault: an old label
    assert tag_problems(old, "v0.1.2") == ["plugin.json says 0.1.1, the tag says 0.1.2",
                                           "pitboard/__init__.py says 0.1.1, the tag says 0.1.2"]
    shutil.rmtree(tmp_path / "tree")
    left = _tree(tmp_path, changelog=("## 0.1.2 (not yet released)", "## 0.1.1 (2026-11-22)"))
    assert tag_problems(left, "v0.1.2") == ["CHANGELOG.md heading 0.1.2 (not yet released): the tag says 0.1.2",
                                            "CHANGELOG.md heading 0.1.1 (2026-11-22): the tag says 0.1.2"]


@pytest.mark.skipif(not shutil.which("git"), reason="no git here")
def test_G21_1_a_fresh_clone_of_a_tag_finds_its_tag(tmp_path, monkeypatch):
    """`git clone --branch <tag>` checks out the tag's commit with the tag, so the check above runs there."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))                       # P51: git runs with the test's home
    src = _tree(tmp_path)
    env = dict(os.environ, HOME=str(tmp_path / "home"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "release"], ["tag", "v0.1.2"]):
        subprocess.run(["git", "-C", src] + cmd, check=True, env=env, capture_output=True, timeout=30)
    clone = str(tmp_path / "clone")
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "v0.1.2", "file://" + src, clone],
                   check=True, env=env, capture_output=True, timeout=60)
    assert release_tags_at_head(clone) == ["v0.1.2"]
    assert release_tags_at_head(src) == ["v0.1.2"]
    subprocess.run(["git", "-C", src, "commit", "-q", "--allow-empty", "-m", "after"], check=True, env=env,
                   capture_output=True, timeout=30)
    assert release_tags_at_head(src) == []                                   # a branch past the tag: nothing to check


ODD_HEADINGS = ["## 0.1.2.1 (2026-11-30)", "## v0.1.3 (2026-11-26)", "## 0.1.3", "## 0.1 (2026-11-26)",
                "## 0.1.3-rc1 (not yet released)", "## 0.1.3 (2026-11-26) and more"]
ODD_TAGS = ["v0.1.2.1", "v0.1.3-rc1", "0.1.3", "v1.2", "V0.1.3"]


@pytest.mark.skipif(not shutil.which("git"), reason="no git here")
def test_G21_1_a_tag_or_heading_that_begins_like_a_version_and_is_not_three_numbers_is_refused_by_name(tmp_path, monkeypatch):
    """P100: a release heading or a tag the checks cannot read is a problem with its own name in it, never passed
    over. A plan's heading, and a tag that is not a version at all, do not begin like a version and are left alone."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))                       # P51: git runs with the test's home
    assert heading_shape_problems(ROOT) == [] and tag_shape_problems(ROOT) == []
    assert heading_shape_problems(_tree(tmp_path)) == []                      # "## Plan 1.23 (...)" is not one
    for odd in ODD_HEADINGS:
        want = (f"CHANGELOG.md heading '{odd}' begins like a version and is not "
                "'## MAJOR.MINOR.PATCH (a day, or not yet released)'")
        for changelog in ((odd, "## 0.1.2 (2026-11-24)"), ("## 0.1.2 (2026-11-24)", odd)):   # above the top dated one, and below
            shutil.rmtree(tmp_path / "tree")
            root = _tree(tmp_path, changelog=changelog)
            assert heading_shape_problems(root) == [want], odd
            assert want in version_problems(root) and want in tag_problems(root, "v0.1.2"), odd       # on a branch, at a tag
    shutil.rmtree(tmp_path / "tree")
    src = _tree(tmp_path)
    env = dict(os.environ, HOME=str(tmp_path / "home"), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")

    def git(*cmd):
        subprocess.run(["git", "-C", src] + list(cmd), check=True, env=env, capture_output=True, timeout=30)

    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "release"], ["tag", "v0.1.2"], ["tag", "pilot"]):
        git(*cmd)
    assert tag_shape_problems(src) == [] and release_tags_at_head(src) == ["v0.1.2"]
    for odd in ODD_TAGS:
        git("tag", odd)
        assert tag_shape_problems(src) == [f"tag {odd} begins like a version and is not vMAJOR.MINOR.PATCH"], odd
        assert release_tags_at_head(src) == ["v0.1.2"]                       # the older read does not see it at all
        git("tag", "-d", odd)
    git("tag", "v0.1.2.1")
    clone = str(tmp_path / "clone")                                          # as the release step meets it
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", "v0.1.2.1", "file://" + src, clone],
                   check=True, env=env, capture_output=True, timeout=60)
    assert "tag v0.1.2.1 begins like a version and is not vMAJOR.MINOR.PATCH" in tag_shape_problems(clone)
    git("commit", "-q", "--allow-empty", "-m", "after")
    assert tag_shape_problems(src) == []                                     # a branch past the tags: nothing at HEAD


def _rows(root, *rows):
    with open(os.path.join(root, "PROMISES.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": list(rows)}, f)


def test_G21_1_a_tag_is_refused_while_a_row_due_in_it_has_no_proven_line(tmp_path):
    """P18 (plan 1.29): a row that leans on a stand-in is seen on a real machine before its version is tagged."""
    root = _tree(tmp_path)
    _rows(root, {"id": "P1", "ship_in": "0.1.2", "proven": "a stock machine, 0.1.2, 2026-11-23"},
          {"id": "P2", "ship_in": "0.1.3", "proven": ""})
    assert promise_problems_at_tag(root, "v0.1.2") == ([], [])
    _rows(root, {"id": "P1", "ship_in": "0.1.2", "proven": ""})
    assert promise_problems_at_tag(root, "v0.1.2") == (["P1 is due in 0.1.2 and has no proven line"], [])
    _rows(root, {"id": "P1", "ship_in": "0.1.2", "proven": "", "proven_after_release": "a count over two days"})
    assert promise_problems_at_tag(root, "v0.1.2") == ([], ["P1"])          # listed, not refused
    _rows(root, {"id": "P1", "ship_in": "0.1.2", "proven": "", "proven_after_release": "  "})
    assert promise_problems_at_tag(root, "v0.1.2")[0] == ["P1 is due in 0.1.2 and has no proven line"]
    with open(os.path.join(root, "PROMISES.json"), "w") as f:
        f.write("{not json")
    assert promise_problems_at_tag(root, "v0.1.2") == (["PROMISES.json could not be read: JSONDecodeError"], [])
