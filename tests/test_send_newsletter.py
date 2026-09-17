import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from send_newsletter import (  # noqa: E402
    COMBINED_REGION,
    SendError,
    extract_subject,
    html_byte_size,
    load_send_config,
    read_built_email,
)

# The real file opens with an authoring comment that mentions "<title>" in
# prose. A naive regex matches that mention first and returns most of the
# file as the subject, so every fixture here keeps the trap in place.
COMMENT_WITH_TITLE_MENTION = (
    "<!--\n  Subject line is shown both in <title> (visible in a browser\n"
    "  tab) and as a note at the top of the body.\n-->\n"
)


def build_email_html(subject: str, body: str = "<p>Hi</p>") -> str:
    return (
        f"{COMMENT_WITH_TITLE_MENTION}<!doctype html>\n<html>\n<head>\n"
        f"<title>{subject}</title>\n</head>\n<body>{body}</body>\n</html>\n"
    )


def test_extract_subject_ignores_the_prose_mention_in_the_comment():
    html = build_email_html("This weekend in Mount Prospect: Oktoberfest, and 1 more")
    assert (
        extract_subject(html)
        == "This weekend in Mount Prospect: Oktoberfest, and 1 more"
    )


def test_extract_subject_unescapes_entities():
    html = build_email_html("Fall Festival &amp; Oktoberfest")
    assert extract_subject(html) == "Fall Festival & Oktoberfest"


def test_extract_subject_rejects_a_file_with_no_title():
    with pytest.raises(SendError, match="found 0"):
        extract_subject("<!doctype html><html><body>no head</body></html>")


def test_read_built_email_refuses_the_preview_annotation(tmp_path):
    """Item 91's guard. If email-send.html ever regresses into a copy of
    email-preview.html, the annotation would go out as body copy - which
    is exactly what happened on the first real send."""
    region = tmp_path / "mount-prospect-60056"
    region.mkdir()
    (region / "email-send.html").write_text(
        build_email_html("Subject", body="<p>PREVIEW ONLY, NOT PART OF THE EMAIL</p>"),
        encoding="utf-8",
    )
    with pytest.raises(SendError, match="preview annotation"):
        read_built_email("mount-prospect-60056", docs_dir=tmp_path)


def test_read_built_email_returns_subject_and_html(tmp_path):
    region = tmp_path / "mount-prospect-60056"
    region.mkdir()
    (region / "email-send.html").write_text(
        build_email_html("This weekend in Mount Prospect"), encoding="utf-8"
    )
    subject, html = read_built_email("mount-prospect-60056", docs_dir=tmp_path)
    assert subject == "This weekend in Mount Prospect"
    assert "<body>" in html


def test_read_built_email_missing_file_names_the_build_step(tmp_path):
    with pytest.raises(SendError, match="build_digest.py"):
        read_built_email("nope-00000", docs_dir=tmp_path)


def test_load_send_config_rejects_an_unknown_mode(tmp_path):
    cfg = tmp_path / "newsletter.yaml"
    cfg.write_text("send:\n  enabled: true\n  mode: blast\n", encoding="utf-8")
    with pytest.raises(SendError, match="draft"):
        load_send_config(cfg)


def test_load_send_config_defaults_to_draft(tmp_path):
    """The safe default has to survive someone omitting the key."""
    cfg = tmp_path / "newsletter.yaml"
    cfg.write_text("send:\n  enabled: true\n  region: r\n", encoding="utf-8")
    assert load_send_config(cfg)["mode"] == "draft"


def test_load_send_config_absent_block_is_a_clean_no_op(tmp_path):
    cfg = tmp_path / "newsletter.yaml"
    cfg.write_text("buttondown_username: someone\n", encoding="utf-8")
    parsed = load_send_config(cfg)
    assert parsed["enabled"] is False
    assert parsed["mode"] == "draft"


def test_the_real_config_is_parseable_and_names_a_real_region():
    """Guards the live config, not a fixture: a typo'd region id here
    would only surface on a Thursday morning."""
    parsed = load_send_config()
    if parsed["enabled"] and parsed["region"] != COMBINED_REGION:
        repo_root = Path(__file__).resolve().parents[1]
        assert (repo_root / "config" / "regions" / f"{parsed['region']}.yaml").exists()


def test_read_built_email_combined_region_reads_the_combined_file(tmp_path):
    (tmp_path / "combined-email-send.html").write_text(
        build_email_html("This weekend across Mount Prospect and Arlington Heights"),
        encoding="utf-8",
    )
    subject, html = read_built_email(COMBINED_REGION, docs_dir=tmp_path)
    assert subject == "This weekend across Mount Prospect and Arlington Heights"
    assert "<body>" in html


def test_read_built_email_combined_region_also_refuses_the_preview_annotation(tmp_path):
    (tmp_path / "combined-email-send.html").write_text(
        build_email_html("Subject", body="<p>PREVIEW ONLY, NOT PART OF THE EMAIL</p>"),
        encoding="utf-8",
    )
    with pytest.raises(SendError, match="preview annotation"):
        read_built_email(COMBINED_REGION, docs_dir=tmp_path)


class _FakeResponse:
    def __init__(self, ok=True, status_code=200, payload=None):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload or {"id": "abc123"}
        self.text = "{}"

    def json(self):
        return self._payload


def _capture_post(monkeypatch):
    """Record the kwargs post_to_buttondown hands to requests.post."""
    import send_newsletter

    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr(send_newsletter.requests, "post", fake_post)
    return seen


def test_live_send_carries_the_buttondown_confirmation_header(monkeypatch):
    """Buttondown rejects status='about_to_send' without this header with a
    400 sending_requires_confirmation. A real run failed on exactly that."""
    import send_newsletter

    seen = _capture_post(monkeypatch)
    send_newsletter.post_to_buttondown("Subj", "<p>hi</p>", "key", "send")
    assert seen["headers"][send_newsletter.LIVE_SEND_HEADER] == "true"
    assert seen["json"]["status"] == send_newsletter.STATUS_SEND


def test_draft_does_not_carry_the_live_send_header(monkeypatch):
    """A draft neither needs it nor should imply a send."""
    import send_newsletter

    seen = _capture_post(monkeypatch)
    send_newsletter.post_to_buttondown("Subj", "<p>hi</p>", "key", "draft")
    assert send_newsletter.LIVE_SEND_HEADER not in seen["headers"]
    assert seen["json"]["status"] == send_newsletter.STATUS_DRAFT


def test_api_errors_are_surfaced_verbatim(monkeypatch):
    """The 400 that found the header requirement was only debuggable
    because the body came through untouched."""
    import send_newsletter

    def fake_post(url, **kwargs):
        r = _FakeResponse(ok=False, status_code=400)
        r.text = '{"code":"sending_requires_confirmation"}'
        return r

    monkeypatch.setattr(send_newsletter.requests, "post", fake_post)
    with pytest.raises(SendError, match="sending_requires_confirmation"):
        send_newsletter.post_to_buttondown("S", "<p>h</p>", "key", "send")


def test_html_byte_size_counts_utf8_bytes_not_characters():
    # A found bug: len(html) (character count) under-counts a payload
    # full of multi-byte characters, which is exactly what the real
    # templates are (em dashes, arrows, curly quotes repeated per
    # event/region) - Gmail's 102KB clip limit is a byte limit.
    html = "—" * 1000  # em dash: 1 character, 3 bytes in UTF-8
    assert len(html) == 1000
    assert html_byte_size(html) == 3000


def test_html_byte_size_matches_character_count_for_ascii():
    assert html_byte_size("a" * 500) == 500
