import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from send_newsletter import (  # noqa: E402
    COMBINED_REGION,
    MIN_WEEKEND_EVENTS,
    SendError,
    assert_build_is_fresh,
    assert_has_confirmed_subscribers,
    assert_weekend_is_not_thin,
    extract_subject,
    fetch_subscriber_count,
    html_byte_size,
    load_send_config,
    load_send_history,
    next_thursday_morning,
    read_build_timestamp,
    read_built_email,
    read_weekend_event_count,
    record_send,
    save_send_history,
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


def test_read_built_email_allows_a_real_event_containing_the_shorter_phrase(tmp_path):
    """A found bug: the old check matched the substring "PREVIEW ONLY"
    anywhere in the file, so a real event titled with that shorter
    phrase (e.g. a museum's own "Preview Only Weekend") would have
    blocked a legitimate send. The actual annotation is longer and more
    specific; only that full phrase should trip the guard."""
    region = tmp_path / "mount-prospect-60056"
    region.mkdir()
    (region / "email-send.html").write_text(
        build_email_html("This weekend in Mount Prospect", body="<p>Museum Preview Only Weekend</p>"),
        encoding="utf-8",
    )
    subject, html = read_built_email("mount-prospect-60056", docs_dir=tmp_path)
    assert subject == "This weekend in Mount Prospect"


def test_read_built_email_missing_file_names_the_build_step(tmp_path):
    with pytest.raises(SendError, match="build_digest.py"):
        read_built_email("nope-00000", docs_dir=tmp_path)


def test_load_send_config_rejects_an_unknown_mode(tmp_path):
    cfg = tmp_path / "newsletter.yaml"
    cfg.write_text("send:\n  enabled: true\n  mode: blast\n", encoding="utf-8")
    with pytest.raises(SendError, match="draft"):
        load_send_config(cfg)


def test_load_send_config_accepts_schedule_mode(tmp_path):
    cfg = tmp_path / "newsletter.yaml"
    cfg.write_text("send:\n  enabled: true\n  region: r\n  mode: schedule\n", encoding="utf-8")
    assert load_send_config(cfg)["mode"] == "schedule"


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

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} error")


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


def test_schedule_mode_sets_scheduled_status_and_a_future_publish_date(monkeypatch):
    """ROADMAP.md item 110: schedule mode hands the actual delivery moment
    to Buttondown instead of GitHub Actions cron, which this repo's own
    history showed running 5-7h late. It should not carry the live-send
    header (that's specific to an immediate about_to_send, unverified
    either way for scheduled - see the module docstring)."""
    import send_newsletter

    seen = _capture_post(monkeypatch)
    now = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)  # a Thursday, midday UTC
    send_newsletter.post_to_buttondown("Subj", "<p>hi</p>", "key", "schedule", now=now)
    assert seen["json"]["status"] == send_newsletter.STATUS_SCHEDULED
    assert send_newsletter.LIVE_SEND_HEADER not in seen["headers"]
    scheduled_for = datetime.fromisoformat(seen["json"]["publish_date"])
    assert scheduled_for > now


def test_schedule_mode_publish_date_matches_buttondowns_documented_z_format(monkeypatch):
    """A real, found mismatch: next_thursday_morning() returns an
    America/Chicago-zoned datetime, and .isoformat() on that produces an
    offset string like "2026-09-24T07:00:00-05:00" - but Buttondown's own
    published API docs (docs.buttondown.com/scheduling-emails-via-the-api,
    found via web search since the sandbox can't fetch that domain
    directly) show only a "Z"-suffixed UTC example:
    "2024-12-31T12:00:00Z". A subtly wrong offset a lenient parser reads
    as UTC would send hours early with no error at all - the one failure
    mode this module's "a wrong guess is loud and obvious" docstring
    claim can't actually promise. Assert the exact documented shape
    instead of merely a parseable one."""
    import send_newsletter

    seen = _capture_post(monkeypatch)
    now = datetime(2026, 9, 17, 15, 0, tzinfo=timezone.utc)  # a Thursday, midday UTC
    send_newsletter.post_to_buttondown("Subj", "<p>hi</p>", "key", "schedule", now=now)
    publish_date = seen["json"]["publish_date"]
    assert publish_date.endswith("Z")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", publish_date)
    # And it's still the correct absolute moment, not just correctly shaped.
    assert datetime.fromisoformat(publish_date) == next_thursday_morning(now).astimezone(timezone.utc)


