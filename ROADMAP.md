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

1. ✅ done (PR #19, hub-level fast-follow PR #21) — **Date-scoped,
   linkable views: `/this-weekend`, `/today`, `/free`.** Each region has
   three extra static pages, distinct `<title>`/description per view, and
   a small nav row. `docs/this-weekend/` merges every region's weekend
   events into one page (grouped by region, regions with nothing dated
   simply omitted), linked from the hub via a callout banner. Scoped to
   events with a resolved `date_iso` (currently the ICS-sourced Park
   District events only — see item 4's note, still unresolved for
   HTML-scraped sources).

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

4. ⚠️ partially done (PR #17) — **Real datetime normalization + a
   structured-data coverage stat.** `_try_parse_date` (renamed from
   `parse_event_date_iso`'s inline logic) now handles RFC 822/ICS plus
   several common human-readable formats, and `structured_date_coverage()`
   logs `N/M events have a machine-readable start date` per region and as
   a build total. **Still blocking item 1**: `fetch_html_events` in
   `fetchers.py` doesn't extract a date at all today — only RSS/ICS
   sources populate `date` — so the broadened parser has nothing to parse
   for HTML-scraped events yet. Real fix needs either fetching each
   event's detail page or parsing text near each link in the surrounding
   DOM; both need real fetched HTML to design against rather than a
   blind guess (this sandbox's network is blocked). Next research-loop
   pass: if you can reach a live source, note what a real scraped
   `<a>` tag's surrounding HTML actually looks like (e.g. a sibling
   `<span class="date">`) so this can be finished with real structure
   instead of another guess.

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

8. **Bento-grid hub layout + a "This weekend at a glance" block.** Bento
   grids are the dominant 2026 editorial layout; the hub's uniform 3-up card
   grid reads generic next to one. Asymmetric blocks — a big "this weekend"
   tile, smaller region tiles, a stat tile ("3 towns · 58 events this week") —
   would make the hub look designed rather than generated.

9. **Scroll-reveal motion** via `IntersectionObserver` + CSS transitions,
   gated on `prefers-reduced-motion`. Hardware-accelerated properties only,
   no framework, no measurable Core Web Vitals cost. The cheapest available
   difference between "a static page" and "a designed site" on first scroll.

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

19. **Do item 9 in pure CSS instead.** `animation-timeline: view()` ties
    keyframes directly to an element's viewport progress with no scroll
    listeners and no JavaScript at all, and it's broadly supported now.
    Strictly better than the `IntersectionObserver` approach item 9
    originally proposed — **supersedes it**; `prefers-reduced-motion` still
    applies.

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

21. **Container queries for the card component.** At universal support and
    "just use them" maturity in 2026. Cards currently size off the
    viewport; container queries let one card adapt to whichever column it
    lands in — which starts to matter the moment item 8's bento layout
    puts cards into differently-sized slots. Do this *with* item 8, not
    before it.

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

22. **Get cited by AI search (GEO), as a deliberate strategy.** Under 10%
    of AI-cited sources rank in Google's top 10 for the same query, so the
    Phase 9 SEO work does **not** buy this channel — and AI Overviews now
    trigger on roughly half of all queries. Concretely: a hand-written
    `llms.txt`; an AI-crawler-aware `robots.txt` that *explicitly* allows
    GPTBot / ClaudeBot / PerplexityBot / Google-Extended rather than
    leaving it unstated; a 40–60 word answer block at the top of each
    region and guide page (literally answering "What's happening in Mount
    Prospect this weekend?"); `FAQPage` schema on the guides; and
    consistent entity naming across pages.
    **The strategic point worth stating out loud:** content updated within
    30 days earns ~3.2× more AI citations, and this site rebuilds itself
    every week. Automated freshness is a structural advantage over every
    hand-written competitor guide — Time Out's "54 Best Things to Do"
    piece decays the moment it's published; this doesn't. That is arguably
    the strongest moat in the whole business, and right now it's an
    accident rather than a strategy.

23. **Analytics — the first number every sponsor will ask for.** The
    self-serve sponsor page shipped in item 3, but there is nothing to
    put in it: traffic is currently unknown, which makes the price a
    guess and the pitch unprovable. GoatCounter is a ~1KB cookie-free
    script needing no consent banner, with a free hosted tier — the right
    size here. Gate it behind a config flag exactly like the Buttondown
    embed in item 12, add a privacy line matching the existing
    geolocation note, and once real data exists, surface a rolling
    "≈N readers/month" on `/sponsor`. **Blocks nothing technically and
    unblocks the entire monetization story.**

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

26. **Performance budget in CI.** The site has quietly accumulated real
    JavaScript — filters, distance sort, itinerary tray, weather, map,
    view transitions — and none of it has ever been measured. Add
    Lighthouse CI to the existing tests workflow with a JS-bytes cap and
    thresholds at the 2026 bar (LCP ≤2.5s, CLS ≤0.1, TBT as the lab proxy
    for INP ≤200ms), so the *next* feature fails the build instead of
    quietly degrading the site. This is insurance on everything shipped in
    PRs #15–#39, and it matters more now than any single new feature.

#### P3 (new)

27. **Third region — now worth more than when Phase 10 parked it.**
    Distance sort (Phase 8), the hub map (item 17) and the guides (items
    5 and 15) all get better with more towns, and each region is another
    sponsor slot at zero marginal cost. Des Plaines (60016), Palatine
    (60067) or Elk Grove Village (60007).

28. **Visible freshness signals.** A human-readable "Updated <date>" plus
    `dateModified` in the JSON-LD. Trivial to add, and it's the exact
    signal both AI citation and human trust key on — the cheapest possible
    down-payment on item 22.

**Re-rank:** item 4 (datetime normalization, still ⚠️ partial) should move
up. It was originally justified by Google event rich results; item 22 makes
it matter twice over, since an event an AI can't read a start time from is
an event it won't cite. It is now the oldest unfinished thing blocking the
newest priority.

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
