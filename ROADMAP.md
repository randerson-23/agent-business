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

Design goals for the site itself (from the 2026-08-26 direction, refined
same day after seeing the first pass):
- Fast-loading, good-looking, easy to navigate — and modern enough that a
  local business owner takes the sponsor pitch seriously (see Phase 7; the
  first pass reads too much like a classifieds board for that).
- Filterable at a glance: kid-friendly, dog-friendly, free, indoor/outdoor,
  etc.
- Enough info in the card itself (date, time, tags, one-line description)
  that a reader mostly doesn't need to click through to know if an event
  is for them.
- Distance from the viewer, so "what's nearby" is answerable at a glance
  too (see Phase 8).

## Phases

### Phase 0 — Single-ZIP MVP ✅ done
Fetchers (RSS/ICS/HTML), digest builder, GitHub Pages, sponsor kit,
outreach templates, tests. Live for 60056.

### Phase 1 — Infra hardening ✅ done
Problem: hand-built commits that include the *generated* `docs/` output
kept colliding with the scheduled `build-digest.yml` workflow's own
auto-commits (hit this twice). Fix: generated site output is CI's job, not
a feature branch's — see "Working agreements" below. Still watch for this;
it's a practice, not something code enforces.

### Phase 2 — Multi-region data model ✅ done
`config/sources.yaml` → `config/regions/<region-id>.yaml`, one file per
ZIP/region, each with region metadata (id, name, city, state, zip,
timezone) plus its own `sources` and `evergreen` list. Build script
iterates every file in `config/regions/`.

### Phase 3 — Event tagging + at-a-glance info ✅ done
Heuristic keyword-based tagging (kid-friendly, dog-friendly, free,
indoor/outdoor, etc.) applied to fetched + evergreen items. Best-effort by
design — wrong or missing tags fail soft, same philosophy as the fetchers.
Curated sources (evergreen entries) can set tags explicitly in YAML.

### Phase 4 — Redesign: cards, badges, client-side filters ✅ done
Card-based layout per event: date/time, tag badges, one-line detail,
"View source" link. Vanilla-JS filter bar (no framework/build step, so it
stays fast) toggling tags client-side. Hub page lists all regions.

### Phase 5 — Second region (proves the architecture) ✅ done
Added Arlington Heights (60005) as a real second data point (village news,
library events, park district) — see PR #5. Also generalized
`fetch_html_events`'s "detail link" signal into a per-source
`detail_link_pattern` config override, instead of a hardcoded pattern.
**Not yet verified against a live build** — check the next scheduled
run's output for real Arlington Heights content, especially Village News
(should work first-try thanks to `detail_link_pattern`) and Library Events
(still on keyword-fallback, may need the same fix Mount Prospect's library
needed).

### Phase 6 — Per-region sponsor rotation (structure done, selling not started)
`config/sponsors.yaml` is already keyed by region (done alongside Phase 2).
What's left is actually selling into each region — see `SPONSOR_KIT.md` /
`OUTREACH_TEMPLATES.md`, which are per-business-owner outreach, outside
what this loop can automate.

### Phase 7 — Visual redesign: look modern enough to pitch sponsors (not started, high priority)
Feedback (2026-08-26): the current card/badge design (Phase 4) reads flat
and dated — "more like a Craigslist site." Sponsors won't take a media kit
seriously if the site looks like a classifieds board, so this jumps ahead
of the other Phase 7 candidates below.

Concrete directions (not all required for a first pass — ship in slices):
- Typographic hierarchy: bring in one distinctive heading/display font
  (Google Fonts, real `<link>` — this is a normal website, not a sandboxed
  artifact, so no CDN restriction applies here) layered over the existing
  system-font body text, with a proper fallback stack.
- Elevation & depth: real card shadows and a hover lift, refined spacing/
  radius scale — right now cards are just a thin border, which reads flat.
- A real hero band on the hub page and each region page: gradient or
  subtle pattern background, larger headline, maybe a small inline SVG
  motif (skyline/map-pin) instead of plain text on the flat page background.
- Iconography: emoji tag badges (Phase 3) render inconsistently across
  OS/browsers and look unpolished at this scale — consider a small
  consistent inline-SVG icon set instead, or at least pair emoji with more
  refined pill/chip styling.
- A simple logo/wordmark and a real favicon (currently none) — ties into
  Phase 9's domain/brand work, do them together if convenient.
- Open Graph image + meta tags so shared links preview well (also an SEO
  item, see Phase 9).
- Explicit mobile pass: the sticky filter bar and card grid need to hold
  up on a phone, since "checking what's on this weekend" is a mobile use
  case first.
Acceptance: a before/after screenshot comparison (Playwright is available
in this environment for local rendering/screenshots) before calling this
phase done — "looks more modern" is subjective, so get a visual to judge
it by rather than just shipping CSS changes blind.

