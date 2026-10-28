"""ROADMAP.md item 402: the pasted Buttondown emails stay short and carry the
variable Buttondown requires."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _body(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    return text.split("**Body:**", 1)[1].split("\n---", 1)[0]


def test_confirmation_email_is_short_and_links_the_confirmation_url():
    body = _body("CONFIRMATION_EMAIL.md")
    assert len(re.findall(r"\S+", body)) < 80
    assert "[Click to confirm]({{ confirmation_url }})" in body
    assert "utm_campaign=confirm" in body and "Ignore this" in body
    assert "Confirm your Within Ten email (one click)" in (ROOT / "CONFIRMATION_EMAIL.md").read_text(encoding="utf-8")
