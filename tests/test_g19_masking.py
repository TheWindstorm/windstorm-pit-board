"""G19: secret masking. Every fake secret is built from pieces at run time (G19.3)."""
import os
import re

import pytest

from pitboard import contract as c

M = c.MASK


def fake(prefix, n, alphabet="aB3"):
    return prefix + (alphabet * n)[:n]


@pytest.mark.parametrize("secret", [
    fake("sk-", 24),
    fake("sk-" + "ant-", 30),
    fake("gh" + "p_", 36),
    fake("gh" + "o_", 36),
    fake("github" + "_pat_", 40),
    fake("xo" + "xb-", 20),
    "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    fake("AI" + "za", 35),
    fake("gl" + "pat-", 24),
    fake("np" + "m_", 36),
    "ey" + "J" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12,
])
def test_G19_1_known_token_shapes(secret):
    out = c.mask(f"use {secret} now")
    assert secret not in out and M in out and out.startswith("use ") and out.endswith(" now")


def test_G19_1_private_key_block_with_and_without_end():
    begin, end = "-----BEGIN " + "RSA PRIVATE KEY-----", "-----END " + "RSA PRIVATE KEY-----"
    out = c.mask(f"key:\n{begin}\nabc\n{end}\nafter")
    assert "abc" not in out and out.endswith("after")
    cut = c.mask(f"start {begin}\nabc\ndef")
    assert cut == "start " + M


def test_G19_1_url_credentials():
    url = "postgres://admin:" + "hunter" + "22@db.example:5432/app"
    out = c.mask(url)
    assert "hunter" not in out and out == f"postgres://{M}@db.example:5432/app"


@pytest.mark.parametrize("text,keep", [
    ("password=" + "x1", "password="),
    ("DB_PASSWORD=" + "x1", "DB_PASSWORD="),
    ("AWS_SECRET_ACCESS_KEY=" + "x1", "AWS_SECRET_ACCESS_KEY="),
    ('{"password": "' + "x1" + '"}', '"password": '),
    ("api_key: " + "x1", "api_key: "),
    ("token=" + "'x1'", "token="),
])
def test_G19_1_key_value_keeps_the_name(text, keep):
    out = c.mask(text)
    assert "x1" not in out and keep in out and M in out


def test_G19_1_bearer():
    out = c.mask("Authorization: Bearer " + "abcDEF123456" * 2)
    assert "abcDEF" not in out and "Bearer " + M in out


def test_G19_1_long_opaque_needs_digit_lower_upper():
    mixed = ("aB3" * 20)[:44]
    assert c.mask(mixed) == M
    sha = "0123456789abcdef" * 3            # git hash style: no upper case
    assert c.mask(sha) == sha
    word = "a" * 50
    assert c.mask(word) == word


def test_G19_1_paths_and_urls_are_left_alone():
    path = "/home/dev/Projects2026/WindstormPitBoard/src/Component9Folder/file.py"
    assert c.mask(path) == path
    url = "https://github.com/TheWindstorm/windstorm-pit-board/blob/main/DNA-STRAND-MASTER-PLAN.md"
    assert c.mask(url) == url


def test_G19_1_plain_asks_are_untouched():
    for t in ["Merge #651 now or wait for review?", "Create a Stripe account for test payments",
              "Name it instead (the Stripe test key)", "Use commit 4f1e2d3 as the base?"]:
        assert c.mask(t) == t


def test_G19_1_masking_is_idempotent():
    t = "password=" + "x1" + " and " + fake("sk-", 24)
    once = c.mask(t)
    assert c.mask(once) == once


def test_G19_2_prepare_masks_every_text_field():
    s = fake("sk-", 24)
    e = c.make_event("asked", uid="a" * 32, ask="A1", lane="l", lane_name="Lane " + s, machine="m",
                     session_id=None, by="agent",
                     data={"kind": "hand", "severity": "blocking", "title": "Key " + s,
                           "detail": s, "why": s, "steps": ["paste " + s], "source": "agent",
                           "where": {"cwd": "/x/" + s}})
    p = c.prepare(e, mode="cut")
    flat = repr(p)
    assert s not in flat


def test_G19_3_no_secret_literals_in_repo_tests():
    """The repository never holds a whole fake secret as one literal (they are built from pieces)."""
    here = os.path.dirname(os.path.abspath(__file__))
    pattern = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})")
    for name in os.listdir(here):
        if name.endswith(".py"):
            with open(os.path.join(here, name), encoding="utf-8") as f:
                assert not pattern.search(f.read()), name