### Phase 8 — Distance from the user, per event (not started)
Requested 2026-08-26: show how far away each event/region is from the
person viewing the site.

Approach (v1, region-level — the honest starting point given the data we
actually have):
- Add lat/lon to each region's config (village-center coordinates are easy
  to source and good enough for a first version; individual events don't
  have structured addresses from the fetchers today, so per-venue distance
  isn't available yet without a geocoding step — see "later" below).
- Client-side only (this stays a static site, no server to do this work):
  use the browser Geolocation API to get the viewer's position, compute
  straight-line (haversine) distance to each region's center in plain JS,
  and show it on the hub page's region cards (e.g. "~4 mi away"), with an
  option to sort regions nearest-first.
- Graceful fallback for denied/unavailable geolocation: a manual "enter
  your ZIP" input that maps to a rough lat/lon (even a small hardcoded
  table of nearby ZIPs would do for v1) rather than just hiding the
  feature.
- Be upfront in the UI that it's regional distance, not per-venue, until
  the "later" item below lands — don't overclaim precision.
- Privacy note: compute entirely in the browser, never send the viewer's
  location anywhere (there's no backend to send it to) — worth a line in
  the UI so people trust the feature.

Later (bigger lift, not this phase): per-event distance would need actual
venue coordinates, which means geocoding addresses extracted from event
listings during the build (most current sources don't expose a structured
address at all, only a title/detail blob) — likely a free-tier geocoding
API called during `build_digest.py`, cached to stay within rate limits.
Worth doing once regions multiply enough that "which specific event is
closest" actually matters more than "which town is closest."

### Phase 9 — SEO plan + domain name (not started)
Requested 2026-08-26.

SEO technical tasks (in-repo, no human needed, can ship incrementally):
- Open Graph + Twitter Card meta tags per page (ties into Phase 7's OG
  image) so shared links preview well on social/messaging apps.
- `robots.txt` + a generated `sitemap.xml` (region pages + hub), produced
  by `build_digest.py` alongside the HTML.
- JSON-LD structured data (`schema.org/Event`) on each event card — the
  single highest-leverage SEO move for a site like this, since it makes
  events eligible for Google's event rich results.
- Canonical URLs — revisit once a real domain exists (currently served
  from a GitHub Pages subpath, `randerson-23.github.io/agent-business/`).
- Keep Core Web Vitals fast as the redesign (Phase 7) adds weight: no JS
  framework, defer/inline appropriately, optimize any images before they
  ship.

Domain name candidates (research only — I can't register a domain myself,
that's a paid human action; availability below is **unverified**, check a
registrar before committing):
- `zipscout.com`
- `weekendscout.com`
- `nearbyzip.com`
- `townhopper.com`
- `scoutnearby.com`
- `ziptripper.com`
- `ourweekendguide.com`
- `localloopil.com` (ties the brand to Illinois specifically — good for
  local SEO/trust now, but limits the story if this ever expands beyond
  IL; the others are geography-agnostic)

A short, geography-agnostic `.com` is the safer bet for a sponsor-facing
brand that might expand past the Chicago suburbs — lean toward
`zipscout.com` / `weekendscout.com` / `scoutnearby.com` unless a human
picks otherwise. Once a name is chosen and registered: point it at GitHub
Pages via a custom domain (repo Settings → Pages → Custom domain), which
also needs a DNS change only the domain owner can make.

### Phase 10 — Later / parking lot (pick from here once 7-9 are done)
- A third region, to keep validating the architecture holds (e.g. Des
  Plaines, Elk Grove Village, or Schaumburg — all near 60056/60005). Also
  gives Phase 8's distance/sort feature more to actually sort.
- Fix any Phase 5 gaps found once real Arlington Heights data comes in.
- Revisit whether an archive/history feature is worth it (dropped in Phase
  1 for simplicity) — only if a real user asks for it.
- Per-event (not just per-region) distance — see Phase 8's "later" note.

## Working agreements for autonomous iteration

- Cadence is hourly (the platform's durable scheduler has a 1-hour floor;
  a faster session-local scheduler was tried and doesn't survive this
  environment's container lifecycle, confirmed empty after the fact — see
  chat history 2026-08-26). Not every firing needs to end in a merged PR —
  batch a coherent slice of work, ship it when it's coherent and tested,
  skip the ship step (with a one-line note) when mid-slice.
- Always run `python -m pytest tests/ -q` and `python scripts/build_digest.py`
  before committing.
- Never hand-commit `docs/` output — run `git restore docs/` and remove any
  newly-created `docs/<region-id>/` directories before staging.
- Don't add speculative complexity ahead of an actual phase — this is a
  real small business, not a demo.
- No human approval needed to merge your own PRs in this repo — squash
  merge once tests pass locally.
