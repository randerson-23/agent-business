"""ROADMAP.md item 219: reject any "<Weekday>, <Month> <day>" whose weekday
doesn't match its year.

Search results kept presenting 2025 dates as 2026 (three of four in one
research pass), and the repo's own config once carried "Friday, October 31"
for a year in which it is a Saturday. The weekday is the cheap, mechanical
way to catch that before it ships. A date a person typed into config, a
template or a pitch is only as good as its weekday.
"""

import re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The season the repo is currently working in. A weekday-date with no year
# anywhere on its line is checked against this one; bump it each January.
DEFAULT_YEAR = 2026

# Text a person writes dates into. ROADMAP.md is deliberately left out: it
# quotes wrong dates on purpose when it explains what the check catches.
CHECKED_GLOBS = (
    "config/**/*.yaml",
    "templates/*.j2",
    "SEASONAL_CALENDAR.md",
    "SPONSOR_KIT.md",
    "OUTREACH_TEMPLATES.md",
)

WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTH_ABBR = {m[:3]: i for i, m in enumerate(MONTHS.split("|"), start=1)}

DATE_RE = re.compile(
    rf"(?<![-–/])\b(?P<weekday>{WEEKDAYS}),?\s+"
    rf"(?P<month>{MONTHS}|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+"
    rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*[-–]\s*\d)(?:,?\s+(?P<year>20\d\d))?"
)
YEAR_RE = re.compile(r"\b(20\d\d)\b")


def _month_number(name: str) -> int:
    return MONTH_ABBR[name[:3]]


def weekday_problems(text: str, label: str, default_year: int = DEFAULT_YEAR) -> list[str]:
    """One message per weekday-date in `text` whose weekday is wrong for every
    year it could mean: the year written in the date itself, else any year on
    the same line (a comment quoting "2025's Saturday, Oct. 25th; 2026's is
    Saturday, October 24"), else `default_year`."""
    problems = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in DATE_RE.finditer(line):
            if m.group("year"):
                years = [int(m.group("year"))]
            else:
                years = sorted({int(y) for y in YEAR_RE.findall(line)}) or [default_year]
            month, day = _month_number(m.group("month")), int(m.group("day"))
            actual = []
            for year in years:
                try:
                    actual.append(date(year, month, day).strftime("%A"))
                except ValueError:  # e.g. February 30
                    actual.append("(no such date)")
            if m.group("weekday") not in actual:
                problems.append(
                    f"{label}:{lineno}: '{m.group(0).strip()}' - "
                    + ", ".join(f"{y} is a {a}" for y, a in zip(years, actual))
                )
    return problems


def test_weekday_check_catches_the_original_mistake():
    # Item 218's config comment said "Friday, October 31" for 2026.
    assert weekday_problems("hours: Friday, October 31", "x")
    assert not weekday_problems("hours: Saturday, October 31", "x")


def test_weekday_check_reads_the_year_from_the_string_or_the_line():
    assert not weekday_problems("Saturday, October 25, 2025", "x")
    assert weekday_problems("Saturday, October 25, 2026", "x")
    # A comment quoting two years passes when the weekday fits either.
    assert not weekday_problems('reads as 2025 ("Saturday, Oct. 25th"); 2026 is different', "x")
    # No year on the line: the default season applies.
    assert weekday_problems("Saturday, October 25th", "x")


def test_weekday_check_skips_ranges_and_bad_dates():
    assert not weekday_problems("runs Fri-Sat, October 2-3, 2026", "x")
    assert not weekday_problems("Friday, October 2-3, 2026", "x")
    assert weekday_problems("Saturday, February 30, 2026", "x")


def test_every_weekday_date_in_config_and_docs_matches_its_year():
    problems = []
    checked = 0
    for pattern in CHECKED_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            checked += len(DATE_RE.findall(text))
            problems += weekday_problems(text, str(path.relative_to(ROOT)))
    assert checked >= 5, "the scan found almost nothing; did a glob stop matching?"
    assert not problems, "weekday does not match its year:\n" + "\n".join(problems)
