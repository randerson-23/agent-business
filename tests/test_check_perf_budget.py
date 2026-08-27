import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_perf_budget import MAX_INLINE_JS_BYTES, inline_js_bytes  # noqa: E402


def test_counts_plain_script_blocks():
    html = "<html><body><script>const x = 1;</script></body></html>"
    assert inline_js_bytes(html) == len(b"const x = 1;")


def test_ignores_json_ld_blocks():
    html = (
        '<script type="application/ld+json">{"@type": "Event"}</script>'
        "<script>doStuff();</script>"
    )
    assert inline_js_bytes(html) == len(b"doStuff();")


def test_sums_multiple_script_blocks():
    html = "<script>a();</script><p>text</p><script>bbbb();</script>"
    assert inline_js_bytes(html) == len(b"a();") + len(b"bbbb();")


def test_no_scripts_is_zero():
    assert inline_js_bytes("<html><body>hi</body></html>") == 0


def test_budget_has_headroom_over_current_pages():
    assert MAX_INLINE_JS_BYTES > 7135
