# Local Weekend & Trip Planner

An automated, multi-ZIP local events site: village/city news, library
events, and park district programs, aggregated by region, filterable by
tags (kid-friendly, dog-friendly, free, indoor/outdoor, ...), monetized
with a local-business sponsor slot per region. Started as "60056 Weekly"
for Mount Prospect, IL — see [`ROADMAP.md`](ROADMAP.md) for where it's
headed (stringing together multiple ZIPs for weekend/trip planning) and
[`BUSINESS_PLAN.md`](BUSINESS_PLAN.md) for the original rationale.

## How it works

1. `config/regions/*.yaml` — one file per region (ZIP code), each with its
   own metadata (name, zip, state, timezone) plus its own data `sources`
   and curated `evergreen` entries. Add a new region by adding a new file
   here.
2. `scripts/fetchers.py` — fail-soft fetchers for RSS, ICS (iCalendar), and
   a best-effort HTML listing-page scrape (events *or* news, via a
   per-source `keywords` override). Any source that fails to fetch is
   skipped and logged; it never breaks the build.
3. `scripts/tagging.py` — best-effort keyword-based tag inference (e.g.
   "storytime" → kid-friendly) for fetched events; curated `evergreen`
   entries can set `tags` explicitly in YAML instead.
4. `scripts/build_digest.py` — loads every region, fetches + tags its
   events, and renders `templates/region.html.j2` into
   `docs/<region-id>/index.html`, plus `templates/hub.html.j2` into
   `docs/index.html` (a picker page listing all regions).
5. `.github/workflows/build-digest.yml` — runs the pipeline on a weekly
   cron (Mondays) and on every push to `main` touching
   `scripts/`/`templates/`/`config/`, committing the generated `docs/`
   output, which GitHub Pages serves. `workflow_dispatch` lets you trigger
   a rebuild manually.
6. `.github/workflows/tests.yml` — runs the test suite on every PR and push
   to `main`.

**Generated `docs/` output is CI's job, not a feature branch's** — see
`ROADMAP.md`'s "Working agreements" section. Don't hand-commit it; the
workflow above regenerates and commits it automatically after every merge.

## Local development

```bash
pip install -r requirements.txt
python scripts/build_digest.py     # writes docs/index.html + docs/<region>/index.html
pip install pytest
python -m pytest tests/ -q
```

Before committing, run `git restore docs/` (and remove any newly-created
`docs/<region-id>/` directories) so your commit only touches source files.

## One-time setup checklist

See [`SETUP.md`](SETUP.md) — a short, human-in-the-loop checklist (verify
feed URLs, enable GitHub Pages) that takes about 15 minutes.

## Selling sponsor spots

See [`SPONSOR_KIT.md`](SPONSOR_KIT.md) for pricing/positioning and
[`OUTREACH_TEMPLATES.md`](OUTREACH_TEMPLATES.md) for ready-to-send emails.
To activate a paid sponsor for a region, edit `config/sponsors.yaml`.
