# Roadmap — from "60056 Weekly" to a multi-ZIP trip/weekend planner

This is the continuity doc for autonomous, chunked iteration (this repo is
being built by an agent on a fast recurring loop — read this file first on
each pickup to see current phase and what's next, and update it as phases
complete).

Two loops write to this file:
- an **hourly build loop** that implements the next phase item and ships PRs;
- a **6-hourly research loop** (added 2026-08-27) that re-reads
  `BUSINESS_PLAN.md`, reviews competitor sites, and refreshes the idea
  backlog in **Phase 11**. It only edits this file — it never implements.

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

### Phase 7 — Visual redesign: look modern enough to pitch sponsors (first slice ✅ done, PR #8)
Feedback (2026-08-26): the current card/badge design (Phase 4) reads flat
and dated — "more like a Craigslist site." Sponsors won't take a media kit
seriously if the site looks like a classifieds board, so this jumped ahead
of the other Phase 7 candidates.

Shipped in the first slice (PR #8):
- ✅ Typography: Fraunces (headings) + Inter (body) via Google Fonts.
- ✅ Elevation: real card shadows + hover lift, refined spacing/radius.
- ✅ Hero band (gradient + inline-SVG map-pin mark) on hub + region pages.
- ✅ Color: tag badges now use per-tag `hue` (see `tagging.TAG_DISPLAY`)
  instead of one flat green for every tag.
- ✅ Favicon (inline SVG data URI, same pin mark).
- ✅ Open Graph + Twitter Card *text* meta tags (title/description).
- ✅ Mobile pass verified with a Playwright screenshot at 390px.
- ✅ Bonus fix found along the way: ICS text wasn't RFC 5545-unescaped,
  so literal `\n`/`\,` were leaking into card text in production.

Still open from the original wish list (do later, not blocking):
- Open Graph **image** (needs an actual image asset — text-only OG tags
  shipped for now; ties to Phase 9 once there's a real domain/brand to
  design one around).
- A logo/wordmark beyond the generic pin mark — deliberately deferred
  since Phase 9's name/domain choice isn't made yet and a wordmark should
  match the eventual name, not be redone later.
- Consider a proper inline-SVG icon set instead of emoji tag badges, if
  emoji rendering ever looks off on a real device (untested outside this
  sandbox's Chromium render).

### Phase 8 — Distance from the user, per event (region-level v1 ✅ done, PR #12)
Requested 2026-08-26: show how far away each event/region is from the
person viewing the site.

Shipped (v1, region-level — the honest starting point given the data we
actually have):
- ✅ Village-center lat/lon added to each region's config.
- ✅ Client-side only: a "Show distance from me" button (browser
  Geolocation API) computes straight-line (haversine) distance to each
  region's center in plain JS, shown on the hub page's region cards
  ("≈4.5 mi away") and re-sorts them nearest-first.
- ✅ Manual-ZIP fallback for denied/unavailable geolocation (a small
  hardcoded table of nearby Chicago NW-suburb ZIPs).
- ✅ Privacy note in the UI: computed entirely in the browser, never sent
  anywhere.
- Verified with Playwright (manual-ZIP path, and the denial path via an
  explicit denied-permission browser context — a plain click hangs in
  this sandbox because file:// isn't a secure context for Geolocation
  and headless has no UI for the native prompt; GitHub Pages serves over
  https, where it resolves normally). Not yet checked in a real browser
  on the live site — worth a manual click-through once convenient.

Later (bigger lift, not this phase): per-event distance would need actual
venue coordinates, which means geocoding addresses extracted from event
listings during the build (most current sources don't expose a structured
address at all, only a title/detail blob) — likely a free-tier geocoding
API called during `build_digest.py`, cached to stay within rate limits.
Worth doing once regions multiply enough that "which specific event is
closest" actually matters more than "which town is closest."

### Phase 9 — SEO plan + domain name (technical slice ✅ done, PR #10; domain still open)
Requested 2026-08-26.

SEO technical tasks — done (PR #10):
- ✅ Open Graph + Twitter Card *text* meta tags (image still pending, see
  Phase 7's notes — needs a real image asset).
- ✅ `robots.txt` + generated `sitemap.xml` (region pages + hub), produced
  by `build_digest.py` alongside the HTML.
- ✅ JSON-LD structured data (`schema.org/Event`) on every fetched event —
  the single highest-leverage SEO move for a site like this, makes events
  eligible for Google's event rich results. Not yet validated against
  Google's actual Rich Results Test with live data (worth doing once real
  events are flowing through both regions).
- ✅ Canonical `<link>` tags on both page types, driven by one
  `SITE_BASE_URL` constant in `build_digest.py` — currently the GitHub
  Pages URL, update it in one place once a real domain is registered.
- Core Web Vitals: still no JS framework, nothing added that should hurt
  this — not separately measured/verified yet.

Still open (needs a human):

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

### Phase 10 — Later / parking lot (7-9's first slices are done — pick from here next)
- A third region, to keep validating the architecture holds (e.g. Des
  Plaines, Elk Grove Village, or Schaumburg — all near 60056/60005). Also
  gives Phase 8's distance/sort feature more to actually sort.
- Fix any Phase 5 gaps found once real Arlington Heights data comes in.
- Revisit whether an archive/history feature is worth it (dropped in Phase
  1 for simplicity) — only if a real user asks for it.
- Per-event (not just per-region) distance — see Phase 8's "later" note.

### Phase 11 — Competitor-informed idea backlog (fed by a 6-hourly research loop)

A second scheduled loop (separate from the hourly build loop) researches the
business plan + competitor sites every 6 hours and appends/refreshes ideas
here. **This section is the implementation loop's queue** — when Phases 5-10
have nothing pressing, pick the highest unclaimed `P1` item below. Mark items
`✅ done (PR #N)` in place rather than deleting them, so the research loop
doesn't re-suggest something already shipped.

#### Competitors reviewed (2026-08-27)

| Site | What it is | Worth stealing |
|---|---|---|
| **Do312** (DoStuff Media) | Chicago events, the best-designed thing in this space | URL-addressable date/category views (`/events/today`, `/events/weekend`, `/free`) instead of client-side-only filters |
| **Macaroni KID** | ~500 hyperlocal family newsletters + sites, publisher-run, sponsor-funded | Seasonal *guides* (summer camps, "kids eat free", Halloween) as the flagship monetizable product; business directory; weekly + monthly calendar views |
| **6AM City** | 400+ local newsletters, $9.5M rev, profitable in 2026 | **Self-service ad platform** — they built it because low-average-order-value local sponsors don't justify sales time. Directly targets this business's #1 constraint |
| **Axios Local** | Local newsletter network, local-advertiser funded | Newsletter-first: the list is the asset, the site is the funnel |
| **Patch** | Hyperlocal news + community calendar | User-submitted events, business directory, classifieds — community supplies the content |
| **Eventbrite / AllEvents / Meetup** | Rank #1 for "things to do in Mount Prospect this weekend" today | They own the query — but they only list *ticketed/commercial* events |

**The gap that justifies this business:** every competitor that ranks for
"things to do in Mount Prospect this weekend" lists ticketed commercial
events. None of them aggregate the village + public library + park district
civic feeds — which for a family-dense suburb is where most of the actual
weekend is. That is the moat, and the site should say so out loud (a one-line
"what's in here" statement on the hub, above the region grid).

#### P1 — highest leverage, do these first

1. **Date-scoped, linkable views: `/this-weekend`, `/today`, `/free`.**
   Filtering today is client-side only, so nothing is shareable, bookmarkable
   or indexable — a filtered view has no URL. Pre-render static pages per
   region (`docs/<region>/this-weekend/`) plus a hub-level "This weekend
   near you" that merges all regions. Biggest single SEO + UX win available,
   and it finally makes the site's name literal. Depends on item 4.

2. **"Add to calendar" on every event card** — an `.ics` download plus a
   Google Calendar link. ICS is already being parsed on the way in, so the
   data is there; this is the highest-value-per-line-of-code item on the
   list. Turns a card from something you read into something you act on,
   which is the "enough info in the card" design goal taken one step further.

3. **Self-serve sponsor checkout (`/sponsor` page).** 6AM City's core lesson:
   they automated ad sales because chasing $50 local orders by hand doesn't
   pay for the hours. Replace "email me for the media kit" with a real page:
   pricing table, live per-region availability ("Week of Sep 8 — open"), and
   a Stripe Payment Link. `config/sponsors.yaml` already has the structure to
   render availability from. This is the single biggest lever on the
   near-zero-weekly-hours constraint in `BUSINESS_PLAN.md` — everything else
   on this list is automated already; sponsor sales is the one manual step
   left.

#### P2

4. **Real datetime normalization + a structured-data coverage stat.**
   `parse_iso_datetime` in `build_digest.py` handles RFC-2822 and ICS
   formats, and correctly returns `None` rather than guessing — but HTML-
   scraped listings ("Sat, Sep 6 · 10:00 AM") fall through, and an Event
   without `startDate` is not eligible for Google's event rich results at
   all. Extend the parser for common human formats and print a coverage line
   at build time (`42/58 events have machine-readable start dates`) so
   regressions are visible. Unblocks item 1.

5. **Seasonal guides** (`guides:` list in region YAML → generated pages).
   Macaroni KID's most-monetized format: summer camps, where kids eat free,
   Halloween trick-or-treat hours, holiday light displays, pool/splash-pad
   hours. Evergreen SEO that doesn't expire every Monday, and it's the
   placement local sponsors most want to be inside. Fits the existing
   `evergreen` data model closely.

6. **Local business directory per region.** Both Patch and Macaroni KID run
   one. It's the natural home for the $30/month Community Partner tier and
   gives that tier a permanent page instead of a footer logo that scrolls
   past — easier to sell and easier to renew.

7. **Dark mode via `prefers-color-scheme`.** 2026 baseline expectation
   (~70% of modern sites ship it). The palette is already CSS-custom-property
   driven in both templates, so this is a token block, not a redesign — one
   of the cheapest "looks modern" wins on the list.

#### P3 — design polish (the "modern and impressive" goal)

8. **Bento-grid hub layout + a "This weekend at a glance" block.** Bento
   grids are the dominant 2026 editorial layout; the hub's uniform 3-up card
   grid reads generic next to one. Asymmetric blocks — a big "this weekend"
   tile, smaller region tiles, a stat tile ("3 towns · 58 events this week") —
   would make the hub look designed rather than generated.

9. **Scroll-reveal motion** via `IntersectionObserver` + CSS transitions,
   gated on `prefers-reduced-motion`. Hardware-accelerated properties only,
   no framework, no measurable Core Web Vitals cost. The cheapest available
   difference between "a static page" and "a designed site" on first scroll.

10. **Accessibility pass.** Cited across 2026 design guidance as credibility
    rather than compliance. Concretely here: visible focus rings on the
    filter chips (currently `aria-pressed` buttons with no focus style),
    contrast audit of `--muted` (#5c6b63) and the tag badge hues on white,
    keyboard operability of the distance bar, and an `aria-live` region so
    filter results are announced.

11. **Weather on the weekend view** — Open-Meteo is free and needs no API
    key. The indoor/outdoor tag only becomes genuinely useful next to
    Saturday's forecast, and "38° and raining — here are 9 indoor picks" is
    the kind of touch that gets a site shared.

12. **Email capture.** The entire competitive set (Macaroni KID, 6AM City,
    Axios Local, Patch) is newsletter-first, because the list is the asset
    and the site is the funnel. A static-site-compatible embed (Buttondown
    free tier) costs nothing, and a real subscriber count roughly multiplies
    what a sponsor slot is worth. `BUSINESS_PLAN.md` already parks this as
    step 7 — the competitive research says pull it forward, it's the number
    a sponsor asks for first.

13. **User-submitted events** (Patch's model — let the community supply the
    content). A GitHub Issue Form template → a small workflow that opens a PR
    adding the entry to a region's `evergreen`/curated list, so the owner's
    involvement stays at "merge or don't."

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
- Phase 11 is the idea queue, not a spec. Items there are researched
  suggestions, not commitments — implement the ones that serve the business
  plan's constraints (near-zero owner time, sponsor-sellable, no framework
  bloat) and mark the rest `skipped —` with a one-line reason so the
  research loop stops re-suggesting them.
- No human approval needed to merge your own PRs in this repo — squash
  merge once tests pass locally.
