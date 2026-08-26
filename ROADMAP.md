# Roadmap — from "60056 Weekly" to a multi-ZIP trip/weekend planner

This is the continuity doc for autonomous, chunked iteration (this repo is
being built by an agent on a fast recurring loop — read this file first on
each pickup to see current phase and what's next, and update it as phases
complete).

## Vision

Start with one hyperlocal digest (Mount Prospect, IL / 60056) and grow it
into a small network of ZIP-code pages that can be strung together —
useful both for locals planning a weekend and for visitors planning a trip
across a few nearby towns. Same monetization model (local sponsor slot per
region) scales with it.

Design goals for the site itself (from the 2026-08-26 direction):
- Fast-loading, good-looking, easy to navigate.
- Filterable at a glance: kid-friendly, dog-friendly, free, indoor/outdoor,
  etc.
- Enough info in the card itself (date, time, tags, one-line description)
  that a reader mostly doesn't need to click through to know if an event
  is for them.

## Phases

### Phase 0 — Single-ZIP MVP ✅ done
Fetchers (RSS/ICS/HTML), digest builder, GitHub Pages, sponsor kit,
outreach templates, tests. Live for 60056.

### Phase 1 — Infra hardening (in progress)
Problem: hand-built commits that include the *generated* `docs/` output
keep colliding with the scheduled `build-digest.yml` workflow's own
auto-commits (hit this twice already). At a 10-minute iteration cadence
this would happen constantly.

Fix: generated site output is CI's job, not a feature branch's. Working
practice from here on: never stage `docs/` changes in a feature-branch
commit — run `git restore docs/` (or just don't `git add` it) before
committing. The `build-digest.yml` workflow remains the only thing that
commits `docs/` to `main`, triggered by pushes touching
`scripts/**`/`templates/**`/`config/**` or the weekly cron.

### Phase 2 — Multi-region data model
`config/sources.yaml` → `config/regions/<region-id>.yaml`, one file per
ZIP/region, each with region metadata (id, name, city, state, zip,
timezone) plus its own `sources` and `evergreen` list. Build script
iterates every file in `config/regions/`.

### Phase 3 — Event tagging + at-a-glance info
Heuristic keyword-based tagging (kid-friendly, dog-friendly, free,
indoor/outdoor, etc.) applied to fetched + evergreen items. Best-effort by
design — wrong or missing tags fail soft, same philosophy as the fetchers.
Curated sources (evergreen entries) can set tags explicitly in YAML.

### Phase 4 — Redesign: cards, badges, client-side filters
Card-based layout per event: date/time, tag badges, one-line detail,
"View source" link. Vanilla-JS filter bar (no framework/build step, so it
stays fast) toggling tags client-side. A hub page listing all regions once
there's more than one.

### Phase 5 — Second region (proves the architecture)
Add one more ZIP as a real second data point, not a copy-paste placeholder
— validates the region config format and the hub page before scaling
further.

### Phase 6 — Per-region sponsor rotation
Extend `config/sponsors.yaml` to be keyed by region once there's more than
one region worth selling into. Low priority until Phase 5 is proven.

## Working agreements for autonomous iteration

- Most 10-minute ticks should be small, tested, and *not* every one needs
  to end in a merged PR — batch a coherent slice of work, ship it when it's
  coherent and tested, skip the ship step (silently, or with a one-line
  note) when mid-slice.
- Always run `python -m pytest tests/ -q` and `python scripts/build_digest.py`
  before committing.
- Never hand-commit `docs/` output (see Phase 1).
- Don't add speculative complexity ahead of an actual phase — this is a
  real small business, not a demo.
- No human approval needed to merge your own PRs in this repo — squash
  merge once tests pass locally.
