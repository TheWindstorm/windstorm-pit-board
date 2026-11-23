"""G21.2 (plan 1.25, P14): the README's install and update lines, and the way back for an install made before the
catalog's entry changed form. The lines themselves were seen to work on stock machines (PROMISES.json P14 'proven');
this test holds the README to the lines that were run."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _blocks(text):
    return [b.strip().splitlines() for b in re.findall(r"^```\n(.*?)^```", text, re.M | re.S)]


def test_G21_2_the_readme_gives_the_update_lines_and_the_way_back():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    blocks = _blocks(text)
    assert ["claude plugin marketplace add TheWindstorm/windstorm-pit-stop",
            "claude plugin install windstorm-pit-board@thewindstorm"] in blocks
    assert ["claude plugin marketplace update thewindstorm",
            "claude plugin update windstorm-pit-board@thewindstorm"] in blocks
    assert ["claude plugin uninstall windstorm-pit-board@thewindstorm",
            "claude plugin install windstorm-pit-board@thewindstorm"] in blocks
    versions = text[text.index("**Claude Code versions.**"):]
    assert "URL source over HTTPS" in versions and "no GitHub key" in versions
    for seen in ("2.1.280", "2.1.330"):
        assert seen in versions
    assert "insteadOf" not in text                     # no git-wide workaround (ruled 2026-11-23)
