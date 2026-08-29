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

1. ✅ done (PR #19, hub-level fast-follow PR #21; widened to include Friday
   2026-08-28 per the owner's explicit request) — **Date-scoped, linkable
   views: `/this-weekend`, `/today`, `/free`.** Each region has three
   extra static pages, distinct `<title>`/description per view, and a
   small nav row. `docs/this-weekend/` merges every region's weekend
   events into one page (grouped by region, regions with nothing dated
   simply omitted), linked from the hub via a callout banner. Scoped to
   events with a resolved `date_iso` (item 4 closed the HTML-scraped-source
   gap this note used to flag). `weekend_dates()` now returns
   Friday/Saturday/Sunday (was Sat/Sun only) - most people's weekend
   starts Friday evening after work, not Saturday morning. Weather,
   `filter_events_by_dates`, the date-range display, and the FAQ's
   "Friday-Sunday" copy all updated to match; `format_date_range` needed
   no change since it already took any two dates.

2. ✅ done (PR #15) — **"Add to calendar" on every event card**: `.ics`
   download (as a `data:` URI, no extra output file) plus a Google
   Calendar quick-add link, for every event with a machine-readable date.
   Assumes a 1-hour duration (stated as an assumption, not fact) since
   sources rarely give an explicit end time.

3. ✅ mostly done (PR #23) — **Self-serve sponsor page (`/sponsor`).**
   Real page with pricing table + live per-region availability ("Open this
   week" / "Sponsored by X"), replacing "email me for the media kit". CTA
   opens a prefilled GitHub issue inquiry instead of a Stripe Payment
   Link. **Two things not done, both need a human**: (a) an actual Stripe
   account + Payment Link for real self-serve checkout — currently the
   inquiry still gets confirmed/invoiced manually; (b) a real multi-week
   availability calendar ("Week of Sep 8 — open") — `config/sponsors.yaml`
   only tracks one current slot per region today, not a dated schedule;
   worth building once there's an actual sponsor to schedule around.

#### P2

4. ✅ done (PR #17, extended 2026-08-28) — **Real datetime normalization +
   a structured-data coverage stat.** `_try_parse_date` (renamed from
   `parse_event_date_iso`'s inline logic) now handles RFC 822/ICS plus
   several common human-readable formats (`%Y-%m-%d` added this session),
   and `structured_date_coverage()` logs `N/M events have a
   machine-readable start date` per region and as a build total.
   `fetch_html_events` now extracts a date via `fetchers._nearby_date_hint()`,
   which tries two real, confirmed calendar-grid shapes in order of
   confidence: AHML's Drupal calendar stamps each day's `<td>` with
   `data-date="YYYY-MM-DD"`; Mount Prospect's Vision Internet-style
   Calendar has no such attribute, but its day cells carry an accessible
   `aria-label="Scheduled events, Saturday, September 12, 2026"` that
   parses via the existing `%B %d, %Y` format. Both signals are found by
   searching the raw HTML text near a matched link's href rather than
   modifying the flat link extractor's parsing logic (which every other
   source depends on) to track DOM ancestry - purely additive, so sources
   without either signal are unaffected. **Caught one real bug while
   adding the second signal**: `_EventLinkExtractor` (an `HTMLParser`)
   decodes `&amp;` to `&` in attribute values, but the raw HTML text
   being searched still has it escaped, so `html.find(href)` silently
   failed for any link with a query string - which is *every* Mount
   Prospect calendar link (`?curm=X&cury=Y`). Would have meant a 100%
   miss rate in production, caught by the new aria-label test before
   shipping, not after. The aria-label pattern is based on a single
   confirmed sample; if a differently-phrased one turns up later, loosen
   the regex rather than guess now - same fail-soft default as
   everything else here (a phrasing that doesn't match just produces no
   date, never a wrong one).

5. ✅ first slice done (PR #27) — **Seasonal guides** (`guides:` list in
   region YAML → generated pages). Each region config now has a `guides:`
   list (same shape as `evergreen`, grouped into named pages instead of one
   flat section). Each guide gets its own linkable page
   (`/<region>/guides/<slug>/`) plus a per-region guides index
   (`/<region>/guides/`), reusing `region.html.j2` so it inherits filters,
   dark mode, and the card layout for free. A "Guides" nav pill appears on
   every region view once a region has at least one guide. Both regions
   ship a real "Fall Family Guide" — sourced only from the same civic feeds
   as the weekly digest (park district / library / village), deliberately
   not inventing venue-specific hours or dates since those change yearly
   and belong on the official page the guide links to. Sitemap updated to
   include guide pages. **Not yet done**: only one guide (fall) exists per
   region — Macaroni KID's other formats (where-kids-eat-free, holiday
   lights, pool/splash-pad hours) are natural next entries in the same
   `guides:` list, no new code needed, just YAML content once there's a
   real season/occasion to write one for.

6. ✅ first slice done (PR #28) — **Local business directory per region.**
   `/<region>/directory/` (always in the nav, unlike Guides which only
   appears once a region has one). Driven by `config/sponsors.yaml`
   `history` entries opted in with `directory: true` (optionally
   `category`) — `build_business_directory()` in `build_digest.py`. This
   is what makes the $30/month Community Partner tier worth more than a
   footer logo that scrolls past: a business keeps its listing here after
   its sponsored week/month ends, as long as it was ever a paying sponsor.
   **No businesses are listed yet** — no sponsor has signed up (see Phase
   6's still-open note), so an empty directory is the honest, expected
   state right now, not a bug. The empty page isn't wasted, though: it
   renders its own CTA ("Be the first →" linking to `/sponsor/`) instead
   of a generic "nothing here." The moment `config/sponsors.yaml` gets its
   first real `directory: true` entry, this page starts working with zero
   further code changes.

7. ✅ done (PR #25) — **Dark mode via `prefers-color-scheme`.** Full dark
   token block on all four page templates (hub, region, weekend hub,
   sponsor), system-preference only, no manual toggle. Along the way,
   fixed a real WCAG AA contrast failure (white text on the brightened
   dark accent was 2.41:1, needed 4.5:1) by giving filled-pill
   backgrounds their own tuned token instead of reusing the text/link
   accent color for both jobs — worth remembering for any future color
   token added: check contrast in both directions (text-on-bg vs
   white-on-fill), not just one.

#### P3 — design polish (the "modern and impressive" goal)

8. ✅ done (PR #45), shipped with item 21 (item 19 shipped in the same PR,
   then reverted in it — see below) — **Bento-grid hub layout
   + a "This weekend at a glance" block.** The hub's `region-grid` is now a
   `.bento-grid`: a big weekend tile (`grid-column: span 2`, links to
   `/this-weekend/`, shows the date range and total weekend event count)
   plus a stat tile ("N towns · M live updates this week", real numbers from
   `main()`'s existing per-region totals — no new fetch needed) sit above
   the region tiles, which kept their existing card styling. New
   `render_hub_page(..., stats=hub_stats)` param carries `region_count`,
   `event_count`, `weekend_count`, `weekend_date_range`, computed once in
   `main()` from data already gathered for other pages.
   **Real bug caught and fixed before shipping, not by code review**: at
   narrow (mobile) widths, the grid has room for exactly one real 220px
   track, but the weekend tile's `grid-column: span 2` still demanded two —
   CSS grid satisfies that by creating a second, unusably narrow *implicit*
   column, and whatever auto-flowed into it (a region card) rendered
   squeezed to a handful of pixels wide with character-by-character text
   wrap. Caught with an actual Playwright screenshot at 390px width, not
   assumed; fixed with `@media (max-width: 560px) { .bento-weekend {
   grid-column: span 1; } }`. Verified again after the fix, plus light/dark
   and desktop/mobile combinations, plus the distance-sort JS still
   reorders only the region tiles (weekend/stat tiles stay put) with no
   console errors. **A second real regression — item 26's own budget
   caught it on GitHub's actual runner, not in local testing** — is the
   fuller story behind item 19: the scroll-reveal's original opacity
   animation genuinely pushed hub-page LCP to 2.87s (over the 2.5s
   budget), fixed by dropping opacity from that animation entirely — but
   even that fix then failed on Total Blocking Time, so the scroll-reveal
   animation was removed from this page altogether. Bento-grid layout and
   container queries both stayed and pass every budget on their own. See
   item 19 for the full account of what was tried and why it didn't ship.

9. ✅ done (PR #47), confirmed by real CI on the first push, not just
   locally — the original `IntersectionObserver` approach this item
   proposed, after item 19's pure-CSS attempt (`animation-timeline:
   view()`) had to be reverted for real Total Blocking Time cost.
   Deliberately more conservative than attempt 1: one observer callback
   per `.bento-tile`, immediately `unobserve()`d after it fires (bounded,
   one-time work per tile, not a continuous per-frame recalculation),
   `transform` only - never `opacity`, so the LCP-deferral bug from item
   19's first version can't recur regardless of timing. Locally confirmed
   before pushing: `opacity` stays `1` at every point (checked via
   `getComputedStyle`), a tile already on-screen at load reveals without
   needing a scroll gesture, a tile below the fold correctly waits for
   one. Given attempt 1 also passed local testing before failing for real
   on GitHub's runner, this one was deliberately not marked done until
   the real CI run on PR #47 came back green - which it did, on the first
   push, no re-work needed. **Worth remembering for the next motion
   feature on this site**: the difference between the two attempts wasn't
   the visual effect (both did the same slide-in), it was the mechanism -
   `IntersectionObserver` with `unobserve()` is bounded one-time work,
   while `animation-timeline: view()` is continuous per-frame
   recalculation that Lighthouse's CPU throttling amplifies into real
   measured cost. Prefer the observer pattern here going forward.

10. ✅ done (PR #29) — **Accessibility pass.**
    - Contrast audit (computed WCAG relative-luminance contrast for every
      token pair, not eyeballed): `--muted` and all 8 tag-badge hue pairs
      already passed 4.5:1 in both themes. Found one real failure:
      `--accent-2` (#d9772e) as small text (card dates, sponsor label,
      tier price, zip/distance labels) was only 2.9:1 on `--bg` in light
      mode — below AA. Fixed the same way as the dark-mode accent fix in
      item 7: split it into a separately-tuned `--accent-2-text` (#a95c23,
      4.5–5.0:1) for text, keeping `--accent-2` for non-text accents
      (border-left decoration) where contrast rules don't apply. Dark
      mode's accent-2 already passed (7.7:1), so `--accent-2-text` equals
      `--accent-2` there.
    - Visible focus rings: `:focus-visible { outline: 2px solid
      var(--accent); outline-offset: 2px; }` on all four templates, so
      focus is guaranteed legible against the site's own palette instead
      of relying on the browser's default (which isn't tuned for dark
      backgrounds or filled pill buttons). Verified visible via a
      Playwright keyboard-tab screenshot.
    - `aria-live="polite"` region in `region.html.j2` announcing filter
      results ("Showing 2 of 9 items.") when filter chips are toggled —
      verified the text actually updates on click, not just present in
      markup.
    - `aria-live="polite"` on the hub's `#distance-status` span, so the
      "Locating…" / "Sorted by distance from you." messages reach screen
      reader users (previously visual-only).
    - Added a visually-hidden `<label>` for the manual ZIP `<input>` on
      the hub (previously placeholder-only, which isn't a reliable label
      for assistive tech).
    - Distance-bar keyboard operability: already fine — the geolocation
      button, ZIP input, and "Go" button are native `<button>`/`<input>`
      elements, not click-handler `<div>`s, so no change was needed there
      beyond the focus ring.

11. ✅ done (PR #30) — **Weather on the weekend view.** `fetch_weather()`
    in `fetchers.py` calls Open-Meteo (free, no API key/account) for a
    ~10-day daily forecast, same fail-soft contract as every other
    fetcher — a weather outage just omits the block, never breaks the
    build. `build_weekend_weather()` in `build_digest.py` matches
    Saturday/Sunday **by date string**, not list position, so an
    unexpected response shape can't mismatch a day. Wired into each
    region's `/this-weekend/` page only (not the merged hub-level weekend
    page, to keep this slice contained — a natural next step, same data
    already computed per-region in `main()`). Shows high/low °F,
    condition + emoji (mapped from Open-Meteo's WMO weather codes), and
    precip % per day; when either day has meaningful precipitation, a note
    points at the Indoor filter chip. **Caveat worth knowing**: this only
    refreshes when the site rebuilds (weekly per `build-digest.yml`'s
    cron, more often while this hourly loop is actively shipping other
    changes that also touch `scripts/`/`templates/`/`config/`) — a
    forecast baked in on Monday for the coming Saturday is a few-day-out
    forecast, not live weather. Acceptable for "should I plan something
    indoor" at a glance; not sold as minute-fresh.

12. ✅ done (PR #33) — **Email capture.** Followed the second research
    pass's re-rank (promoted ahead of items 8/9 as "the number a sponsor
    asks for first" now that the sponsor page has somewhere to send a
    business owner). Same config-gated pattern as the sponsor page and
    business directory: `config/newsletter.yaml` holds a `buttondown_
    username`, a headline, and detail text; `load_newsletter_config()` in
    `build_digest.py` derives a `configured` flag from whether a real
    username is set. Signing up for Buttondown (or any email service) is
    a human/paid action this loop can't do on its own, same as Stripe for
    the sponsor page — so the file ships **unconfigured** and the hub +
    every region page show the real headline/detail with an honest
    "Signup coming soon" message instead of a form posting to nowhere.
    The moment a real account exists and the username is set, the same
    block on the same pages switches to Buttondown's documented embed
    form (`<form action="https://buttondown.com/api/emails/embed-
    subscribe/{username}">`) with zero other code changes. Verified both
    states render correctly with a mocked-config Playwright screenshot
    (configured state) alongside the real unconfigured build output.
    **Not yet done, deliberately scoped out of this slice**: the merged
    hub-level weekend page and the sponsor page itself don't show the
    block yet (natural follow-ups, same pattern); once there's a real
    subscriber count, `SPONSOR_KIT.md`/the sponsor page copy should cite
    it (item 18's "recommendation, not an ad" reframe is a good place to
    fold that in).

13. ✅ done (PR #31) — **User-submitted events** (Patch's model — let the
    community supply the content). `.github/ISSUE_TEMPLATE/
    event-submission.yml` is a GitHub Issue Form (region dropdown, title,
    description, link, optional date). `.github/workflows/
    event-submission.yml` parses it and opens a PR — **never merges
    anything itself**: a public submission form is spam/abuse-prone, so a
    person always reviews before it goes live, exactly the "owner's
    involvement stays at merge or don't" framing this item asked for.
    `scripts/parse_event_submission.py` does the actual work, split into
    two independently-tested pure functions: `parse_issue_body()` (text
    parsing) and `insert_evergreen_entry()` (a **targeted text splice**
    into the region file, not a `yaml.safe_load`/`yaml.safe_dump` round
    trip — the region files carry extensive hand-written comments a round
    trip would silently discard; verified with a diff against the real
    Mount Prospect file that the insertion touches only the 3 new lines).
    The submitted text still goes through `yaml.safe_dump` rather than
    string interpolation, so a title/detail/url containing a quote or
    colon can't corrupt the file. Tags are deliberately left unset on the
    new entry — `prepare_evergreen()` already infers them at build time,
    so a submitted entry gets the same auto-tagging a fetched event would,
    no new code needed. A submitted date isn't written into the entry
    (evergreen items have no date field in this schema); it's surfaced in
    the PR description instead for the human reviewer to act on.
    `tests.yml` already runs on every PR including this one, so a
    malformed region file also fails CI before a human looks at it.
    **Unverified**: the live GitHub → Issue Form → workflow → PR flow
    itself — this sandbox can't fire a real `issues.opened` webhook, so
    only the parsing/insertion logic (13 unit tests) and a real dry run
    against a scratch copy of the actual region file are verified.
    **Known limitation, accepted rather than solved here**: nothing rate-
    limits or screens who can open a submission (any GitHub user, if the
    repo is public) — worst case is spam PRs sitting unmerged, since
    nothing auto-publishes, but a quality/abuse gate is future work if
    that turns out to matter in practice.

#### Research pass 2026-08-27 (second pass)

Pace note: the build loop cleared **10 of the first 13 items inside a day**
(PRs #15–#31), leaving only items 8, 9 and 12 open. The backlog empties
faster than a 6-hourly research cadence refills it — if that holds, this
loop should generate deeper batches, and the owner may want the research
cadence raised.

Competitors reviewed this pass:

| Site | What it is | Worth stealing |
|---|---|---|
| **Time Out Chicago** | Editorial city guide, "54 Best Things to Do Right Now" | Curation *as* the product — standardized listings, star ratings, an "editors chose this" voice; plus a weekly-refreshed interactive map of picks |
| **Choose Chicago / Wanderlog / Pilot Plans** | Destination + trip-planning tools | The itinerary builder is the defining trip-planner feature — pick things, collect them, map them, share them |
| **Nextdoor** | Neighborhood social network | Local *recommendation* beats local *advertisement*: 79% of neighbors acted on a recommendation seen there, 81% within days, ranked above conventional directories |
| **Chicago Parent / Chicago Kids** | Chicagoland parenting hubs since 1984/1999 | Standing high-intent directories — birthday party venues ("39 great places"), summer camp guides, kids' classes — as their flagship ad inventory |

#### P1 (new)

14. ✅ done (PR #34) — **"Build my weekend" — a client-side itinerary
    tray.** A ☆ button on every event/evergreen/guide card (region page's
    every view, plus the merged cross-region weekend page) toggles it into
    a `localStorage`-persisted tray, no backend or accounts. A floating
    "🧭 My Weekend (N)" widget (bottom-right, every page that has cards)
    lists what's saved with per-item remove, a Clear button, and "Export
    all to calendar" — one merged `.ics` built client-side (same 1-hour-
    duration assumption as the existing single-event export). Because the
    same `localStorage` key is used on every page (same origin), a tray
    built on one region's page still shows correctly on another region's
    page or the merged weekend page — the first feature that makes the
    *multi-ZIP* "trip across a few nearby towns" promise in the vision
    real, not just aspirational copy.
    **Real bug caught before shipping**: the star button's `data-item`
    attribute embeds each item as JSON via Jinja's `tojson` filter, which
    HTML-escapes `<`, `>`, `&`, and `'` for safe embedding — but leaves
    literal `"` characters as-is (required JSON syntax). The first version
    used `data-item="{{ ... }}"` (double-quoted), which broke the HTML
    attribute the instant real JSON double quotes appeared - confirmed by
    inspecting the actual build output, not assumed. Fixed by switching
    the attribute delimiter to single quotes (`data-item='{{ ... }}'`),
    which `tojson`'s escaping is specifically designed to be safe inside.
    Verified end-to-end with Playwright: star persists across a reload,
    remove/clear work and resync the card's star glyph, and the exported
    `.ics` is well-formed (dated and undated items both handled).
    Deferred, not done: the "copy a share URL with the selection encoded
    in the hash" idea from this item's original wording — `.ics` export
    alone covers the primary use case (get it into your calendar app);
    a shareable link is a natural follow-up if it turns out people want to
    hand a whole itinerary to someone else rather than each import it.

15. ✅ done (PR #39) — **Birthday-party venues + kids' classes guides.**
    A second `guides:` entry per region, `birthday-parties-and-kids-
    classes` — the guides machinery (item 5) already generalized to
    multiple guides per region, so this needed zero Python/template
    changes, exactly the "content/config slice" this item predicted.
    Four items per region: Park District birthday-party rentals, Park
    District kids' classes/camps, Library kids' programs — same civic-
    source-only discipline as the fall guide (no invented prices, times,
    or private venue names; a family finds those on the linked page,
    where they're actually kept current) — plus a fourth item linking to
    the region's own `/directory/` page for "local party venues,
    entertainers & tutoring centers." That last one is the honest answer
    to this item's own observation that those are exactly the businesses
    with budget for a recurring listing: the directory starts empty and
    fills in as real businesses join (see item 6), which beats guessing
    names that may not exist or may be wrong. Verified with a Playwright
    screenshot of the real generated guide page, and confirmed the
    directory cross-link, sitemap entries, and tray-star button all wire
    up correctly.

#### P2 (new)

16. ✅ done (PR #36) — **Editor's pick per region.** `select_editors_pick()`
    in `build_digest.py`: soonest dated item wins first (across both
    fetched events and evergreen entries), free + kid-friendly break ties
    — exactly the heuristic this item asked for. `region.editors_pick_url`
    in `config/regions/<id>.yaml` (documented, commented-out by default in
    both region files) overrides the heuristic with a specific item by
    URL; a stale/unmatched override logs a warning and falls back to the
    heuristic rather than crashing the build. Rendered as a pinned card on
    the region's main page only (not the date-scoped/guides/directory
    subpages, so it reads as a genuine pick rather than boilerplate),
    placed **directly above the sponsor box** — literal adjacency, per
    this item's own reasoning that it's "the most valuable adjacency on
    the page to sell a sponsor next to." Styled with the site's green
    `--accent` (vs. the sponsor box's orange `--accent-2`) so editorial
    and paid content stay visually distinct. Also gets a tray-star button
    for consistency with item 14's itinerary feature — verified with
    Playwright that starring it updates the tray correctly. 7 new tests
    cover the heuristic (soonest-wins, dated-beats-evergreen, tie-breaking,
    override-found, override-missing-falls-back, no-candidates,
    missing-title-or-url-excluded).

17. ✅ region-level slice done (PR #37) — **Map view.** `build_region_map()`
    in `build_digest.py`: a simple equirectangular projection of each
    region's lat/lon (already in config) onto a small SVG canvas — no
    tile provider, JS library, API key, or rate limit. A dashed line
    between regions is labeled with the real great-circle distance
    (`_haversine_miles()`, computed once at build time since region-to-
    region distance is fixed, unlike the client-side "distance from you"
    feature). Pins link to their region page. Rendered as the visual
    centerpiece near the top of the hub, right after the weekend callout.
    Returns `None` (hub omits the block) with fewer than 2 regions with
    real coordinates, so it never draws one meaningless dot.
    **Real bug caught and fixed before shipping**: SVG roots clip to their
    `viewBox` by default, and a region name at `text-anchor="middle"`
    extends well past its pin's x position — the first version clipped
    "Arlington Heights" mid-word at the card edge, caught by actually
    screenshotting the real build output rather than trusting the code.
    Fixed with `overflow: visible` on the `<svg>` plus more generous
    padding. Verified pin links work, keyboard focus reaches them, and
    both light and dark mode render correctly, all via Playwright.
    **Per-event pins** (vs. this region-level slice) still need the
    geocoding parked in Phase 8's "later" note — unstarted, and pairs
    naturally with item 8's still-undone bento layout for a bigger visual
    treatment once there's a real reason to invest in one.

18. ✅ done (PR #38) — **Recast the sponsor slot as a recommendation, not
    an ad.** Not quite the "pure-copy change" this item expected — the
    honesty requirement meant the house ad (no real sponsor booked) can
    never say "we recommend them," since nothing has actually been
    recommended yet. So `resolve_sponsor()` now tags its result with
    `is_active_sponsor` (true only for a real paying entry, never the
    house-ad fallback), and `region.html.j2`'s sponsor box branches on it:
    a real sponsor gets "💚 Local Recommendation" framing plus an optional
    one-line `why` field (new, optional, in a sponsor's `config/
    sponsors.yaml` history entry — e.g. "they sponsor the Little League
    team"); the empty slot still honestly says "Sponsor This Spot."
    `sponsor.html.j2`'s pitch, `SPONSOR_KIT.md`, and `OUTREACH_TEMPLATES.md`
    (also fixed along the way: still said "60056 Weekly," the pre-pivot
    single-region name) now lead with the Nextdoor stats (79% acted on a
    recommendation, 81% within days) as the actual argument for why this
    format beats a banner ad, and the inquiry flow now asks for the "why"
    line up front. Verified both states (empty slot, and a mocked real
    sponsor with a `why` line) render correctly with Playwright — the
    honest branch was worth checking as carefully as the recommendation
    one, since a fake "we recommend them" on an unsold slot would have
    undercut the entire point of this rewrite.

#### P3 (new) — the "modern and impressive" goal, 2026 CSS edition

19. ❌ tried in PR #45, reverted in the same PR — **Do item 9 in pure CSS
    instead.** Shipped `.bento-tile` (hub page) sliding in via
    `animation-timeline: view()`, then pulled it back out after item 26's
    own CI budget caught two real, separate problems with it on GitHub's
    actual runner - neither reproducible in this sandbox's blocked-network
    testing, both worth recording so nobody re-tries the same approach
    without knowing why it failed:
    1. **LCP regression.** The first version animated `opacity: 0 → 1`
       alongside the slide. Per the LCP spec, an element's recorded paint
       time is the moment it becomes non-transparent, not when it first
       exists - so when the real largest-paint candidate on a real network
       landed inside a `.bento-tile`, the reveal genuinely deferred its LCP
       timestamp to 2.87s against the 2.5s budget. Fixed by dropping
       opacity from the animation (`transform: translateY()` only) -
       confirmed every tile stays at `opacity: 1` regardless of scroll
       position, removing that entire risk category.
    2. **TBT regression, which killed the feature.** Even the opacity-free
       version failed CI on Total Blocking Time - 1144ms on the first run,
       324.5ms on one confirming re-run (the >3x swing between two runs of
       identical code confirms TBT is a genuinely noisy lab metric here,
       but a real floor still sat above the 200ms budget both times, so
       this wasn't pure noise). Most likely cause: `animation-timeline:
       view()` requires the browser to keep recalculating scroll-linked
       animation progress, and Lighthouse's simulated 4x CPU throttling
       amplifies that into real measured main-thread blocking time. Rather
       than guess at a third speculative fix, removed the scroll-reveal
       animation entirely and kept the parts of this PR that don't carry
       this cost - the bento-grid layout (item 8) and the container query
       (item 21), both confirmed to still pass every budget afterward.
    **Net position**: pure-CSS scroll-driven animation
    (`animation-timeline: view()`) is real and works, but is not free on
    a CPU-throttled lab run, and this specific page didn't have enough
    performance headroom to absorb it once real network/CPU conditions
    were in play. A future attempt should budget for that up front (e.g.
    only on a page with more LCP/TBT headroom already measured) rather
    than assume "no JS" means "no cost."

20. ✅ done (PR #35) — **View Transitions on navigation.** `@view-transition
    { navigation: auto; }` added to all four page templates (hub, region,
    weekend hub, sponsor), plus a `prefers-reduced-motion` override that
    turns the transition animation off for anyone who's asked for that.
    Genuinely zero-risk: an unknown CSS at-rule is simply ignored per
    spec, so browsers without support get a plain page load exactly as
    before — confirmed no console/page errors and no visual regression
    with a Playwright render, and confirmed the bundled Chromium actually
    supports the underlying API (`'startViewTransition' in document`).
    5 lines of real CSS per page, no router, no framework, no JS.

21. ✅ done (PR #45), shipped with item 8 (item 19 shipped alongside these
    two in the same PR, then had to be reverted — see item 19) —
    **Container queries for
    the card component.** Every `.bento-tile` (hub page, includes region
    cards) is now `container-type: inline-size`, and `.region-card` grows
    its heading/body font at `@container (min-width: 340px)` — a real
    example of "one card adapts to whichever column it lands in," not
    decoration: a region tile only crosses that width when the grid has
    few enough regions to hand it extra room, exactly the scenario item 8
    creates. Scoped to the hub's region cards for this slice, matching
    where the bento layout actually varies a tile's width today; the same
    pattern is available to extend to the region-page event cards
    whenever those sit in a non-uniform layout too.

**Re-rank:** item 12 (email capture) is now the most valuable *open* item
from the first batch. The self-serve sponsor page shipped in item 3, so
there is a real place to send a business owner — and the first question
any of them will ask is how many people this reaches. Promote it ahead of
items 8 and 9.

#### Research pass 2026-08-27 (third pass)

State of play: 19 of the first 21 items are done, and **nothing above P3
was left open**. The site now has most of what the competitive set has —
date-scoped views, calendar export, an itinerary tray, guides, a
directory, a map, weather, dark mode, view transitions. So this pass
deliberately stops asking "what feature is missing" and asks the two
questions that actually decide whether this makes money: **can it be
found, and can it prove an audience?**

Angles reviewed this pass:

| Angle | Finding | Worth stealing |
|---|---|---|
| **AI search / GEO** | Fewer than 10% of sources cited by ChatGPT, Gemini and Copilot rank in Google's organic top 10 for the same query; AI Overviews now fire on ~48% of tracked queries | AI citation is a *separate channel with separate rules* — not a byproduct of the SEO already done in Phase 9 |
| **Newsletter economics** | 2026 benchmarks: 20–30% open average, 40%+ excellent; recommendation networks grow newsletters ~2.75× faster; publishers who recommend others are 32× more likely to be recommended back | Send Tue–Thu; cross-recommendation is the cheapest growth lever there is |
| **Privacy-first analytics** | GoatCounter: ~1KB script, cookie-free, no consent banner needed under GDPR/ePrivacy, free donation-supported hosted tier. Plausible CE for self-hosting later | Right-sized for a static site with zero ops budget |
| **Core Web Vitals 2026** | LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 at p75. INP is field-only — Lighthouse's Total Blocking Time is the accepted lab proxy | Budgets enforced in CI, so regressions fail the build instead of failing readers |

#### P1 (new)

22. ⚠️ first slice done (PR #42) — **Get cited by AI search (GEO), as a
    deliberate strategy.** Under 10% of AI-cited sources rank in Google's
    top 10 for the same query, so the Phase 9 SEO work does **not** buy
    this channel — and AI Overviews now trigger on roughly half of all
    queries.
    Shipped: `build_llms_txt()` generates `/llms.txt` at build time
    (llmstxt.org convention) from the same `region_summaries` the sitemap
    uses, so it can't drift out of sync the way a hand-written one would
    — lists every region, the merged + per-region "this weekend" views,
    every guide, and the sponsor page. `robots.txt` now explicitly names
    GPTBot / ChatGPT-User / OAI-SearchBot / ClaudeBot / Claude-Web /
    anthropic-ai / PerplexityBot / Perplexity-User / Google-Extended /
    CCBot with their own `Allow: /` blocks, rather than leaving AI
    crawler access implicit in the wildcard rule. A genuine ~40-60 word
    answer block (`build_answer_block()`) now sits at the top of each
    region's **main** page (not repeated on every subpage, to avoid
    looking like boilerplate) - deliberately generic/accurate rather than
    citing specific event counts, since a wrong specific in an AI's
    cached copy is worse than a true generality. Item 28's freshness
    signal (below) shipped alongside this, since it's the same strategic
    bet.
    **`FAQPage` schema done in PR #46.** `build_guide_faq()` in
    `build_digest.py` generates four real, honest Q&A pairs about how the
    site itself works (update cadence, coverage limits, the weekend view,
    how to submit an event or inquire as a sponsor) - deliberately not
    fabricated facts about specific venues, hours, or prices, matching
    every other GEO item's discipline. Rendered as real, visible
    `<details>/<summary>` HTML (no JS) on each guide page, with the exact
    same answer text embedded in matching `FAQPage` JSON-LD - Google's own
    guidance treats a mismatch, or hidden-only FAQ markup, as unreliable,
    so `build_faq_json_ld()` takes the same list the template renders
    rather than a second hand-written copy. Verified with a real
    Playwright screenshot (open/closed states, light/dark) and confirmed
    the guides index and main region page don't get the block (only
    actual guide pages do, where it's genuinely relevant).
    **Correction (seventh research pass, 2026-08-28):** the paragraph
    above framed `FAQPage` schema as pursuing Google rich-result
    eligibility - that stopped being true when Google discontinued FAQ
    rich results on 2026-05-07, after already dropping HowTo results.
    This is not a request to remove the markup: it still feeds AI
    parsing and E-E-A-T signals, consistent with this whole item's GEO
    strategy, so it earns its keep for a different reason than
    originally stated. The correction is only that no further FAQPage
    work should be justified by SERP rich-result eligibility going
    forward - that door is closed.
    **Entity-naming audit done in PR #49.** Found a real inconsistency,
    not a hypothetical one: every page's `<title>` and `og:title` said
    "Weekend & Trip Planner" - except region pages (the most numerous
    page type on the whole site: every region's main/today/weekend/
    free/guides/directory view), whose `page_title` was independently
    computed in `build_digest.py` and said the shortened "Weekend
    Planner" instead. Two different strings for what should read as one
    entity to a search/AI crawler. Fixed by introducing a single
    `SITE_NAME` constant and using it everywhere a page names its own
    publisher, instead of each call site spelling it out separately.
    Also added `og:site_name` (previously present nowhere) to all four
    templates, and an `isPartOf` link on every region page's `WebPage`
    JSON-LD pointing at a canonical `WebSite` entity - stating "these
    pages belong to the same site" directly instead of leaving a
    crawler to infer it purely from repeated title-string matches.
    **The strategic point worth stating out loud:** content updated
    within 30 days earns ~3.2× more AI citations, and this site rebuilds
    itself every week (see item 28). Automated freshness is a structural
    advantage over every hand-written competitor guide — Time Out's "54
    Best Things to Do" piece decays the moment it's published; this
    doesn't. That is arguably the strongest moat in the whole business,
    and until this PR it was an accident rather than a strategy.

23. ✅ done (PR #41) — **Analytics — the first number every sponsor will
    ask for.** `config/analytics.yaml` holds a `goatcounter_code`, gated
    exactly like the Buttondown embed in item 12 - unset by default (real
    account creation is a human action this loop can't do), so no script
    is embedded and nothing is tracked until a real code is set.
    `load_analytics_config()` in `build_digest.py` derives the
    `configured` flag; wired into **all four page templates** (hub,
    region, weekend hub, sponsor), each getting the ~1KB async
    `data-goatcounter` script plus a footer privacy line ("no personal
    data collected") once configured. Verified both states: the real
    unconfigured build emits the script nowhere (checked all four page
    types), and a mocked configured code renders the correct script tag
    on all four. **Not yet done, left for once there's real data**:
    surfacing a rolling "≈N readers/month" on `/sponsor` - that's real
    numbers this loop can't fabricate, so it waits for an actual
    GoatCounter account and some traffic.

#### P2 (new)

24. **Actually send the newsletter.** Item 12 captures addresses; nothing
    mails them, so the list is currently an asset earning zero. Buttondown's
    API plus the existing weekly build is the whole product Macaroni KID
    and 6AM City monetize. Send Tuesday–Thursday (highest engagement), and
    judge it against 2026 benchmarks — 20–30% open is average, 40%+
    excellent. Those same numbers belong in `SPONSOR_KIT.md`, since an
    open rate is a stronger sponsor argument than a subscriber count.

25. **Newsletter cross-recommendations.** Newsletters in recommendation
    networks grow about 2.75× faster, and publishers who recommend others
    are 32× more likely to be recommended back. A small "other local
    newsletters we like" block plus reciprocal listings with nearby-suburb
    publishers costs nothing per week and compounds. Depends on item 24.

26. ✅ done (PR #43) — **Performance budget in CI.** `.github/workflows/
    tests.yml` now runs Lighthouse CI (`@lhci/cli`, new `package.json` +
    lockfile, `lighthouserc.json` at repo root) against the built `docs/`
    output on every PR and push to main, asserting the exact 2026 bar this
    item named — LCP ≤2.5s, CLS ≤0.1, TBT ≤200ms (the lab proxy for INP) —
    as hard `error`-level assertions, so a regression fails the build
    instead of quietly shipping. Checked against four representative pages
    (hub, a region's main view, that region's `/this-weekend/`, and
    `/sponsor/`) via `staticDistDir`, no external hosting needed. A
    separate `scripts/check_perf_budget.py` covers the JS-bytes cap half of
    this item as a plain Python check (12KB inline-JS-per-page budget, real
    pages currently peak at 7.1KB on the tray-widget-heavy region views) —
    kept out of Lighthouse's own `resource-summary` audit because every
    script on this site is inline, not a separate request, so that audit
    can't see it; JSON-LD `<script>` blocks are explicitly excluded since
    they're data, not code. 5 new unit tests for the byte-counting logic.
    **Verified for real, not assumed**: ran the entire pipeline locally
    exactly as CI will — `npm ci`, `pytest` (141 passed), a real build,
    the budget check, and `npx lhci autorun` — using this sandbox's bundled
    Playwright Chromium as a stand-in for the runner's preinstalled Chrome
    (GitHub-hosted `ubuntu-latest` ships Chrome already, so the checked-in
    config has no hardcoded `chromePath`; that override was local-only).
    Real measured numbers under this sandbox's degraded network (Google
    Fonts blocked, inflating Speed Index) still came back LCP ~1.4s, CLS 0,
    TBT 0 on every page — comfortable headroom, not a number invented to
    make the assertion pass. **Note for future changes**: `npm ci` needs
    `package-lock.json` kept in sync — regenerate with
    `npm install --package-lock-only` if `package.json` ever changes.
    **This budget caught a real regression on its very first CI run**: the
    sandbox's blocked network couldn't reproduce it (Google Fonts just
    failed outright there), but on GitHub's actual runner the synchronous
    `<link rel="stylesheet">` to `fonts.googleapis.com` genuinely blocked
    first paint, pushing LCP to ~2.7-2.8s on all four checked pages -
    over budget. Fixed with the standard preload+swap pattern (paint with
    the existing fallback font stack immediately, swap to the web font once
    it loads, `<noscript>` fallback for JS-off) on all four templates,
    confirmed by re-checking that `render-blocking-resources` now reports
    zero items on every page. Exactly the outcome this item was for: a real
    performance issue this project had been shipping unnoticed, caught by
    CI instead of a reader's slow connection.
    **A second real problem, found in PR #49 - the budget's own noise
    floor, not a page regression.** `numberOfRuns: 1` meant every
    assertion ran on a single Lighthouse sample, and Total Blocking Time
    turned out to swing wildly run-to-run on GitHub's shared runners even
    with zero relevant code changes: PR #45's reverted animation measured
    1144ms then 324.5ms on identical code; PR #49 - which touched the hub
    page with nothing but a static `<meta>` tag and a JSON-LD field, no
    JS at all - measured 727.7ms then 275.5ms on two runs of the literal
    same commit. A 200ms budget on a single noisy sample was going to
    fail real, unrelated PRs indefinitely. Fixed the actual root cause
    rather than loosening the threshold to paper over it: `numberOfRuns`
    raised from 1 to 3, which is Lighthouse CI's own documented fix for
    exactly this - it takes the *median* of three runs for every
    assertion instead of trusting one sample, filtering out the kind of
    outlier that produced the 1144ms and 727.7ms readings above while
    still catching a real, sustained regression. Costs roughly 3x the CI
    minutes for this one step; worth it since a budget nobody trusts
    (because it fails PRs that didn't cause the failure) gets ignored or
    disabled, which defeats the entire point of item 26.

#### P3 (new)

27. ✅ done (not yet verified live) — **Third region — now worth more than
    when Phase 10 parked it.** Distance sort (Phase 8), the hub map (item
    17) and the guides (items 5 and 15) all get better with more towns,
    and each region is another sponsor slot at zero marginal cost. Added
    Des Plaines (60016) as `config/regions/des-plaines-60016.yaml` — the
    first of the three shortlisted candidates (Des Plaines, Palatine, Elk
    Grove Village), picked because 60016 was already present in
    `templates/hub.html.j2`'s `ZIP_COORDS` table, so its coordinates were
    already vetted rather than a fresh guess. All three source domains
    (desplaines.org, dppl.org, dppd.org) and listing-page paths are a
    best-effort guess from training knowledge — same starting point every
    region here began from — not yet confirmed against a live build;
    Playwright screenshots confirm the hub and region pages render
    correctly with the expected "no live updates fetched" fallback state,
    same as any other unconfirmed source. Also updated the two other
    places a region list is hardcoded: `parse_event_submission.py`'s
    `REGION_LABEL_TO_ID` map and the event-submission Issue Form's region
    dropdown. Arlington Heights doesn't get the same downtown-merchants /
    tourism-site sources item 41 added to Mount Prospect, and neither does
    Des Plaines — no equivalent has been confirmed to exist for either,
    same reasoning item 42 already recorded.

28. ✅ done (PR #42), shipped alongside item 22 — **Visible freshness
    signals.** The human-readable "Generated {date}" footer line already
    existed on every page; new is `build_freshness_json_ld()`, a
    `WebPage` node carrying `dateModified` (the build timestamp),
    independent of `build_event_json_ld`'s Event graph so it's present
    even on a page with zero currently-dated events. Deliberately its own
    `<script>` block rather than folded into the Event graph, since the
    two have different truthiness (an empty Event graph is legitimately
    `None`; a page's freshness is never nothing).

**Re-rank:** item 4 (datetime normalization, still ⚠️ partial) should move
up. It was originally justified by Google event rich results; item 22 makes
it matter twice over, since an event an AI can't read a start time from is
an event it won't cite. It is now the oldest unfinished thing blocking the
newest priority.

#### Research pass 2026-08-28 (fourth pass)

This pass went looking for the closest *business* analogue rather than more
features, and found one. The finding is about pricing structure, not UI.

First, a correction owed from the third pass: item 19 (pure-CSS
`animation-timeline: view()`) was **wrong**, and item 26's CI budget caught
it on GitHub's real runner — an LCP regression and then a fatal TBT
regression, neither reproducible in the sandbox. That is the perf budget
paying for itself in its first week, and the standing lesson is that any
change whose cost only shows up on a real network stays gated behind it.

| Angle | Finding | Worth stealing |
|---|---|---|
| **Family Focus Media** (Main Line Parent / Philadelphia Family / Bucks County Parent, est. 2010) | The closest analogue to this business that exists. Monetizes via annual **memberships**, explicitly to reduce "dependence on advertising dollars". Members get a profile page, directory listing, spotlight inside guides, SEO backlinks, social promotion, priority event coverage | The whole pricing model — and every one of those member benefits is a feature this site already shipped |
| **Real-estate agents as a sponsor category** | Agents budget **$500–$1,500/month** to "farm" a ~400-home neighborhood across direct mail, digital and event sponsorship. The stated goal is to be seen as *the* local authority | A category whose budget is 3–8× the current top price, wanting exactly what a town events guide confers |
| **Weekend-newsletter send timing** | Both Main Line Parent and Philadelphia Family send their weekend planner **Thursday afternoon** | Sharpens open item 24 from "Tue–Thu" to a specific slot two independent analogues converged on |
| **School / youth-sports calendars** | Districts publish academic calendars, early dismissals and game schedules publicly; no local competitor aggregates them | A data source, not a feature — and a genuine gap |
| **2026 premium design direction** | Sophisticated serif + warm champagne-toned neutrals; the high-contrast 2022–23 era is softening; transitions that never call attention to themselves; 60fps or don't ship | A palette pass, gated behind item 26 |

#### P1 (new)

29. ✅ done (PR #50), shipped with item 30 — **Reprice around annual
    memberships, not weekly ad slots.** `SPONSOR_TIERS` in
    `build_digest.py` restructured around a new **Annual Partner**
    ($1,200/year) as the flagship: permanent directory listing (item 6),
    a spotlight placement inside one seasonal guide (items 5/15), a live
    SEO backlink, and priority Editor's Pick consideration (item 16) —
    every benefit already existed in the product, only the packaging
    changed, zero new code. The old weekly slot survives as **Weekly
    Spot** ($50/week or $175/month), now framed as the lower-commitment
    add-on rather than the headline product, matching this item's
    instruction exactly. `SPONSOR_KIT.md`, `/sponsor`,
    `OUTREACH_TEMPLATES.md`, and `BUSINESS_PLAN.md`'s own pricing table
    all updated together so nothing quotes stale tier names or prices.
    Annual Partner priced below 7 months of the old top monthly rate
    ($175 × 12 = $2,100/yr) as a real incentive to commit, not a token
    discount — reasoning kept inline as a code comment next to
    `SPONSOR_TIERS` for whoever revisits pricing next.

30. ✅ done (PR #50), shipped with item 29 — **Add a real-estate tier, and
    raise the ceiling.** New **Neighborhood Authority** tier
    ($5,000/year, one business per region) — priced at the low end of
    the $500–1,500/month "neighborhood farming" budget category this
    item named, deliberately introductory for an unproven, brand-new
    premium product with room to raise it once it has actually sold.
    Region exclusivity needed no new code: every tier already competes
    for the same single `active` sponsor slot per region
    (`resolve_sponsor()`), so "held exclusively" was already true the
    moment a business buys any tier — only the pricing/copy needed to
    say so. Pitched honestly per this item's own instruction (presence
    and authority, not leads, low year-one ROI) in a new dedicated
    outreach template (`OUTREACH_TEMPLATES.md` #5) rather than folding
    real-estate messaging into the generic cold-intro template, since
    the sales conversation is genuinely different from every other
    category this site targets.

#### P2 (new)

31. **Send the weekend email Thursday afternoon.** A refinement of open
    item 24, not a replacement. Both Main Line Parent and Philadelphia
    Family send their weekend planner Thursday PM — two independent
    analogues converging on the same slot is a stronger signal than the
    generic Tue–Thu benchmark from the third pass. Ship item 24 with a
    Thursday-afternoon send.

32. **School district and youth-sports calendars as a data source.** This
    is a gap rather than a feature to copy: no local competitor aggregates
    them, and for a family suburb the school calendar — early dismissals,
    no-school days, concerts, games — is a large share of what a parent's
    week actually contains. Would add sources to `config/regions/*.yaml`
    for District 57 and Township High School District 214.
    **Verify before shipping:** confirm each district publishes a calendar
    feed intended for public syndication, and keep it fail-soft like every
    other source. Strengthens the civic-feed moat that already separates
    this site from Eventbrite and AllEvents.

#### P3 (new)

33. ✅ done (PR #51) — **Local-group distribution, in the low-effort form
    only.** No managed community was built (that's a real ongoing-time
    commitment, squarely against the near-zero-time constraint this item
    itself ruled out). Instead, `build_weekly_summary_txt()` generates a
    real, plain-text `/<region>/weekly-summary.txt` at every build — up
    to 6 real dated weekend events, or up to 3 real `free`-tagged
    evergreen highlights when nothing's dated yet, or an honest "nothing
    dated yet" line when there's truly nothing - never an invented event
    to fill space, same discipline as every other view on this site. A
    low-key footer link ("Copy this week's summary") on every region page
    makes it discoverable without turning it into a reader-facing
    feature it isn't meant to be. Grab the URL, select-all, paste into an
    existing local Facebook group - thirty seconds, no moderation duty
    taken on. 4 new unit tests cover the dated/evergreen-fallback/empty
    paths and the 6-event cap.

34. ✅ done (owner-directed, 2026-08-28) — **A considered palette pass.**
    2026's premium direction is sophisticated serif with warm,
    champagne-toned neutrals — softer than the high-contrast era — plus
    transitions that never announce themselves. The Fraunces/Inter pairing
    already fit; the cool-green palette was the part that read a
    generation older. This was explicitly held for the owner's direction
    rather than decided autonomously (a brand/taste call, not an
    engineering one) — asked, and the owner chose the recommended full
    repaint now.
    Kept green as the core accent (it's still a green-pin business,
    already live) but warmed and muted the hue rather than replacing the
    family — light-mode accent moved from a cool forest `#1f4d3a` to a
    warm sage-olive `#526b3f`; `--accent-2`'s orange, already warm-toned,
    only needed a small deepening (`#d9772e` → `#c17a3d`) to fit. Base
    neutrals moved from a cool off-white/near-black-green (`--bg #f7f4ee`,
    `--ink #17231c`) to warm champagne/dark-brown (`--bg #f6efe1`, `--ink
    #2b2318`); dark mode mirrored the same warm shift (`--bg #121c17` →
    `#1c1710`, etc). All four templates share identical `:root` tokens, so
    one consistent edit updated every page. Every ink/bg, muted/bg, and
    white-on-accent-background pairing was verified against the real WCAG
    relative-luminance formula (not eyeballed) before landing — all clear
    AA's 4.5:1 for text, matching the accessibility work already shipped
    in item 31; the deliberately-decorative hero gradient's brightest
    point stays at ~3.6:1, same level the original design already
    accepted there for large/bold heading text (WCAG's large-text
    threshold is 3:1). Deliberately left the categorical tag/status hue
    system (`--hue-*`, `--status-*` — free/indoor/outdoor/kid-friendly
    badges, sponsor availability) untouched: those are functional
    color-coding, not brand identity, and already read fine against the
    new warm background in real screenshots. Verified in both light and
    dark mode, on all four page templates, with real Playwright
    screenshots before shipping.

#### Research pass 2026-08-28 (fifth pass)

Deliberately short. Eight items were still open when this ran, so this pass
adds only what the research actually turned up rather than padding the
queue — including one item recorded as **skipped**, to stop a tempting bad
idea from being re-proposed every pass.

The membership model shipped in PR #50 changed what matters next. A weekly
ad slot is judged on whether it ran; an annual membership is judged, once a
year, on whether it was worth renewing. Nothing in the site currently
produces evidence for that conversation.

| Angle | Finding | Worth stealing |
|---|---|---|
| **Sponsor ROI reporting** | Without structured reporting, publishers "cannot demonstrate consistent ROI, which weakens pricing power and reduces renewal rates." Advertisers have moved past open rates toward attributable outcomes | The renewal half of the membership model — currently missing entirely |
| **beehiiv vs Substack / paid newsletters** | beehiiv runs an ad marketplace that acts as a sales agent (brands accept in one click) and takes 0% of paid subscriptions vs Substack's 10%. Subscription revenue rose from ~30% to ~85% of creator revenue there | The marketplace, which is the only thing found so far that could push sponsor *selling* time toward zero |
| **HTML email in 2026** | Outlook still renders via Word's engine (no flexbox/grid); Gmail clips over 102KB; dark mode behaves three different ways — Apple Mail inverts aggressively, Outlook barely, Gmail partially | A warning, before item 24 gets built the wrong way |

#### P1 (new)

35. ⚠️ first slice done (PR #52) — **Sponsor click reporting and a monthly
    member report.** This is the direct consequence of item 29 shipping:
    memberships renew annually, and the renewal conversation needs
    evidence. The industry finding is blunt — absent structured reporting,
    pricing power and renewal rates both fall.
    Shipped: the active sponsor's outbound "Learn more" link on every
    region page now carries `data-goatcounter-click="sponsor-click-
    {region-id}"` whenever analytics is configured - GoatCounter's
    documented click-event mechanism, which auto-binds elements with that
    attribute to the already-embedded `count.js` script with no extra
    JS of this project's own. Config-gated exactly like every other
    analytics-dependent feature (item 23) - the attribute simply doesn't
    render while analytics stays unconfigured, so this ships zero-risk
    today and activates the moment a real account exists.
    **Not done, and deliberately not attempted**: the actual monthly
    report (impressions, clicks, per-member breakdown) needs GoatCounter's
    stats API, which requires a real account + API token to inspect and
    verify - this sandbox's blocked network means the exact request/
    response shape couldn't be checked. Rather than write report-fetching
    code against a guessed API contract, this slice stops at
    instrumentation. **The GoatCounter click-event attribute name itself
    is unverified against live docs** (this sandbox can't reach
    goatcounter.com either) - confident from training knowledge, not
    confirmed live; worth a real click-through check the first time a
    genuine account is configured, before relying on it for a renewal
    conversation.

#### P2 (new)

36. **Build the email template from scratch — do not reuse the site
    templates.** A gate on items 24 and 31, not a standalone feature.
    Whoever implements the newsletter must know: Outlook (2016–2021) renders
    through Microsoft Word's engine, so no flexbox, no grid, tables for
    layout; Fraunces and Inter will not load, so system fonts only (Arial,
    Georgia, Helvetica); single-column, mobile-first; Gmail clips anything
    over 102KB of HTML and hides the CTA behind a "message clipped" notice;
    and dark mode is three separate problems rather than one. `region.html.j2`
    violates essentially all of this. Reusing it would produce an email that
    looks correct in testing and broken in half of real inboxes.

37. **Decide the newsletter platform deliberately, before item 24 locks it
    in.** Item 24 currently assumes Buttondown, which was chosen for being
    static-site-friendly, not after comparison. beehiiv deserves a look for
    one specific reason: its ad marketplace functions as a sales agent —
    brands are matched to newsletters and the publisher accepts in one
    click — which is the only mechanism found in five passes that could
    reduce sponsor *selling* time toward zero, and selling is the single
    un-automated step left in `BUSINESS_PLAN.md`. It also takes 0% of paid
    subscriptions against Substack's 10%. This is not a recommendation to
    switch; it is a recommendation not to default.

#### Recorded as skipped

38. **skipped — paid reader subscriptions.** Recording the reasoning so
    later passes stop resurfacing it. The trend data is genuinely
    tempting: paid newsletter subscriptions have more than tripled since
    2021, and on beehiiv subscription revenue climbed from roughly 30% to
    85% of creator revenue. It is still wrong for this business. The entire
    proposition sold to a local sponsor is *reach into the town*, and a
    paywall shrinks precisely the thing being sold. `BUSINESS_PLAN.md`
    monetizes businesses, not residents, and that split is the reason the
    owner's time budget works at all — subscribers demand support, refunds
    and churn handling; sponsors don't. The site stays free to readers.

#### Research pass 2026-08-28 (sixth pass)

This pass ran the periodic SERP re-check instead of hunting new features,
and it turned up the most important finding since the moat note in the
third pass — plus two local players six passes of research had missed.

**Process note first:** the open backlog went from 8 items to 10 across
this cycle. Research is outpacing implementation. Until it drains, passes
should stay small and diagnostic (like this one) rather than adding
features, or the build cadence needs to rise.

| Angle | Finding | Consequence |
|---|---|---|
| **SERP re-check** (target query: "things to do in Mount Prospect IL this weekend") | Results are Eventbrite, TripAdvisor, Meetup, Groupon, AllEvents, plus `experiencemountprospect.org` and `mpdowntown.com`. **This site appears nowhere** | Everything shipped in Phase 9 and items 22/28 is compounding into an address with no domain behind it |
| **`mpdowntown.com`** — Mount Prospect Downtown Merchants | An *association* whose members are precisely the target member businesses | Sell once to the association instead of fifty times to its members |
| **`experiencemountprospect.org`** — the Village's own tourism site | The closest thing to a direct competitor found in six passes, and it belongs to the Village | Both a competitor to read and a source to fetch |
| **Seasonal circuits** | WBEZ, Sun-Times, WTTW and Secret Chicago all run annual suburban farmers-market guides; none at ZIP granularity. Downtown Oktoberfest & Fall Festival is Sept 18–19, 2026 | Proven guide format, unoccupied at the local level |

#### P1 (new)

39. **The site is invisible, and the fix needs Ryan, not the build loop.**
    The target query returns seven other results and none of them are this
    site. **Stated honestly:** a web-search sample is not a definitive
    Google SERP, and a site this young would not rank yet regardless — so
    treat this as a strong signal, not proof. But the structural cause is
    not in doubt: the site still lives on a `github.io` path, and Phase 9's
    domain decision has sat open and unresolved since the first day. Every
    SEO and GEO item shipped since — canonical tags, sitemap, JSON-LD,
    `llms.txt`, entity naming, freshness signals — is accruing to an
    address that nobody will link to, cite, or take seriously in a sponsor
    pitch. **This is the single blocking action only the owner can take:**
    pick a domain from the Phase 9 shortlist, register it, and point Pages
    at it. Until that happens, further SEO work has sharply diminishing
    returns, and this item should stay at the top of the list as a standing
    reminder.

40. ✅ done. **Pitch the Downtown Merchants Association, not businesses one
    at a time.** `mpdowntown.com` is the Mount Prospect Downtown Merchants —
    an organised body whose membership *is* the target customer list for
    the annual memberships shipped in PR #50. One conversation with an
    association could place many memberships; the current plan is fifty
    individual cold emails. For an owner with 30–60 minutes a month, this
    is the highest-leverage sales motion available, and it is the kind of
    thing no amount of site polish substitutes for. Added Template #6,
    "Downtown merchants association pitch," to `OUTREACH_TEMPLATES.md`
    alongside the per-business ones: it frames a group discount (default
    15% off Annual Partner, `[month/window]`-bounded), is explicit that the
    directory listing and guide spotlight are non-exclusive (every joining
    member gets both at once) while the front-page rotating recommendation
    slot stays a single per-region seat, and offers a one-pager or a
    five-minute meeting rundown as the low-friction next step. Written
    generically (`[Association Name]`, `[region]`) so it applies to
    Arlington Heights' equivalent body too, not just Mount Prospect's —
    every region is assumed to have one. This is a sales-copy change only;
    no code or template logic touched.

#### P2 (new)

41. ✅ done. **Add `experiencemountprospect.org` and `mpdowntown.com` as
    sources.** Two live, local, currently-unfetched event feeds — the
    Village's own tourism site and the downtown merchants' events page.
    Added as two new `html_events` sources ("Things To Do" and "Downtown
    Events") in `config/regions/mount-prospect-60056.yaml`, fail-soft like
    every other source. URLs (`experiencemountprospect.org/events/` and
    `mpdowntown.com/events/`) are a best guess at each site's events
    listing page, same unconfirmed starting point every other source here
    began from — no `detail_link_pattern` set yet, so this relies on the
    keyword fallback until a real link structure is confirmed the way
    Village News, the library, and vah.com's were. Worth noting the
    competitive angle too: the Village's tourism site is the nearest thing
    to a direct competitor found so far, and since it is the Village's
    own, the right posture is to aggregate and credit it, not to try to
    outrank it. Not extended to Arlington Heights — no equivalent tourism
    site or downtown merchants body has been confirmed to exist for it,
    same reasoning item 42 already recorded for its Seasonal Circuit
    Guide; add one if a real link surfaces.

42. ✅ done (Mount Prospect). **Seasonal circuit guides — farmers markets,
    Oktoberfest, restaurant weeks.** WBEZ, the Sun-Times, WTTW and Secret
    Chicago all publish annual suburban farmers-market guides, so the
    format is proven and competitive at metro scale — but none of them
    work at ZIP granularity, which is exactly the gap this site occupies.
    Added a "Seasonal Circuit Guide" to Mount Prospect covering the
    downtown fall festival (linked to `mpdowntown.com`, the merchants
    association's own site), the Village-run farmers market/seasonal
    events (linked to the Village Calendar source added this session),
    and Park District seasonal programming. Deliberately didn't repeat the
    research pass's specific "Sept 18–19 2026" date claim in the guide
    itself — a wrong specific date is worse than none, and the whole point
    of linking to the organizers' own pages is that they're where that
    year's real schedule actually lives, same discipline as the fall
    family and birthday-party guides. **Arlington Heights doesn't have
    this guide yet** — its equivalent of `mpdowntown.com` (a downtown
    merchants body) hasn't been confirmed to exist or found, so nothing
    was invented for it; add it once a real link surfaces, the same way
    AHML's and the Village's real link structures got confirmed this
    session.

#### Research pass 2026-08-28 (seventh pass)

Twelve items were open when this ran, so the bar for adding anything was
high. Three cleared it — two of them **corrections to work already
shipped**, which is the kind of finding this loop exists to catch.

| Angle | Finding | Consequence |
|---|---|---|
| **Google structured-data changes** | Google discontinued FAQ rich results on **2026-05-07**, following HowTo. Event schema still requires name + startDate + physical location; online-only events remain ineligible | The stated justification for PR #46's FAQPage work no longer holds |
| **Schema accuracy under AI** | In late 2026 AI systems begin cross-referencing schema claims against live sources and **penalising** inaccurate schema rather than ignoring it | The Event `location` approximation changes from harmless to risky |
| **Red Tricycle / Tinybeans** | Not a cautionary tale — Red Tricycle reached 20M+ monthly users and sold for **$6.5M in 2020**. On consolidation into Tinybeans in 2021, the headline change was personalisation by **children's ages**, location and interests | Local family discovery is a proven, acquirable asset; age is the axis the category leader converged on |

#### P1 (new)

43. ✅ done — **FAQPage schema no longer earns rich results — correct item
    22's rationale.** Google discontinued FAQ rich results on 2026-05-07,
    after the earlier HowTo removal, on the grounds that both created
    clutter without helping users. PR #46 shipped `build_guide_faq()` and
    `build_faq_json_ld()` on the explicit rationale of rich-result
    eligibility, and that rationale is now dead.
    **Not a request to rip it out:** structured data still feeds AI parsing
    and E-E-A-T signals, so the markup may still earn its keep — it just
    earns it for a different reason. Item 22's notes now carry a
    correction paragraph saying so, so the roadmap stops repeating a dead
    justification.

44. ✅ done — **Schema accuracy is becoming a liability, not just a missed
    opportunity.** `build_event_json_ld()` emitted a region-level
    `location` — town, state, ZIP — rather than the actual venue,
    documented in the source as an honest approximation because the
    fetchers don't expose structured addresses. That reasoning was sound
    when the worst case was "less precise than it could be." It stops
    being sound once AI systems cross-reference schema against live
    sources and penalise mismatches: an event at a specific venue, marked
    up with the town centre, reads as *wrong* rather than *approximate*.
    Took the cheaper of the two honest fixes: `location` is now omitted
    entirely (no source in this codebase provides a real per-venue
    address, so "unknown venue" is every event's actual state, not a rare
    exception). The unused `region` parameter was dropped from the
    function's signature along with it. Finishing Phase 8's parked
    geocoding note would let this be reinstated with real addresses
    someday; not attempted here since that needs live network access this
    sandbox doesn't have.

#### P2 (new)

45. ✅ done — **Age-banded tags: toddler / elementary / teen.** Red
    Tricycle was the largest parenting brand in local discovery — 20M+
    monthly users, sold for $6.5M — and when Tinybeans absorbed it, the
    flagship improvement was personalisation by children's ages. Today
    "kid-friendly" is a single bucket spanning a seventeen-year range; a
    toddler storytime and a high-school battle of the bands both carried
    it, and they're almost never relevant to the same reader.
    Three new orthogonal tags (`toddler`, `elementary`, `teen`) added to
    `tagging.py`'s existing keyword-heuristic, fail-soft `infer_tags()` -
    same mechanism as `kid_friendly`/`dog_friendly`, not a new system.
    **A real false-positive caught before shipping**: bare "teen"/"tween"
    are substrings of number words (thir**teen**, four**teen**,
    be**tween**) - an event description mentioning a headcount would have
    mis-tagged. Fixed with the same space-padding trick `free` already
    used for the same class of problem (` teen `, ` tween `); their
    plural/derived forms (`teens`, `tweens`, `teenager`) don't have this
    problem and stay unpadded. Caught by a dedicated regression test, not
    just noticed by inspection.
    Three new badge hues added (`lime`/`toddler`, `cyan`/`elementary`,
    `indigo`/`teen`) rather than reusing existing ones - two different-
    meaning badges sharing a color would be confusing on a card that
    carries both (e.g. a "teen art class" showing indigo `teen` next to
    what would've been an identically-colored purple `art_culture`).
    Every new light/dark ink-on-bg pairing verified against the real WCAG
    formula before landing (one, light-mode lime, needed darkening from
    4.38:1 to 5.48:1 to clear AA). Applied the `teen` tag to two evergreen
    library entries (Mount Prospect and Arlington Heights) whose own
    existing detail text already said "kids and teens" - not a new claim,
    just tagging what was already truthfully there. Verified end-to-end
    with a real Playwright screenshot of the rendered badge before
    shipping.

**Validation note, worth recording for `BUSINESS_PLAN.md`:** the research
kept implicitly treating this category as unproven. It isn't. Red Tricycle
started in 2010 as one founder's side project and sold for $6.5M in 2020,
and Family Focus Media (fourth pass) has run the same model profitably
since 2010. The thesis is sound; execution and distribution are the
variables.

#### Research pass 2026-08-29 (eighth pass)

The newsletter cluster (items 24, 31, 36, 37) is the largest untouched
block in the backlog, so this pass researched what actually happens when a
site like this sends its first email. The answer changes the priority of
something already on the list.

| Angle | Finding | Consequence |
|---|---|---|
| **Bulk-sender rules, 2026** | Gmail, Yahoo and Microsoft all require SPF, DKIM **and** DMARC. One-click unsubscribe via `List-Unsubscribe` + `List-Unsubscribe-Post` (RFC 8058), honoured within two days. Spam complaints under 0.3%, ideally 0.1% — and recovery from a breach is slow | You cannot authenticate mail without a domain you control, so item 39 blocks the newsletter too |
| **Event syndication** (Eventbrite → Bandsintown, AllEvents' 40,000 cities) | The mechanism exists and is genuinely frictionless for event *owners* | Not applicable here, and worth recording as such — see item 48 |

#### P1 (new)

46. **The unregistered domain blocks the newsletter too — item 39 is now
    two workstreams deep.** The sixth pass framed the missing domain as a
    findability and credibility problem. It is also a hard technical
    prerequisite for items 24, 31, 36 and 37: Gmail, Yahoo and Microsoft
    now require SPF, DKIM and DMARC on bulk mail, and **none of those can
    be published without a domain under the owner's control.** Sending the
    weekend email from a provider's shared subdomain, unauthenticated, is
    a direct route to the spam folder — and a newsletter that lands in
    spam is worse than no newsletter, because the list is spent and the
    complaint history follows the sender.
    Item 39 therefore stops being "important for growth" and becomes
    **the single blocker on two separate workstreams**. It remains the one
    thing the build loop cannot do; it needs Ryan to register a name from
    the Phase 9 shortlist.

#### P2 (new)

47. **Deliverability checklist — a gate on items 24 and 31, not a
    feature.** Before any first send, the following must be true, and
    whoever implements the newsletter should treat this as acceptance
    criteria rather than nice-to-have: SPF, DKIM and DMARC all published
    (`p=none` is an accepted starting posture, with the expectation of
    progressing toward `quarantine` or `reject`); one-click unsubscribe
    implemented as `List-Unsubscribe` **and** `List-Unsubscribe-Post`
    headers per RFC 8058, working without requiring a login and honoured
    within two days; spam-complaint rate held under 0.3% and ideally under
    0.1%; TLS in transit; valid forward and reverse DNS on the sending IPs.
    A managed provider (Buttondown or beehiiv — see item 37) handles nearly
    all of this **only once the sending domain is authenticated with it**,
    which routes straight back through item 46 to item 39. Sequence is:
    domain → authentication → provider → first send.

#### Recorded as skipped

48. **skipped — syndicating our listings out to Eventbrite / AllEvents /
    Bandsintown.** The mechanism is real and tempting: publishing to
    Eventbrite auto-distributes music events to Bandsintown's fan base,
    and AllEvents spans 40,000 cities. It is still wrong here, for a
    reason that won't change. This site **aggregates** events run by the
    Village, the library, the park district and the downtown merchants —
    they are not ours to republish onto commercial platforms under our own
    submission, and doing so would feed listings straight to the
    competitors currently outranking us in the sixth pass's SERP check.
    The flow should run the other direction, as item 41 proposes: fetch
    locally, credit the source. Don't revisit.

#### Research pass 2026-08-29 (ninth pass)

`BUSINESS_PLAN.md` has been updated with the membership tiers from the
fourth pass — Annual Partner at $1,200/yr, Neighborhood Authority at
$5,000/yr — so the research → roadmap → plan loop is now closing properly.

**Re-rank first, because the shape of the backlog matters more than
anything below:** of eleven open items, **six are the newsletter cluster
(24, 25, 31, 36, 37, 47), and every one of them is blocked behind item 39 —
registering a domain, which only Ryan can do.** The build loop should not
sit idle waiting on that. Both items below are deliberately chosen to be
unblocked, and item 49 in particular should be picked up ahead of anything
in the newsletter block.

| Angle | Finding | Consequence |
|---|---|---|
| **6AM City's seed-market model** | 400+ local newsletters "built and sent by AI, untouched by humans", launched in towns as small as **20,000 people** for "pennies a day", profitable at roughly $1 CPC and a couple of clicks, monetised through a self-service ad platform | The architecture here already is that model; the plan has implicitly chosen the opposite strategy without saying so |
| **New-mover marketing** | New movers spend **$9,000–$10,000+ in their first year** on furniture, appliances and home services. Welcome Wagon exists solely to reach them; one welcome guide was funded by a National Association of Realtors grant | The single highest-value content type for the $5,000/yr real-estate tier just added |

#### P1 (new)

49. ✅ done. **A "New to town" newcomer guide per region.** This is the
    content the Neighborhood Authority tier exists to sponsor, and it was
    unblocked. New movers spend $9,000–$10,000+ in their first year on
    furniture, appliances and home services, which is why Welcome Wagon is
    a whole business and why realtor associations fund welcome guides
    outright.
    Shipped: a `new-to-town` guide added to all three regions' `guides:`
    list — no new code, purely config, exactly like item 27's third
    region turned out to be. Five items each: Village/City services +
    utilities + vehicle stickers, a library card, Park District
    registration, "find your school district," and (Mount Prospect only,
    since it's the only region with a confirmed downtown/tourism source)
    a downtown/nearby pointer. All five link only to domains already
    established in that region's own config — no new URLs invented for
    this guide specifically. **"Find your school district" deliberately
    has no url**: Illinois suburbs are typically split into separate
    school districts by home address rather than village boundaries, and
    no specific district site has been confirmed for any of the three
    regions, so this states the true general fact rather than guessing a
    link — confirmed safe (renders as plain text, not a broken link) by
    reading `region.html.j2`'s card template, which already guards every
    guide-item link with `{% if item.url %}`, and confirmed with a real
    Playwright screenshot (light + dark) that it renders correctly and
    that `build_event_json_ld` never touches guide items regardless
    (it only includes items with `date_iso`, which guides never set).
    It is evergreen (no weekly decay) and the natural landing page for
    anyone searching "moving to Mount Prospect."

#### P2 (new)

50. ✅ done. **Choose the scale strategy deliberately — few regions sold
    well, or many regions monetised thinly.** 6AM City runs 400+ markets with AI
    sending the newsletters untouched, viable in towns of 20,000, earning
    "dollars at best" per market per day and profitable anyway because
    there are hundreds of them. This site's architecture *is* that model —
    the marginal cost of region four is one YAML file, as Des Plaines just
    demonstrated in PR #67.
    The business plan has implicitly chosen the opposite: few regions, sold
    well, $1,200–$5,000/yr memberships, high-touch. That is very likely
    right for an owner with 30–60 minutes a month, because the thin model
    depends on programmatic and self-service ad infrastructure that does
    not exist here. But the choice should be **stated rather than drifted
    into**, because it decides whether adding regions five through ten is
    the main growth lever or a distraction.
    The honest middle: keep monetising few regions deeply, but keep adding
    neighbouring towns anyway — they cost almost nothing, they make the
    "trip across a few nearby towns" promise in the Vision real, and they
    widen the surface that starts earning the moment a domain exists.
    **Caveat worth respecting:** each new region is another set of feed
    URLs nobody has verified, so growth should stay gated on the fetchers
    failing soft, which they do.
    Shipped: recorded as a real decision in `BUSINESS_PLAN.md`'s new
    "Scale strategy" section, in the same place item 29's monetization
    finding got incorporated - not left implicit in this roadmap alone.
    States the "honest middle" above as the actual chosen policy, not
    just a suggestion, so future sessions (this loop included) treat
    adding a fourth-plus region as expected, ongoing work rather than a
    question to keep re-raising.
    Acted on immediately: Palatine (60067) added as
    `config/regions/palatine-60067.yaml`, the fourth region and the next
    name on item 27's original shortlist (Des Plaines, Palatine, Elk
    Grove Village) — same unconfirmed-domain, fail-soft posture as every
    region before it, same three guides (fall, birthday/kids'-classes,
    new-to-town per item 49) shipped from day one instead of backfilled
    later. Verified with pytest, a full digest build, and a Playwright
    screenshot of the hub page confirming all four regions render and the
    distance-comparison map correctly plots all four.

#### Field note 2026-08-29: first real confirmation of live fetch status

Every region config's "not yet confirmed against a live run" caveat has
been repeated since Phase 5 because this sandbox's own network is
blocked. It was never checked against what the real GitHub Actions build
(which has real network access) actually logs — until now. Read
`build-digest.yml` run 33246555815's job log directly (09:54 UTC), not
generated HTML, and updated all four region configs' header comments with
the precise, dated result per source. The shape of it:

| Region | Confirmed working | Blocked (403, real domain) | Wrong domain (connection/SSL error) |
|---|---|---|---|
| Mount Prospect | Library (mppl.libnet.info), Park District (mppd.org) | Village News, Village Calendar, Experience Mount Prospect | — |
| Arlington Heights | Library, Park District (both real) — Village News resolves but only via keyword fallback | — | — |
| Des Plaines | Library (dppl.org), Park District (dppd.org) — both real, low-precision matches | — | City News (desplaines.org — connection reset) |
| Palatine | Park District (palatineparks.org) | Library (palatinelibrary.org) | Village News (palatineil.gov — TLS error, wrong hostname) |

Two real, previously-unknown facts worth remembering: (1) `mountprospect.org`
and `experiencemountprospect.org` actively 403 this fetcher's plain
`requests` User-Agent — the URLs are very likely right, this needs a
different fetch approach (not more URL guessing) if it's ever worth
revisiting; (2) `palatineil.gov` is very likely the wrong hostname
entirely (TLS handshake fails, not a 403/404) — no confident replacement
guessed yet, left as-is since it fails soft regardless. Every region
still builds and serves real content either way — the point of recording
this isn't to fix everything at once, it's to stop guessing blind about
sources this exact evidence has already settled.

**Follow-up, same day:** acted on the one finding with a clear, low-risk
fix. Des Plaines Park District's real event linked to
`dpparks.org/event/13491/`, which matches `fetchers.py`'s *default*
detail-link pattern (`/event/\d+`) with no config override needed.
Switched that source's `url` from `dppd.org/events` to
`dpparks.org/events` directly, betting that the real listing page
surfaces more than the one item `dppd.org` incidentally linked to.
Evergreen/guide links still point at `dppd.org` (the confirmed-resolving
domain) since there's only one data point suggesting `dpparks.org` is the
canonical site, not enough to redirect human-facing links too. Next real
build's log is the check for whether this paid off.

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