def test_fetch_subscriber_count_reads_the_count_field(monkeypatch):
    import send_newsletter

    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _FakeResponse(payload={"count": 42, "results": []})

    monkeypatch.setattr(send_newsletter.requests, "get", fake_get)
    count = fetch_subscriber_count("key", "regular")
    assert count == 42
    assert seen["params"] == {"type": "regular"}
    assert seen["headers"]["Authorization"] == "Token key"


def test_fetch_subscriber_count_raises_on_http_error(monkeypatch):
    import send_newsletter

    monkeypatch.setattr(
        send_newsletter.requests, "get", lambda url, **kwargs: _FakeResponse(ok=False, status_code=500)
    )
    with pytest.raises(requests.HTTPError):
        fetch_subscriber_count("key", "regular")


def test_assert_has_confirmed_subscribers_allows_at_least_one():
    assert_has_confirmed_subscribers(1)
    assert_has_confirmed_subscribers(500)


def test_assert_has_confirmed_subscribers_rejects_zero():
    # ROADMAP.md item 190: this is exactly the real result item 187's
    # first live metrics call returned (recipients: 0) for this
    # business's only send - the guard this pass found missing.
    with pytest.raises(SendError, match="0 confirmed"):
        assert_has_confirmed_subscribers(0)


def test_record_send_omits_subscriber_count_when_not_measured():
    # A draft never queries Buttondown for a count, so the key shouldn't
    # appear at all rather than showing a misleading 0.
    updated = record_send(
        [], timestamp="t", subject="s", buttondown_id="1", region="r", mode="draft"
    )
    assert "pre_send_subscriber_count" not in updated[0]


def test_record_send_includes_subscriber_count_when_measured():
    updated = record_send(
        [],
        timestamp="t",
        subject="s",
        buttondown_id="1",
        region="r",
        mode="send",
        pre_send_subscriber_count=7,
    )
    assert updated[0]["pre_send_subscriber_count"] == 7


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


CHICAGO = ZoneInfo("America/Chicago")


def test_next_thursday_morning_from_a_monday_lands_the_same_week():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)  # Monday, 07:00 Chicago
    result = next_thursday_morning(now)
    assert (result.year, result.month, result.day) == (2026, 9, 17)  # that week's Thursday
    assert result.hour == 7
    assert result.tzinfo is not None


def test_next_thursday_morning_before_the_hour_returns_today():
    now = datetime(2026, 9, 17, 11, 0, tzinfo=timezone.utc)  # Thursday, 06:00 Chicago
    result = next_thursday_morning(now)
    assert (result.year, result.month, result.day) == (2026, 9, 17)


def test_next_thursday_morning_after_the_hour_rolls_to_next_week():
    now = datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc)  # Thursday, 08:00 Chicago
    result = next_thursday_morning(now)
    assert (result.year, result.month, result.day) == (2026, 9, 24)  # a week later


def test_next_thursday_morning_uses_local_day_not_utc_day():
    # 03:00 UTC Friday is still Thursday evening in Chicago (UTC-5 in
    # September) - the found bug this guards against is computing the
    # weekday from `now` directly instead of from the converted local
    # time, which would see "Friday" and roll a whole week later than it
    # should.
    now = datetime(2026, 9, 18, 3, 0, tzinfo=timezone.utc)
    assert now.astimezone(CHICAGO).strftime("%A") == "Thursday"
    result = next_thursday_morning(now)
    assert (result.year, result.month, result.day) == (2026, 9, 24)


def test_read_build_timestamp_parses_lastbuilddate(tmp_path):
    built_at = datetime(2026, 9, 17, 10, 30, tzinfo=timezone.utc)
    (tmp_path / "feed.xml").write_text(
        f"<rss><channel><lastBuildDate>{format_datetime(built_at)}</lastBuildDate></channel></rss>",
        encoding="utf-8",
    )
    assert read_build_timestamp(docs_dir=tmp_path) == built_at


def test_read_build_timestamp_missing_file_names_the_build_step(tmp_path):
    with pytest.raises(SendError, match="build_digest.py"):
        read_build_timestamp(docs_dir=tmp_path)


def test_read_build_timestamp_missing_element_raises(tmp_path):
    (tmp_path / "feed.xml").write_text("<rss><channel></channel></rss>", encoding="utf-8")
    with pytest.raises(SendError, match="lastBuildDate"):
        read_build_timestamp(docs_dir=tmp_path)


