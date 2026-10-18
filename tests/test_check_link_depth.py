import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_link_depth as cld  # noqa: E402

B = cld.BASE


def site(tmp_path, pages, sitemap):
    for path, links in pages.items():
        f = tmp_path / path / "index.html" if path else tmp_path / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("".join(f'<a href="{l}">x</a>' for l in links), encoding="utf-8")
    (tmp_path / "sitemap.xml").write_text("".join(f"<loc>{B}{p}</loc>" for p in sitemap), encoding="utf-8")


def test_a_page_three_clicks_deep_or_unlinked_is_reported(tmp_path):
    site(tmp_path, {"": ["/a/"], "a": ["/b/"], "b": ["/c/"], "c": [], "orphan": []}, ["", "a/", "b/", "c/", "orphan/"])
    assert cld.too_deep(tmp_path) == [(B + "c/", 3), (B + "orphan/", None)]


def test_relative_absolute_and_fragment_links_all_count(tmp_path):
    site(tmp_path, {"": ["a/#top", B + "b/?x=1"], "a": ["c/"], "b": [], "a/c": []}, ["", "a/", "b/", "a/c/"])
    assert cld.too_deep(tmp_path) == []
