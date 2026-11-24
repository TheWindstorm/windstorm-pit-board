"""P57 (the family's rule 2, part 3): the lived-in list is kept beside the tests, every line dated, and it carries
what rule 2 names for Claude Code (a settings file with many keys, other plugins' hooks, an own status line) and for
a shell (a token and tool settings exported). The lived-in round itself runs on a test account before each tag."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_G21_14_P57_the_lived_in_list_is_kept_beside_the_tests():
    with open(os.path.join(ROOT, "tests", "LIVED-IN.md"), encoding="utf-8") as f:
        text = f.read()
    items = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert items and all(re.match(r"- \d{4}-\d{2}-\d{2}: ", ln) for ln in items), items
    for needed in ("ten top-level keys", "`hooks`", "`enabledPlugins`", "an own status line", "`refreshInterval` 5",
                   "a token exported", "tool settings exported", "a session name holding a quote"):
        assert needed in text, needed
    for name in ("no-name.json", "name-1.json", "name-2.json"):
        assert os.path.isfile(os.path.join(ROOT, "tests", "fixtures", "statusline", name)), name