def test_read_build_timestamp_raises_cleanly_on_a_date_with_no_timezone(tmp_path):
    # parsedate_to_datetime doesn't raise on a date string with no UTC
    # offset - it silently returns a naive datetime. Unguarded, that
    # would surface later as a raw, uncaught TypeError ("naive minus
    # aware") from assert_build_is_fresh's subtraction, instead of the
    # clean SendError every other bad-input path here raises.
    (tmp_path / "feed.xml").write_text(
        "<rss><channel><lastBuildDate>Fri, 18 Sep 2026 13:00:29</lastBuildDate></channel></rss>",
        encoding="utf-8",
    )
    with pytest.raises(SendError, match="no timezone"):
        read_build_timestamp(docs_dir=tmp_path)


def test_assert_build_is_fresh_allows_a_recent_build():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    build_time = now - timedelta(days=1)
    assert_build_is_fresh(build_time, now)  # does not raise


def test_assert_build_is_fresh_rejects_a_stale_build():
    # ROADMAP.md item 111: the one signal available that a scheduled
    # rebuild was silently dropped rather than merely late.
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    build_time = now - timedelta(days=5)
    with pytest.raises(SendError, match="docs/feed.xml"):
        assert_build_is_fresh(build_time, now)


def test_read_weekend_event_count_combined_region_returns_total(tmp_path):
    path = tmp_path / "weekend_signal.json"
    path.write_text(
        '{"region_counts": {"mount-prospect-60056": 1, "palatine-60067": 0}, "total": 1}',
        encoding="utf-8",
    )
    assert read_weekend_event_count(COMBINED_REGION, path=path) == 1


def test_read_weekend_event_count_single_region_returns_its_own_count(tmp_path):
    path = tmp_path / "weekend_signal.json"
    path.write_text(
        '{"region_counts": {"mount-prospect-60056": 4, "palatine-60067": 0}, "total": 4}',
        encoding="utf-8",
    )
    assert read_weekend_event_count("palatine-60067", path=path) == 0
    assert read_weekend_event_count("mount-prospect-60056", path=path) == 4


def test_read_weekend_event_count_unknown_region_is_zero_not_a_crash(tmp_path):
    path = tmp_path / "weekend_signal.json"
    path.write_text('{"region_counts": {}, "total": 0}', encoding="utf-8")
    assert read_weekend_event_count("wheeling-60090", path=path) == 0


def test_read_weekend_event_count_missing_file_names_the_build_step(tmp_path):
    with pytest.raises(SendError, match="build_digest.py"):
        read_weekend_event_count(COMBINED_REGION, path=tmp_path / "weekend_signal.json")


def test_assert_weekend_is_not_thin_allows_the_floor_exactly():
    assert_weekend_is_not_thin(MIN_WEEKEND_EVENTS, COMBINED_REGION)  # does not raise


def test_assert_weekend_is_not_thin_rejects_below_the_floor():
    # ROADMAP.md item 172: the fortieth research pass's own example - a
    # combined issue with one event across five towns should not send.
    with pytest.raises(SendError, match="floor"):
        assert_weekend_is_not_thin(1, COMBINED_REGION)


def test_load_send_history_missing_file_returns_empty_list(tmp_path):
    assert load_send_history(tmp_path / "nope.json") == []


def test_load_send_history_corrupt_file_returns_empty_list(tmp_path):
    path = tmp_path / "send_history.json"
    path.write_text("not json", encoding="utf-8")
    assert load_send_history(path) == []


def test_record_send_appends_without_mutating_the_original():
    # ROADMAP.md item 114: the actual record item 111's staleness guard
    # couldn't provide, because build-digest.yml rebuilding fine all day
    # said nothing about whether a send job ever ran at all.
    original = [{"timestamp": "old"}]
    updated = record_send(
        original, timestamp="2026-09-17T18:33:00+00:00", subject="This weekend",
        buttondown_id="abc123", region="combined", mode="schedule",
    )
    assert original == [{"timestamp": "old"}]  # not mutated in place
    assert updated == [
        {"timestamp": "old"},
        {
            "timestamp": "2026-09-17T18:33:00+00:00",
            "subject": "This weekend",
            "buttondown_id": "abc123",
            "region": "combined",
            "mode": "schedule",
        },
    ]


def test_save_and_load_send_history_round_trips(tmp_path):
    path = tmp_path / "send_history.json"
    history = record_send(
        [], timestamp="2026-09-17T18:33:00+00:00", subject="Subj",
        buttondown_id="abc123", region="combined", mode="send",
    )
    save_send_history(history, path)
    assert load_send_history(path) == history


def test_save_send_history_creates_the_parent_directory(tmp_path):
    path = tmp_path / "nested" / "send_history.json"
    save_send_history([{"timestamp": "x"}], path)
    assert path.exists()
