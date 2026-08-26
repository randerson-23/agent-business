# 60056 Weekly

An automated hyperlocal digest for Mount Prospect, IL (ZIP 60056): village
news, library events, and park district programs, aggregated into one page
every week — monetized with a single local-business sponsor slot per issue.

Built for low ongoing time investment (see [`BUSINESS_PLAN.md`](BUSINESS_PLAN.md)
for the full rationale and why this idea fits ZIP 60056 specifically).

## How it works

1. `scripts/fetchers.py` — fail-soft fetchers for RSS, ICS (iCalendar), and
   a best-effort HTML events scrape. Any source that fails to fetch is
   skipped and logged; it never breaks the build.
2. `scripts/build_digest.py` — pulls sources from `config/sources.yaml`,
   resolves the active sponsor from `config/sponsors.yaml`, and renders
   `templates/digest.html.j2` into `docs/index.html` (plus a dated copy in
   `docs/archive/`).
3. `.github/workflows/build-digest.yml` — runs the pipeline on a weekly
   cron (Mondays) and commits the generated `docs/` output, which is served
   by GitHub Pages. `workflow_dispatch` lets you trigger a rebuild manually.
4. `.github/workflows/tests.yml` — runs the test suite on every PR and push
   to `main`.

## Local development

```bash
pip install -r requirements.txt
python scripts/build_digest.py     # writes docs/index.html
pip install pytest
python -m pytest tests/ -q
```

## One-time setup checklist

See [`SETUP.md`](SETUP.md) — a short, human-in-the-loop checklist (verify
feed URLs, enable GitHub Pages) that takes about 15 minutes.

## Selling sponsor spots

See [`SPONSOR_KIT.md`](SPONSOR_KIT.md) for pricing/positioning and
[`OUTREACH_TEMPLATES.md`](OUTREACH_TEMPLATES.md) for ready-to-send emails.
To activate a paid sponsor, edit `config/sponsors.yaml`.
