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

### Phase 8 — Distance from the user, per event (region-level v1 shipped PR #12, geolocation removed 2026-09-15)
Requested 2026-08-26: show how far away each event/region is from the
person viewing the site.

Shipped originally (v1, region-level — the honest starting point given
the data we actually have):
- ✅ Village-center lat/lon added to each region's config (still in use).
- ~~Client-side only: a "Show distance from me" button (browser
  Geolocation API) computes straight-line (haversine) distance to each
  region's center in plain JS, shown on the hub page's region cards
  ("≈4.5 mi away") and re-sorts them nearest-first.~~
- ~~Manual-ZIP fallback for denied/unavailable geolocation (a small
  hardcoded table of nearby Chicago NW-suburb ZIPs).~~
- ~~Privacy note in the UI: computed entirely in the browser, never sent
  anywhere.~~

**Removed 2026-09-15, owner-directed** (commit `862cd1c`): the geolocation
button, its manual-ZIP fallback and hardcoded coordinate table, the
per-card distance label, the privacy note, and the ~80-line script itself
are all gone. Deliberately kept, because neither uses geolocation and the
owner didn't ask for them to go: the build-time "Nearby: Arlington
Heights ~2.7 mi" strip on region pages (server-computed from each
region's own lat/lon, no browser permission needed) and the distances
already drawn on the inline SVG region map. The village-center lat/lon in
each region's config stays too, since both of those still read it.

Later (bigger lift, not this phase): per-event distance would need actual
venue coordinates, which means geocoding addresses extracted from event
listings during the build (most current sources don't expose a structured
address at all, only a title/detail blob) — likely a free-tier geocoding
API called during `build_digest.py`, cached to stay within rate limits.
Worth doing once regions multiply enough that "which specific event is
closest" actually matters more than "which town is closest." Not a
justification to bring geolocation itself back, though — that was a
direct owner call, not a build-loop finding to second-guess.

### Phase 9 — SEO plan + domain name (technical slice ✅ done, PR #10; domain registered 2026-09-15, DNS/Pages setup still open — see "Needs Ryan")
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
- **Before shipping a 5th region**: grep for hardcoded "four towns"/"four
  ZIPs" first (`templates/hub.html.j2`'s hub subheading,
  `templates/combined_email_digest.html.j2`'s intro line, and
  `build_llms_txt()`'s "all four towns" trick-or-treat line in
  `scripts/build_digest.py` are the ones as of the twenty-ninth pass's
  own follow-up cycle) - none is wrong today at exactly four regions, so
  not worth templating dynamically ahead of that need, but a real,
  findable staleness risk the moment a fifth ships. `SPONSOR_KIT.md`'s
  "All four ZIPs" line is hand-maintained prose, not generated - update
  it by hand same as any other fact there.

### Phase 11 — Competitor-informed idea backlog (fed by a 6-hourly research loop)

A second scheduled loop (separate from the hourly build loop) researches the
business plan + competitor sites every 6 hours and appends/refreshes ideas
here. **This section is the implementation loop's queue** — when Phases 5-10
have nothing pressing, pick the highest unclaimed `P1` item below. Mark items
`✅ done (PR #N)` in place rather than deleting them, so the research loop
doesn't re-suggest something already shipped.

#### Needs Ryan

Everything below blocks on one person taking a real action outside this
repo. **Restructured per item 165, 2026-09-21.** The flat list this
section used to be had grown to ten rows, six of them real judgment
calls, none acted on in a week — and item 165's finding was that
presenting six roughly-equal-looking options is itself why nothing gets
picked: a queue that size in front of someone with an hour a month
functionally reads as no queue at all. The fix is the research loop's
own job, not the owner's: rank the decisions and name **one** next
action instead of handing back a list. Standing rule (also in the
working agreements below): the research loop leaves at most three open
owner *decisions* at a time, ranked, not appended to indefinitely.

**Next action.** **Put a real name on the About page** (item 130) —
currently "written and run by a local parent." Takes minutes, costs
nothing, and is the one prerequisite the other two items below actually
depend on: a reporter won't write about an anonymous site, a library
won't link to one as readily, a business owner won't sponsor one. An
anonymous automated local-events site also now pattern-matches to the
200+ AI-generated "local news" sites shut down in August for invented
bylines — the press pitch, sponsor conversations, and the "we're not
one of those sites" claim (item 124) all sell the person, not just the
product. A first name + last initial beats full anonymity by a wide
margin if full disclosure isn't wanted. This is the owner's own privacy
to trade, which is exactly why it's a decision and not a default.

**After that, in order:**

1. **Send the outreach emails** — six civic-source link-back emails
   (item 152, `OUTREACH_TEMPLATES.md` §11, one per village/library/park
   district across all four regions) plus the two already-drafted,
   ready-to-send Mount Prospect emails (item 161, §12a/12b — send
   Experience Mount Prospect first, let its reply inform Downtown Mount
   Prospect's). No cost, repeatable, no deadline, and the most durable
   result of anything in this section: item 131 verified 19/19 event
   cards already link out to the publisher that posted the event, so
   every issue already sends these organizations readers — a community-
   links-page entry, once added, keeps working without further effort.
2. **Send the local press pitch** to the **Daily Herald first** (item
   125 found Journal & Topics runs a competing Event Calendar, so
   Daily Herald is the first attempt, not the second; template in
   `OUTREACH_TEMPLATES.md` §7). The single highest-yield action
   available — 100-500 subscribers from one email (seventeenth pass) —
   but one-shot, and item 155 argues it should follow gradual list
   growth (item 1 above) rather than lead it, so a press-driven spike
   lands on a domain with real sends behind it already. Every technical
   dependency is cleared: domain, HTTPS, signup form, sponsor CTA,
   Google's sitemap, and a proven live send all work.

**Parked — real, but shouldn't compete with the two above:**
- **Chamber of Commerce membership** (item 153) — a real backlink and a
  prospect directory, but a recurring cost, and `BUSINESS_PLAN.md`
  assumes zero spend.
- **Illinois DBA / Fictitious Business Name filing** (item 154) — the
  real blocker to Nextdoor's free Business Page, per that item's own
  investigation. $50 plus a three-week newspaper-publication
  requirement — a real cost and multi-week timeline, not a quick
  decision.
- **Meta geo-targeted ads** (item 78) — a bounded, low-cost test in
  principle, but a spend decision `BUSINESS_PLAN.md` doesn't assume,
  parked alongside the other two money questions rather than competing
  with the two free, no-deadline actions above.

**Small, no-decision-required — do whenever convenient, no ranking
needed because none of these compete with anything above:**
- Run a real trademark search before spending on signage, print, or
  sponsor contracts (item 69) — "Within Ten"/"WithinTen" turned up no
  registered mark by web search, materially cleaner than the rejected
  "PORCHLIGHT" name, but a web search isn't a clearance search.
- Check **Settings → Subscribing → Welcome** in Buttondown's dashboard
  and enable one welcome email if free-plan-available (item 106) —
  welcome emails average 34.79% opens, up to 4× a regular issue's; the
  cost question (is the one-off transactional toggle free, distinct
  from the confirmed-$29/month automations feature) can only be
  answered inside the account.
- Send the newsletter cross-recommendation email to Northwest Neighbor
  (item 25, `OUTREACH_TEMPLATES.md` §10) — a free weekly newsletter
  covering overlapping northwest suburbs, complementary rather than
  competing; publishers who recommend others are 32× more likely to be
  recommended back.
- Enable Cloudflare's free DMARC Management (item 156; Postmark's free
  digest is the named fallback) — the owner currently gets zero
  deliverability reporting; a dashboard toggle, not a hand-written DNS
  record, best done before item 77's press-driven volume spike.
- Open **mountprospect.org/community/hidden-page/new-advanced-components/list-all-rss-feed**
  (item 179) and paste back the actual "Village News" feed URL it
  links to — confirmed real and live by WebSearch, but the click-
  through URL itself isn't something this loop can reach from its own
  blocked sandbox (confirmed directly: both `requests` and this
  sandbox's own Playwright/Chromium hit the same tunnel block against
  external domains, not just the `requests`-only limitation earlier
  passes assumed). Thirty seconds in a browser; unblocks a real fix
  for Mount Prospect's dead Village News source without guessing a
  feed-URL pattern.

**Time-boxed, not a decision:** check Buttondown's dashboard on
2026-09-23 (send-newsletter.yml's cron fires ~5:37pm Chicago Wednesday
the night before) to confirm item 110's `schedule` mode actually
worked — item 151 fixed a real `publish_date` format mismatch against
Buttondown's documented API shape, so this is now docs-verified but
still not live-API-verified; a failed run surfaces loudly by design, so
check either way.

Update, same day (item 172): that Wednesday run will very likely fail
by design, not by accident. The live build this pass produced counted
only 1 dated event across all five regions — well under the floor
item 172 just added — so `send_newsletter.py` will refuse and the
workflow will show red. That is the intended behavior, not a bug to
chase: it is the guard stopping the first-ever scheduled send from
going out as a one-event issue. If Wednesday's real count is still
under the floor, this is exactly item 172's second decision, now live
rather than hypothetical: let it skip (recommended — nothing else to
do), or run `python scripts/send_newsletter.py --force-thin` by hand
to send anyway. Either way it's a one-line decision, not new
investigation, since item 159's source-health re-verification is the
actual fix and is already the loop's own standing work.

**Closed since the last check:** `BUTTONDOWN_API_KEY` — the owner added
it, and it works. Real evidence, checked directly against GitHub
Actions rather than assumed: workflow run `35176614362` (2026-09-17
03:02 UTC) shows `=== LIVE: this will SEND to every subscriber ===`,
`Region: combined`, `Subject: This weekend across Arlington Heights,
Des Plaines, Mount Prospect, and Palatine`, and `Sent. Buttondown id:
em_5hgyjgfytf8hws9xxpw6b0fesk` — a genuine successful live send of
item 105's combined template, not a dry run. (One earlier manual run,
`35176398162`, failed on a `400 sending_requires_confirmation` from
Buttondown's own first-API-call interlock; the very next commit added
the required header and the next run succeeded.)

**Closed since the last check:** "Allow GitHub Actions to create and
approve pull requests" (item 13) — Ryan flipped it 2026-09-20. Not
just trusted: live-verified with a third test issue (#199, closed)
immediately after. It worked completely — real run `35509989841`
succeeded, and the resulting PR (#200) had a clean, correctly-formed
7-line diff to `config/regions/palatine-60067.yaml`, nothing corrupted.
Closed #200 without merging (test content) and #199 with the
confirmation. The community event-submission feature now works
end-to-end for the first time since it shipped in PR #31.

**Nearly done, no longer blocking:** Buttondown's sending domain (item
47). The owner added `withintenmiles.com` and its managed-delegation NS
records on 2026-09-16 and confirmed them in place; what remains is
checking that Buttondown's own settings show it verified, which is a
look rather than a task. Worth noting the managed option **avoided** the
SPF collision this file warned about earlier: because Buttondown's
records live inside a delegated subdomain, the apex SPF stays free for
Cloudflare Email Routing later. No merge needed.

**Also worth doing, not blocking:** import the GSC property into Bing
Webmaster Tools (part of item 73). It skips re-verification entirely and
covers Bing, Yahoo and DuckDuckGo - and Bing's index feeds ChatGPT
search, which item 22's whole AI-citation effort depends on.

#### Competitors reviewed (2026-08-27)

| Site | What it is | Worth stealing |
|---|---|---|
| **Do312** (DoStuff Media) | Chicago events, the best-designed thing in this space | URL-addressable date/category views (`/events/today`, `/events/weekend`, `/free`) instead of client-side-only filters |
| **Macaroni KID** | ~500 hyperlocal family newsletters + sites, publisher-run, sponsor-funded | Seasonal *guides* (summer camps, "kids eat free", Halloween) as the flagship monetizable product; business directory; weekly + monthly calendar views |
| **6AM City** | 400+ local newsletters, $9.5M rev, profitable in 2026 | **Self-service ad platform** — they built it because low-average-order-value local sponsors don't justify sales time. Directly targets this business's #1 constraint |
| **Axios Local** | Local newsletter network, local-advertiser funded | Newsletter-first: the list is the asset, the site is the funnel |
| **`data/source_health.json`, read properly** | 16 sources live, **4 returning zero — all four of them Mount Prospect's village layer**. And every healthy source returns **exactly 6, every single build**, because `fetchers.py` sets `MAX_ITEMS_PER_SOURCE = 6` | The thin weekend is a fetch-time cap, not quiet towns (items 178/179) |
| **The redesign, inspected** | Site and email both now run **grey `#f3f2f2` with a red accent** (`#ec3013`/`#ae1800`) and Archivo — consistently, in both artifacts. But `DESIGN_PRINCIPLES.md` still says **"a beige/green palette"** and that it was written "as a **defence**, not that anything needs redesigning" | The guard document now contradicts the site it guards (item 176) |
| **The live pages, re-inspected** | Palatine's **entire** dated inventory is last weekend (Sep 18–20 Oktoberfest, all past). Arlington Heights carries **"Tween LitCrate Sign Up" from Sep 1** and "Baby Time" from Sep 2. Several entries appear **twice** | Past events are being served as current content, on the site whose claim is freshness (items 171/173) |
| **The site's own live output** (inspected, not researched) | The committed build is stamped `2026-09-21T01:54Z` — Sunday evening in Chicago — and still headlines **"Sep 18–20"** as *this weekend*. It is now Monday there | The freshness claim items 162/163 rest on breaks every Monday morning (item 168) |
| **Neighbouring towns** (expansion candidates) | **Wheeling** 38.3k, **39% of households with children under 18**; **Elk Grove Village** 32.8k but **shrinking ~0.6%/yr**; **Rolling Meadows** 24.2k; **Prospect Heights** 16.1k and the oldest (18.7% over 65, 21.1% under 18) | Wheeling is the clear next region on family density; Prospect Heights is the weakest fit (item 166) |
| **AI citation concentration** | Across ~680M citations, the **top 15 domains take ~68% of AI citation share; Reddit alone ~40%**. ChatGPT's single largest source is Wikipedia (47.9%) and it cites brands **0.59%** of the time. But **recency is a strong lever**: pages updated within three months average ~6 citations against 3.6 for stale ones | A four-town local site will not win citation share. It *can* win on freshness, which it already has and never claims (items 162/163) |
| **Tripadvisor / Yelp** (on the head term) | Both now rank for "things to do in Mount Prospect IL this weekend" with **evergreen attraction lists**, not dated events | The head term serves **two intents** and this site answers only one (item 158) |
| **Evergreen vs. dated pages** | "Things to do" guides accumulate backlinks, search history and rank over years; **a new URL per event instance dilutes site authority**, and recurring events should keep one permanent URL updated in place | Confirms the guides are the compounding asset — and sets a rule before items 112/141 create year-stamped URLs (items 158/160) |
| **Domain warm-up** | **Sudden volume spikes are a leading cause of spam placement** — providers read them as a spam pattern, and a flagged domain can lose weeks of progress. The signals that build trust are **replies, opens, stars and spam-to-inbox moves** | The press pitch is designed to take this list from 1 to 300 in a day, on a domain whose entire sending history is one email (item 155) |
| **Local link building** (as a channel) | The strongest local link comes from a **.gov or .org tied to your own geography**; a Chamber of Commerce link outranks a random high-authority blog for local signals; **5–10 quality local links beat 50 directory listings** | The site already *sends* traffic to six local `.org` domains and has never asked for a link back (item 152) |
| **Nextdoor** (as a channel, not a price) | Verified **local** businesses get **two free Business Posts per month** to the neighbourhood feed. National/e-commerce excluded. Anti-spam rules bite on repeated similar content | Two posts a month fits the time budget exactly — if a free local site qualifies at all (item 154) |
| **Shaw Local "Friday Night Drive"** | A dedicated weekly high-school-football product for Chicago's "Suburban Life area" — week-by-week results and recaps for every game | Friday night football is a recurring weekly draw local publishers build whole verticals around, and this site has **zero** coverage of it (item 148) |
| **WBEZ / Sun-Times / WTTW / Patch** (farmers-market guides) | All four publish a **dated suburban farmers-market guide each spring** — by region and day of week, with 2026 season dates, hours and addresses | A head-to-head content category where this site currently **punts to the organiser's page** (item 141) |
| **Kidlist** (mykidlist.com) | "Activities for Kids in the **West and Northwest Suburbs**" — this exact territory. Weekly email, a weekend planner, "200 Things to Do with Kids This Weekend". **Submission-based with human review** (approvals on Wednesdays), a named editor, and a stated editorial rule: calendar carries **only free and/or drop-in** events, and no free events that exist to generate leads | The closest competitor found in thirty-one passes, and it is human-curated rather than generated (item 137) |
| **Prism News / NewsBreak** | Prism ran **200+ AI-generated "local news" sites**, suspended August 2026 after investigations found plagiarism, falsehoods and **fake AI-generated bylines**. NewsBreak: 40+ AI stories with real local inaccuracies | The category this site sits next to just had a public credibility failure. Anonymity now reads as a warning sign (items 130/131) |
| **Patch / PatchAM** | **PatchAM auto-generates a local newsletter for practically any US ZIP** — live in 14,000 towns, ~1M subscribers on that product, 3M overall, deliberately aimed at suburbs. Revenue is a **3–10% cut of sponsorships, memberships and community-calendar listings**. Sourced from "aggregation, automated event calendars, and posts from Nextdoor"; its CEO calls it a utility, not journalism. (Supersedes the original entry here, "hyperlocal news + community calendar" — that description predates PatchAM's auto-generation and was materially out of date, per item 124.) | The first competitor that is **already in 60056 without being asked**. The moat survives but is narrower than this file has claimed: hand-verified village/library/park-district feeds vs. generic aggregation + Nextdoor (item 124) |
| **Journal & Topics** | Runs its own **submission-based Event Calendar** ("Submit Your Event") listing park district, library and history centre events across a coverage area including **Mount Prospect and Palatine** | Item 77's top-priority press target **also runs the competing product** (item 125) |
| **Newsletter ad marketplaces** | Direct-sold B2C newsletter sponsorship conventionally needs **10,000–20,000 subscribers** and 100–200 clicks per ad; below that the advice is to sell through a third party | Those thresholds price a *list*. Half this business's tiers sell the *site* (item 118) |
| **Public ICS feeds** (as a *source*) | A feed can carry more than titles — descriptions, locations, organiser notes — and a public subscription link is unauthenticated, so whatever it exposes is readable by anyone with the URL | Item 100 would **republish** consumed feeds. Whitelist fields rather than pass through (item 115) |
| **Main Line Today** (revisited) | Already cited here for the Thursday send slot. It also **produces its own Restaurant Week** — "the largest, most ambitious dining event in the region" — sold with "direct email blasts to local diners via opt-in subscriber lists" | The mature form of this business is *running* the local event, not just listing it (item 112) |
| **Godly / SiteInspire** vs **Awwwards** | Godly is curated by a small team, 2–3 sites a week, favouring **craft over novelty — restrained, editorial, typographically considered**. Awwwards rewards experimental animation and immersive storytelling | Two different standards, and this site should be chasing exactly one of them (item 113) |
| **Local Facebook groups** | The discovery channel for a suburban family audience. Norm is the **70/30 rule**, many groups run a designated promo day, and **asking the admin first** is the difference between a standing welcome and a blacklist | Unlike Reddit's 90/10 (item 84, rejected on time cost), this is **one conversation, not sustained participation** — it fits the budget (item 107) |
| **Eventbrite → Bandsintown** | Eventbrite lists unlimited events free and **auto-syndicates music events to Bandsintown** | A dead end here, and worth recording as one — see item 109 |
| **Tinybeans / Red Tricycle** | Red Tricycle published local family activity guides across major US cities; **acquired for $6.5M in 2020**, folded into Tinybeans, which wanted it for brand-advertiser access to parents | Proof the category has an exit — and that the asset bought was the **audience**, not the listings |
| **Skylight / TeamSnap / SportsEngine** | The family-calendar surface. Skylight's $299 display ingests **any league or school calendar with a subscribe link**; youth sports has standardised on ICS subscription | Not a competitor — a **distribution channel this site does not use** (item 100) |
| **Nextdoor** (Neighborhood Sponsorship) | ZIP-exclusive "featured agent" placement sold to realtors, **$30–150/ZIP/month** | Not an events competitor — a **pricing anchor**. It is what a realtor already pays for the exact exclusivity item 95 sells |
| **Substack** (local publishers) | Newsletter platform with a built-in reader network; **40% of new subscriptions originate inside it**, Recommendations being the main engine below 10k subs | The one growth channel Buttondown structurally cannot offer (item 96) |
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

    🔴 **That "Unverified" flag was hiding a real, live bug — found by
    actually running the flow, not by re-reading the code.** This session
    has GitHub MCP tools this repo's own build/test loop doesn't: it can
    open a real issue and fire the real webhook. Did exactly that —
    opened a clearly-marked test issue (#189, closed after) through the
    same `event-submission` label the real Issue Form applies, matching
    the exact rendered body format `parse_issue_body()` expects (copied
    from `tests/test_parse_event_submission.py`'s own `SAMPLE_BODY`) —
    then watched the real workflow run rather than assuming success.

    It failed. `parse_event_submission.py` parsed the issue correctly and
    `insert_evergreen_entry()` correctly spliced a new entry into
    `config/regions/mount-prospect-60056.yaml` (confirmed in the job log:
    "1 file changed, 8 insertions") — every line of code this item
    described worked exactly as documented, right up to the last step.
    `peter-evans/create-pull-request@v8` then pushed the branch
    (`event-submission/189`, real, on the remote) and tried to open the
    PR itself, and GitHub's API rejected it:

    ```
    ##[error]GitHub Actions is not permitted to create or approve pull requests.
    ```

    That is a **repository setting**, not a bug in this repo's code —
    Settings → Actions → General → Workflow permissions → "Allow GitHub
    Actions to create and approve pull requests" is off. Every single
    real community submission this feature has ever received, if any,
    has silently failed the same way: parsed correctly, committed to a
    real branch, and then never surfaced as a reviewable PR, with no
    error visible anywhere for a human to notice short of digging into a
    failed Actions run. **Nothing reached `main`** — the failed run never
    merges its branch, so no bad data ever touched the live site; the
    only correction needed is the Settings toggle. The orphaned
    `event-submission/189` branch is harmless (unmerged, easy to delete
    via the GitHub UI whenever) and left in place rather than
    force-deleted, since this sandbox's git credentials aren't scoped for
    remote branch deletion.

    Added to the "Needs Ryan" table above. This is worth treating as
    **P1, not routine cleanup**: a feature that has looked "done" since
    PR #31 has never actually been able to deliver a single community
    submission, and nobody would find out without either a real
    submission failing silently or exactly this kind of deliberate live
    test.

    🟢 **Follow-up, same session: fixed and live-verified the silence
    itself, separately from the Settings gap it's paired with.** A
    parsed submission that fails to reach a PR left the issue with no
    comment at all — indistinguishable from one nobody ever looked at.
    Added a step to `event-submission.yml` that comments whenever a
    parsed submission (`exit_code == '0'`) doesn't make it to a PR, using
    `if: failure()` specifically — the one condition that keeps a step
    running after an earlier step in the same job has failed; every
    other `if:` in this file implicitly requires `success()` too and
    would just get skipped, the same implicit behavior that let this
    silence go unnoticed.

    Merged first (workflow behavior for `issues` events always runs from
    the default branch, so this couldn't be tested pre-merge), then
    live-verified with a second real test issue (#193, closed after)
    while the underlying PR-creation permission gap was still present —
    a rare, time-limited chance to exercise the failure path for real
    before that setting gets fixed and this path stops firing for that
    particular reason. It worked: the real run
    (`35492825966`) failed at PR creation exactly as expected, and the
    new step posted a real comment from `github-actions[bot]` on the
    issue, confirmed by reading it back via the API rather than assuming
    the workflow's green checkmark meant the comment landed. This
    defense-in-depth step stays useful after the Settings toggle is
    flipped too — any *other* future reason `create-pull-request` might
    fail (a branch conflict, a rate limit) now gets the same visibility
    instead of the same silence.

    🟢 **The actual fix, confirmed live, 2026-09-20.** Ryan checked #189's
    email notification, read the diagnosis above, and flipped the
    Settings toggle within the hour. Rather than take that on faith, ran
    a third real test (#199, closed) immediately after: real run
    `35509989841` succeeded end-to-end, and the resulting PR (#200) had
    a clean, correctly-formed 7-line diff to
    `config/regions/palatine-60067.yaml` — nothing corrupted, exactly
    the shape `insert_evergreen_entry()`'s own tests already promised.
    Closed #200 without merging (test content) and #199 with the
    confirmation. The community event-submission feature this item
    shipped in PR #31 now works end-to-end for the first time. Also
    worth recording plainly, since it's the whole point of this
    exercise: Ryan got an alarming-sounding email about issue #193
    overnight from a test this session ran and had already closed with
    an explanation — a real instance of the cost this kind of live
    testing can impose on the person actually watching the inbox, worth
    weighing next time before opening a test issue that will notify him,
    not just treating the technique as free because it's free to this
    loop.

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

22. ✅ **CLOSED AS A GOAL (item 162, 2026-09-20) — Get cited by AI search
    (GEO), as a deliberate strategy.** Under 10% of AI-cited sources rank
    in Google's top 10 for the same query, so the Phase 9 SEO work does
    **not** buy this channel — and AI Overviews now trigger on roughly
    half of all queries.
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
    **Correction (twenty-second research pass, item 98) — the premise
    at the top of this item overstated its case.** "AI Overviews trigger
    on roughly half of all queries" is true in aggregate (~47%) but
    misleading here: **local-intent queries trigger them at ~7%, local
    event queries at ~15%** — a third of the implied opportunity, not
    half. Separately, and more importantly: Google has **explicitly
    stated no Google Search system reads or acts on `llms.txt`**, no
    major AI provider has committed to reading it as of Q1 2026, and AI
    crawlers largely are not fetching it at all. `llms.txt` should not
    have been counted as meaningful progress toward this item's goal —
    it cost nothing to build (`build_llms_txt()` derives it from data
    already computed for the sitemap, so it isn't being removed; dead
    code that costs nothing and can't drift is harmless) but it bought
    less citation than claimed. The `robots.txt` crawler allow-listing
    and the `FAQPage`/`Event`/`WebSite` schema work above are unaffected
    by this correction — allowing crawlers that do exist, and giving
    them real structured data to read, are both real; a convention file
    that nothing reads is the only piece that wasn't. What the same
    research says actually decides AI citation — content structure,
    claim clarity, and **entity authority** — is genuine remaining work,
    not yet done here, and is spun out as item 99 below rather than
    bundled into this correction.
    **Closed as a goal, thirty-seventh research pass, 2026-09-20.**
    Three recalibrations of the same item is enough, and the citation
    data itself now makes the honest verdict clear: the top 15 domains
    hold roughly two-thirds of all AI citations, Reddit alone takes
    about 40%, and ChatGPT's single largest source is Wikipedia at
    47.9%. A four-town local site was never going to win a meaningful
    share of that distribution, and "get cited by AI search" should
    stop being treated as a goal this business can move toward. Closing
    the goal is not undoing the work — `robots.txt`'s AI-crawler
    allow-list, `Event`/`FAQPage`/`WebSite` schema, and the entity-
    naming consistency above all stand on their own, ordinary-search
    or E-E-A-T grounds, independent of AI citation share. `llms.txt`
    stays generated and uncounted, per the correction above. The one
    finding worth carrying forward: pages updated within three months
    earn roughly 6 citations against 3.6 for stale ones, and this site
    rebuilds itself automatically several times a week — a real,
    structural, already-running advantage (see item 163), just never
    the whole strategy this item was named for.

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

24. ✅ **Actually send the newsletter.** Item 12 captures addresses; nothing
    mails them, so the list is currently an asset earning zero. Buttondown's
    API plus the existing weekly build is the whole product Macaroni KID
    and 6AM City monetize. Send Tuesday–Thursday (highest engagement), and
    judge it against 2026 benchmarks — 20–30% open is average, 40%+
    excellent. Those same numbers belong in `SPONSOR_KIT.md`, since an
    open rate is a stronger sponsor argument than a subscriber count.

    ✅ **DONE — closing a stale-looking gap, not building a new one.**
    This item never got its own closing note even though the send path
    it asked for has been live for a while: `scripts/send_newsletter.py`
    + `.github/workflows/send-newsletter.yml` (Wednesday-night cron,
    item 110), `config/newsletter.yaml`'s `send.mode` set to `"send"` by
    the owner on 2026-09-17, and — the real evidence, not an assumption
    — a genuine successful **live** send already confirmed against actual
    GitHub Actions logs: workflow run `35176614362`
    (2026-09-17 03:02 UTC), `=== LIVE: this will SEND to every
    subscriber ===`, `Sent. Buttondown id: em_5hgyjgfytf8hws9xxpw6b0fesk`
    (recorded in this file's "Needs Ryan" section under "Closed since
    the last check"). The open-rate-benchmark follow-up this item asked
    for landed too, in item 102 — see that item's own ✅ note. Left as an
    explicit closing note here, rather than just leaving the item to be
    inferred from later items, because a numbered item with no closing
    marker reads as an open gap to the next research pass, which is
    exactly the false-negative version of item 120's "backlog looks
    less healthy than it is" problem — the twenty-eighth pass came
    close to re-flagging this before this cycle checked the actual
    workflow history.

25. **Newsletter cross-recommendations.** Newsletters in recommendation
    networks grow about 2.75× faster, and publishers who recommend others
    are 32× more likely to be recommended back. A small "other local
    newsletters we like" block plus reciprocal listings with nearby-suburb
    publishers costs nothing per week and compounds. Depends on item 24.

    ⚠️ **Template drafted, sending still needs Ryan — same shape as item
    77.** Item 24 unblocked this a few cycles ago; the missing piece was
    a real candidate, not code. A "we recommend other newsletters" block
    with no real newsletter to name would be exactly the kind of
    speculative, content-free scaffolding this file's working agreements
    warn against, so this went looking for one instead of building one:
    WebSearch (real, not guessed - same discipline as item 32's district
    calendar feeds) surfaced **Northwest Neighbor**
    (newsletter.northwestneighbor.com), a real, active, free weekly
    newsletter covering Chicago's northwest suburbs including Arlington
    Heights directly. Confirmed genuinely complementary rather than
    competing before naming it anywhere: different send day (Tuesday
    vs. Within Ten's Thursday) and a different angle (neighborhood
    lifestyle/openings vs. this site's structured event aggregation).
    Couldn't confirm who operates it from here, so
    `OUTREACH_TEMPLATES.md` §10's draft opens with a question rather
    than a name, and the ask (sending it, reading a reply, deciding
    whether to reciprocate) is a human action this loop shouldn't take
    on its own — added to the "Needs Ryan" table above. The on-site
    "other newsletters we like" block itself still has nothing to
    render until a real reciprocal relationship exists to name; building
    it empty now would be the same content-free-scaffolding problem one
    layer later, so it's deferred to whenever (if ever) that reply comes
    back yes.

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

31. ✅ **Send the weekend email Thursday afternoon.** A refinement of open
    item 24, not a replacement. Both Main Line Parent and Philadelphia
    Family send their weekend planner Thursday PM — two independent
    analogues converging on the same slot is a stronger signal than the
    generic Tue–Thu benchmark from the third pass. Ship item 24 with a
    Thursday-afternoon send.

    ✅ **DONE — decided the other way, deliberately, not silently
    overridden.** Item 110's `next_thursday_morning()` (the function name
    says it outright) computes Thursday **07:00** America/Chicago, and
    `config/newsletter.yaml`'s own comment records why: "the owner asked
    for Thursday mornings." That is an explicit standing instruction, not
    a default this item's afternoon research should quietly overwrite —
    a real preference from the person who actually reads the sponsor
    invoices beats two out-of-category analogues (a suburban Philadelphia
    parenting site, a different one) on a question this small. Recording
    the tension rather than either silently complying with the research
    or silently keeping the status quo: if the owner ever wants to
    revisit the send hour, this item's two analogues are the case for
    afternoon, sitting right next to `next_thursday_morning()`'s own
    comment explaining why morning won instead. Nothing to build - this
    is a documented decision, not an open question.

32. ✅ first slice confirmed working (Mount Prospect / District 57 only).
    **School district and youth-sports calendars as a data source.** Real
    gap, not a feature to copy: no local competitor aggregates them, and
    for a family suburb the school calendar — early dismissals, no-school
    days, concerts, games — is a large share of what a parent's week
    actually contains.
    This sandbox's own network is proxy-blocked for arbitrary domains
    (same as every other source), but `WebSearch` isn't - used it instead
    of guessing blind, and it surfaced a real, specific district-wide
    export URL from D57's own iCalInfo page:
    `webcal://www.d57.org/ical/Mount_Prospect_School_District_57_export.ics`.
    Added as a new `ics` source (`config/regions/mount-prospect-60056.yaml`,
    section "School Calendar"), shipped as an unconfirmed guess since
    WebSearch returns indexed/summarized content, not a verified fetch,
    and `WebFetch` is itself blocked for this domain in this sandbox.
    **Confirmed the very next real build** (run 33277287829, 21:55 UTC,
    read from its job log): `Fetching Mount Prospect School District 57 —
    Calendar (ics)` → `-> 6 item(s)` - 6 real dated events, first try, no
    correction needed.
    Township High School District 214 (the shared high school district)
    was researched too but has no discoverable public ICS feed, only PDF
    calendars - not added rather than shipping a guessed URL with no real
    evidence behind it at all. Same treatment needed for Arlington
    Heights, Des Plaines, and Palatine's own districts - not done this
    pass, deliberately scoped to one region to keep this verifiable.
    **Real follow-up (fourteenth research pass, 2026-08-30)**: extended to
    two more regions. Arlington Heights' District 25 got a real
    `webcal://www.sd25.org/site/handlers/icalfeed.ashx?MIID=569` source,
    found via web search of the district's own "ICal Feed" page - same
    "found, not guessed" discipline as D57's. Palatine got two: District
    15's `webcal://www.ccsd15.net/site/handlers/icalfeed.ashx?MIID=5415`
    (same `icalfeed.ashx?MIID=` pattern as D25, same CMS platform, but a
    separately-found, real MIID - not a copy-guess), and District 211's
    `https://adc.d211.org/site/RSS.aspx?DomainID=4&ModuleInstanceID=9762&PageID=1&PMIID=9953`
    - a genuine find for the shared high school district, unlike
    Mount Prospect's and Arlington Heights' D214 (PDF-only, no feed).
    Added as `type: rss` since it's a standard RSS export, not ICS -
    `build_digest.py` already supports both types (`rss` was already used
    for Mount Prospect's library). None of the four new sources has been
    confirmed by a live fetch yet (this sandbox's network is blocked for
    every source, same as always) - that confirmation will come from the
    next real GitHub Actions build's job log, same as D57's did.
    **That confirmation came back negative, not positive** (real build
    2026-09-15, run 34983302071): all three of D25's, CCSD15's, and
    D211's new sources 404. D57's own source, added a research pass
    earlier and confirmed working the very next build, is unaffected and
    still returns 6 real items - this is specific to the three new
    sources, not a platform-wide problem. Two follow-up WebSearch passes
    per broken URL both surfaced the exact same, still-dead URLs - the
    module instance IDs a real, indexed page pointed at have apparently
    rotated or expired server-side since being indexed, a failure mode
    WebSearch's own indexed-content nature can't detect ahead of a live
    fetch. This is the honest downside of the technique that made D57's,
    the Oktoberfest find, and the domain-bug fixes all work: it finds
    real pages, not necessarily currently-live ones. Left all three
    enabled (see each config's comment) since they fail soft regardless,
    and disabling them buys nothing a 404 doesn't already give for free.
    Not chasing a fresh MIID for either school district this pass -
    would need a real page fetch this sandbox can't do, and repeated
    WebSearch on the exact same query keeps returning the exact same
    stale answer.
    **Still not done**: Des Plaines' District 62 (elementary/middle) and
    Maine Township High School District 207 - both researched this pass,
    neither had a discoverable district-wide feed URL surface via web
    search (D62's school pages mention "Subscribe to Google Calendar" and
    RSS options per-school, not district-wide; Maine207's calendar pages
    mention a "Subscribe to Calendar" option with no URL indexed). Not
    guessing a URL with nothing behind it, same discipline as D214 - real,
    undropped follow-up if a future pass turns up a real URL.

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
    instrumentation.
    **Verified 2026-09-16, closing the gap this paragraph used to flag:**
    WebSearch (unlike a raw web fetch, this sandbox doesn't block it)
    reached GoatCounter's own official docs at
    `goatcounter.com/help/events`, which confirm `data-goatcounter-click`
    verbatim as the real, documented attribute name - "GoatCounter will
    automatically bind a click event on any element with the
    data-goatcounter-click attribute." The shipped markup
    (`data-goatcounter-click="sponsor-click-{region-id}"` in
    `region.html.j2`) matches the documented convention exactly. No code
    change needed - this was a documentation gap, not a bug. Still worth
    a real click-through smoke test the first time a genuine account
    exists, purely because nothing in this sandbox can fire an actual
    click against a live GoatCounter project - but the attribute name
    itself is no longer an open question.

#### P2 (new)

36. ✅ **DONE — Build the email template from scratch — do not reuse the
    site templates.** A gate on items 24 and 31, not a standalone feature.
    Whoever implements the newsletter must know: Outlook (2016–2021) renders
    through Microsoft Word's engine, so no flexbox, no grid, tables for
    layout; Fraunces and Inter will not load, so system fonts only (Arial,
    Georgia, Helvetica); single-column, mobile-first; Gmail clips anything
    over 102KB of HTML and hides the CTA behind a "message clipped" notice;
    and dark mode is three separate problems rather than one. `region.html.j2`
    violates essentially all of this. Reusing it would produce an email that
    looks correct in testing and broken in half of real inboxes.
    Built as `templates/email_digest.html.j2` (`role="presentation"`
    tables throughout, every color set via both a `bgcolor` attribute and
    an inline style so no property survives an email client stripping
    `<style>` blocks) plus `render_email_digest()` in
    `scripts/build_digest.py`, reusing the exact same `weekend_events`/
    `evergreen` data `build_weekly_summary_txt` already computes - never
    invents content. `main()` writes it to `docs/<region-id>/
    email-preview.html` every build, so it's ready to copy into
    Buttondown's dashboard the moment sending unblocks (item 47), and easy
    to spot-check meanwhile without waiting on that. Dark mode: rather
    than build and ship an unverifiable per-client dark theme, every cell
    forces an explicit light-mode color (plus `color-scheme`/
    `supported-color-schemes` meta tags) so Gmail/Outlook.com's
    auto-invert can't produce a broken combination - documented in the
    template itself as a deliberate simplification, not an oversight.
    Verified for real: a Playwright screenshot of a live per-region build
    (Mount Prospect, which actually has weekend events dated 2026-09-18/19
    right now) renders correctly at email width; every generated file is
    under 6KB, nowhere near Gmail's 102KB clip threshold; and 6 new tests
    check no `flexbox`/`grid` ever appears in the output, the sponsor
    block only shows for a real active sponsor, and the honest
    empty/evergreen-fallback states match `build_weekly_summary_txt`'s own
    logic. 224 tests pass; build exits 0.

37. ⚠️ **Overtaken by events — the decision got made without the
    deliberation this item asked for.** Decide the newsletter platform
    deliberately, before item 24 locks it in. Item 24 currently assumes
    Buttondown, which was chosen for being static-site-friendly, not
    after comparison. beehiiv deserves a look for one specific reason:
    its ad marketplace functions as a sales agent — brands are matched
    to newsletters and the publisher accepts in one click — which is the
    only mechanism found in five passes that could reduce sponsor
    *selling* time toward zero, and selling is the single un-automated
    step left in `BUSINESS_PLAN.md`. It also takes 0% of paid
    subscriptions against Substack's 10%. This was not a recommendation
    to switch; it was a recommendation not to default.
    **What actually happened:** Ryan set `buttondown_username` and item 74
    shipped the live capture form on 2026-09-16, ahead of that weekend's
    Oktoberfest/Fall Festival traffic (item 70) - the platform is now
    locked in by a real owner action, not a build-loop default. The
    beehiiv ad-marketplace angle is real and still worth knowing, but
    revisiting it now would mean migrating an account and a growing list
    for a hypothetical, not a live problem. Recording as overtaken rather
    than done: the deliberation this item wanted never happened, timing
    just made the question moot.

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

39. ✅ done (domain registered 2026-09-15, DNS live, `SITE_BASE_URL`
    migrated in `baf26ae` — see the seventeenth pass's housekeeping note).
    **The site is invisible, and the fix needs Ryan, not the build loop.**
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

46. ✅ done — resolved by the same domain registration as item 39.
    **The unregistered domain blocks the newsletter too — item 39 is now
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
    **Update 2026-09-15**: the domain itself is registered
    (`withintenmiles.com`, commit `baf26ae`) and every canonical/sitemap/
    `llms.txt` reference points at it - but DNS and the GitHub Pages
    custom-domain setting are still outstanding (see the "Needs Ryan"
    table), and SPF/DKIM/DMARC on top of that domain remain a separate,
    not-yet-started step once it's actually serving. This item's finding
    still holds; only the domain-registration half of it is done.

#### P2 (new)

47. ✅ **Deliverability checklist — a gate on items 24 and 31, not a
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
    **Buttondown's actual, real procedure (verified 2026-09-16 via
    `docs.buttondown.com/sending-from-a-custom-domain`, not guessed - item
    37/70 already settled on Buttondown by setting `buttondown_username`)
    — needs Ryan, added to the Needs Ryan block below:** in Buttondown's
    own Settings, add `withintenmiles.com` as the sending domain, then use
    the **"managed" DNS option** Buttondown itself recommends for a new
    domain: add just the two NS records Buttondown's settings page shows
    (delegating a subdomain to them), rather than the "manual" option of
    copying individual SPF/DKIM/DMARC TXT records by hand. Managed lets
    Buttondown rotate DKIM keys and switch sending infrastructure without
    Ryan ever touching DNS again; manual works too but is a one-time
    static snapshot that has to be revisited if Buttondown's sending
    infrastructure changes. The exact record values are generated
    per-account inside Buttondown's own dashboard once the domain is
    added there - genuinely unknowable from here, and not safe to guess.
    **Ryan added the domain and its managed-delegation NS records on
    2026-09-16, confirmed in place** - see the "Needs Ryan" block's
    "Nearly done, no longer blocking" note. What remains is checking
    Buttondown's own settings show it verified (a look, not a task), and
    the managed option itself avoided a real SPF collision this item
    warned about: because Buttondown's records live inside a delegated
    subdomain, the apex SPF record stays free for Cloudflare Email
    Routing later.

    ✅ **The remaining two checklist items turned out to already be
    handled, not still owed — checked rather than assumed from the
    item's own "a managed provider handles nearly all of this" framing.**
    WebSearched Buttondown's own documented behavior for each:

    - **`List-Unsubscribe`/`List-Unsubscribe-Post` headers (RFC 8058).**
      Multiple independent search results describe Buttondown as
      automatically including **"one-click unsubscribe headers"** on
      every send - language specific enough to imply the full RFC 8058
      pair, since "one-click" is exactly what distinguishes the `-Post`
      header from a bare `List-Unsubscribe`. One honest gap: no
      Buttondown-specific documentation naming the `-Post` header
      explicitly was found to close this with full certainty, so this
      is strong, multi-source evidence rather than a verified quote -
      worth a real send's raw headers confirming it outright if that
      ever becomes easy to check (e.g. once item 106's welcome email or
      a real weekly issue is inspectable).
    - **Spam-complaint-rate monitoring.** Buttondown has its own
      documented feature for exactly this,
      `docs.buttondown.com/complaint-rate` - it tracks Complaint
      Feedback Loop (CFBL) reports and surfaces the rate directly, no
      separate tooling to build.

    Both are the ESP doing what a managed provider is for, as this item
    predicted before finding the domain-authentication path - nothing
    left to build in this codebase for either. What's **not** resolved,
    and can't be by research: whether this specific list's actual
    complaint rate stays under 0.3%/0.1% is an ongoing operational fact,
    not a one-time task, and is inherently unmeasurable against a
    one-email send history (item 150) - Buttondown's own dashboard is
    where Ryan would watch that, not something this repo needs to
    surface separately. TLS in transit and valid forward/reverse DNS on
    the sending IPs were already covered by "a managed provider... handles
    nearly all of this" and Buttondown owning its own sending
    infrastructure - not independently re-verified here, consistent with
    that original framing.

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

#### Research pass 2026-08-29 (tenth pass)

Regions doubled this cycle — Des Plaines (PR #67) and Palatine (PR #70)
joined Mount Prospect and Arlington Heights, and the scale strategy from
item 50 was stated in PR #69. That changes the risk profile, and this pass
followed the risk rather than the feature list. Both items below are
**unblocked** — the newsletter cluster is still waiting on item 39.

| Angle | Finding | Consequence |
|---|---|---|
| **Silent scraper failure** | Scrapers "finish on schedule with clean logs while quietly delivering nothing of value". Selector degradation captures fields as blanks so error logging stays quiet. The fix is **trend comparison across runs**, not point-in-time validation — plus canary runs and row-count/null-rate checks | There are now 15 sources across 4 regions, every one fail-soft, and nothing would tell us if one died |
| **Multi-location IA** | Standard guidance is hub → all locations, each location → hub, **and cross-link nearby locations** | Region pages currently link only back to the hub, so the "trip across nearby towns" promise isn't actually navigable |

#### P1 (new)

51. ✅ done. **Nothing would tell us if a source silently died — and the
    data *is* the product.** `config/regions/*.yaml` now carries **15
    sources across four regions**, every one a fail-soft scrape of a small
    municipal site that can be redesigned without warning. Fail-soft is
    the right behaviour for uptime and exactly the wrong behaviour for
    detection: a source that starts returning zero events yields an empty
    section, a green build, clean logs, and no signal to anyone. The
    research names this precisely — jobs that finish on schedule while
    quietly delivering nothing, and selector degradation that writes
    blanks without raising errors.
    Shipped exactly as scoped: `fetch_region_sections()` now records each
    source's item count into a `region_id:source_name`-keyed history dict
    (`update_source_health()`), capped at the last 10 builds
    (`SOURCE_HEALTH_HISTORY_LEN`). `detect_source_regressions()` flags any
    source whose *current* count is 0 while its *trailing* median (every
    prior count, current excluded) is positive — deliberately leaves alone
    a source whose own median is already 0 (an unconfirmed guess, or one
    of the real 403-blocked sources this session's field note already
    documented), since that's a normal, already-known state, not a new
    death. `main()` persists the history to `data/source_health.json`
    (created fresh on its first real run - nothing to seed by hand) after
    every other file is written, then calls `sys.exit(1)` if any
    regression was found. `.github/workflows/build-digest.yml`'s commit
    step gained `if: always()` and now stages `data/source_health.json`
    alongside `docs/`, so a regression changes only the job's own
    conclusion (failure → GitHub emails the owner at no cost) — it never
    withholds the site update or the health history itself.
    Verified the full path, not just the unit tests: manually seeded a
    source's history with real prior counts, re-ran `build_digest.py`
    against this sandbox's always-zero fetches, and confirmed exit code 1
    plus the exact log line naming the regressed source - and confirmed
    `docs/` was still fully written despite the non-zero exit, so the
    "don't withhold good output" design actually holds and isn't just
    argued for.
    **The business case, not just the engineering one:** a region page with
    no events is worse than no page at all. It is a broken promise to a
    reader and an active embarrassment in front of a $5,000/yr
    Neighborhood Authority sponsor whose logo sits on it. This risk scales
    linearly with regions, and regions just doubled.

#### P2 (new)

52. ✅ done. **Cross-link nearby regions from each region page.**
    Multi-location best practice is hub → all locations, each location →
    hub, *and* cross-links between nearby locations. This site did the
    first two and not the third: a region page's only navigation was
    "← All regions", so a reader in Mount Prospect who wanted to see what
    is on in Arlington Heights had to return to the hub and guess which
    town is close.
    Shipped exactly as scoped: a "Nearby" strip on each region's main page
    — e.g. Mount Prospect's reads "Arlington Heights ≈2.7 mi · Des Plaines
    ≈3.6 mi · Palatine ≈5.8 mi" — computed **at build time**
    (`build_nearby_regions()`) from the village-centre lat/lon already
    sitting in each region config, reusing `_haversine_miles()` (already
    written for the hub map, item 17) rather than porting the hub's
    client-side JS version server-side. A static `all_regions_meta` list
    is built once before the per-region fetch loop in `main()`, since a
    region's own nearby-strip needs every *other* region's coordinates,
    including ones the loop hasn't reached yet. Real, crawlable `<a>`
    links (not client-side JS, unlike the hub's own "distance from me"),
    so this genuinely distributes internal link equity across region
    pages instead of pooling it all at the hub - the actual payoff once
    item 39 gives those links a real domain. Scoped to each region's main
    page only (not every filtered view/guide/directory page), matching
    where `answer_block` and `map_embed_url` already draw that same line.
    Returns `[]` (template omits the block) with fewer than 2 regions
    total or missing coordinates, same "don't draw something meaningless"
    discipline as `build_region_map`. Verified with a real Playwright
    screenshot (light + dark) showing all three other regions correctly
    sorted nearest-first with real, distinct mileages.

#### Research pass 2026-08-29 (eleventh pass)

Both tenth-pass items shipped within hours (PRs #74, #75) — and the health
check immediately earned its keep, catching real source problems in #76 and
#77. Unblocked work was thinning, so this pass did what ten passes of web
search never did: **built the site and looked at it**, at 1280px and 390px,
via Playwright against the real generated `docs/`.

That found two defects worth more than any trend article.

**Read the empty state carefully before reacting to it.** In this sandbox
every external fetch is proxy-blocked, so the local build renders zero
events everywhere. The zeros are an artefact. **The way the page *handles*
zero is not** — a genuinely quiet week, a holiday, or one dead scraper
produces exactly this rendering in production, so everything below stands.

#### P1 (new)

53. ✅ done, redesigned from the original ask. **The Google Maps embed
    fails loudly, above the fold, with no fallback.** On a region page the
    embed from PR #63 renders as a ~700×250px grey box with a broken-file
    icon, sitting between the intro paragraph and the Editor's Pick — the
    single largest element on the page, and it is a failure state.
    The original ask was: render the inline-SVG region map (item 17)
    underneath, reveal the Google embed only on successful `load`. Built
    that first, then tested it against the real generated site with
    Playwright before shipping - and it does not work. Confirmed directly:
    in this sandbox, where the request is proxy-blocked, the iframe's
    `load` event still fired, revealing the exact broken box the fallback
    was built to hide. The reason is structural, not a bug in this
    implementation: an iframe's `load` event fires once navigation
    *completes*, including to a blocked/error page, and cross-origin
    restrictions mean the parent document can't inspect what actually
    loaded to tell real content from a failure.
    Shipped instead: the reliable inline-SVG map (item 17's
    `build_region_map()`, now reused for a **single region's own page**,
    not just the hub) is the map now, full stop - fixed aspect ratio,
    always renders, no third party, nothing that can fail. A small "View
    on Google Maps ↗" pill link (`build_region_map_link_url()`, a plain
    `google.com/maps/search` URL, not an iframe embed) sits in the
    corner for real streets/zoom - it either opens a real map when
    clicked or it doesn't, with no false-positive "looks fine" state in
    between. Verified with Playwright at 1280px and 390px, light and
    dark: no more broken box, and the map reused across all four regions
    for the first time doubles as a second "nearby towns" visual (item
    52's cross-links are the text version of the same idea).

54. ✅ done. **Empty sections must collapse, not print six apologies.** A
    region page rendered every configured section unconditionally, so
    when sources returned nothing the reader got six consecutive
    headings — Village News, Village Events, Library Events, Park District
    Events, Things To Do, Downtown Events — each followed by the identical
    italic line "No live updates fetched this week." The tag filter bar
    sat above them filtering nothing, and the **"Sponsor this spot" card
    sat directly above the whole run**, the worst possible adjacency.
    Meanwhile "Around Mount Prospect", which *does* have content, was
    pushed to the bottom.
    Shipped on the main region page only (`nav_current == "all"` - every
    other view already passes its own `nav_current` and keeps its
    existing single heading + tailored empty message, which is correct
    there: a reader on `/this-weekend/` asking "what's on this weekend"
    should hear "nothing yet," not get evergreen content substituted in):
    a section with no events is omitted entirely rather than printed as a
    placeholder; when *no* section on the page has anything, the
    evergreen content (wrapped in a new `evergreen_section()` macro so it
    can render in either position without duplicating markup) leads,
    preceded by one quiet line ("It's a quiet week for live updates —
    here's what's always worth checking in {region}"). Verified with
    Playwright: no more apology pile-up, "Around {region}" now leads
    immediately after the tag filter bar exactly when it's the only real
    content on the page.
    **Found in passing, not fixed here (belongs with item 56):** at
    390px, the floating "My Weekend (0)" pill overlaps the sponsor card's
    text, obscuring it - the same class of positioning bug item 56
    already flagged at 1280px, just a different manifestation. Left for
    item 56's pass rather than scope-creeping this one.

#### P2 (new)

55. ✅ done. **The health check can't tell "couldn't reach it" from "reached
    it and parsed nothing."** Item 51's own next real production run
    proved this wasn't a hypothetical: run `33269892878`
    (2026-08-29T19:03:52Z, job `99146378591`) failed with
    `WARNING fetchers: HTML events fetch failed for
    https://www.palatinelibrary.org/events/upcoming: 403 Client Error:
    Forbidden` immediately followed by `ERROR build_digest: Source health
    regression: palatine-60067:Palatine Public Library District — Events
    just returned 0 items despite a positive trailing history` — a
    transient 403, not a dead scraper (real history around it was
    `[0, 6, 6, 6, 0]`).
    Fix: `fetch_rss`, `fetch_ics` and `fetch_html_events` in
    `fetchers.py` now return `None` (not `[]`) on a caught
    transport/parse exception, distinct from a real `[]` (page reached,
    nothing matched). `fetch_weather` is untouched — it was never part of
    source-health tracking. `fetch_region_sections()` in `build_digest.py`
    treats `None` as `transport_failed`: it's still rendered as an empty
    section like any other, but it's skipped from
    `update_source_health()` entirely rather than recorded as a `0`, so a
    transient block can no longer manufacture a false regression. This
    also fixes the loop's own local verification pain: in this sandbox
    every source is proxy-blocked, so `python scripts/build_digest.py`
    now correctly logs each as `(transport error - not counted for
    health)` and no longer reports nine false regressions on every run.
    One nuance confirmed by re-running the build locally after the fix
    and inspecting `data/source_health.json`: Palatine's history was
    still `[0, 6, 6, 6, 0]` and `build_digest.py` still exited 1 flagging
    it — correctly. The trailing `0` is the real entry from the pre-fix
    production run; the fix stops *new* transport failures from being
    recorded, but can't retroactively erase a bad data point that was
    already committed before the fix existed. That's expected, not a
    residual bug: it self-clears the next time Palatine's site responds
    and a real value (zero or non-zero) gets appended in its place. Until
    then the source will keep reading as regressed, which is arguably
    correct — the loop genuinely doesn't yet know whether that source has
    recovered.

#### P3 (new)

56. ✅ done. **Hub layout: an orphan card, a buried map, and help offered
    after the choice.** Four regions in a three-column grid left Palatine
    alone on its own row beside a large gap, recurring at 5, 7 and 8
    regions. Root cause: region cards shared one CSS grid with the
    "This weekend"/stat tiles. First attempt was `auto-fill` →
    `auto-fit` on that grid, on the assumption an unfilled trailing
    track would collapse - screenshotted it and the card was still
    stranded, because grid only collapses a column *track* with zero
    items anywhere in the whole grid, not one that's merely unused in
    one row (tracks 2 and 3 have content in the earlier rows, so they
    never collapse). Fixed by giving region cards their own flex-wrap
    container (`.region-grid`, separate from `.bento-grid`, which now
    only ever holds the weekend + stat tiles as a plain fixed 2-column
    layout): flexbox distributes `flex-grow` space per *line*
    independently, so a lone last-row card genuinely stretches to fill
    its row - confirmed with a screenshot, Palatine now spans full width
    instead of sitting next to a gap.
    The map moved above the region grid, alongside the "Show distance
    from me" bar (both exist to help *pick* a region, and used to render
    after the choice was already made). Its container grew from a
    ~240px thumbnail to `min(480px, 100%)` - tried full `.wrap` width
    first, screenshotted it, and the pin labels (a fixed px size baked
    into `build_region_map()`'s small viewBox) scaled up right along
    with the container and started overlapping each other. 480px was
    the point that's a real, legible size increase without triggering
    that.
    "(Signup coming soon.)" no longer ships to production: the
    newsletter block only renders at all when `newsletter.configured`
    is true (hub and region pages both), instead of showing a permanent
    pending state on the exact pages used to pitch sponsors. Currently
    structurally blocked on domain registration either way (the
    newsletter cluster), so this just means the block is invisible
    until that's unblocked, not broken-looking in the meantime.
    The floating "My Weekend" pill's overlap with card content (found
    shipping item 54, at 390px over the "Sponsor this spot" card) turned
    out to be partly a red herring: Playwright's full-page screenshot
    mode freezes a `position: fixed` element at a single point in the
    composite image, which is *not* what a real scrolling user sees - a
    scroll-to-bottom check with a real (non-full-page) viewport
    screenshot showed the pill sitting harmlessly below the footer, not
    over any card. It's a real concern for the very end of the page,
    though, since the last card sits nearest the fixed pill's screen
    position once scrolled fully down - `.wrap`'s bottom padding grew
    (64px/48px → 96px/88px) on region and weekend-hub pages so there's
    always reserved clearance there, at every width, confirmed by
    re-checking the same scroll-to-bottom viewport screenshot after the
    change. The originally-reported "clips the right edge at 1280px"
    didn't reproduce in this pass (measured the pill's real bounding
    rect - fits with the intended 18px margin) and needs a fresh repro
    if it resurfaces.

#### Research pass 2026-08-30 (twelfth pass)

Every eleventh-pass item shipped (PRs #78, #79, #80) plus the school
calendars (#81, #82), and the fixes hold up under inspection: empty
sections now collapse to one graceful line, the map has a working
inline-SVG fallback with a "View on Google Maps" link, and
`build_digest.py` exits 0 in the sandbox again instead of crying wolf.

Unblocked work is nearly exhausted — only items 22 and 35 remain, both
partial — so this pass inspected the surface never yet examined: **the
`/sponsor` page, where the money actually happens**, plus a real 390px
mobile render. Two of the four findings are on the revenue path.

#### P1 (new)

57. ✅ **DONE — the block cleared 2026-09-16.** **The sponsor CTA sends a
    local dentist to GitHub.** Confirmed exactly
    as reported: the page's single call to action linked to a GitHub "New
    issue" form, so buying a placement meant a realtor or an ice-cream
    shop owner creating a GitHub account and filing an issue in a
    developer bug tracker — the only conversion point in the business,
    gated behind infrastructure the target customer would never sign up
    for.
    `build_sponsor_cta_url()` in `build_digest.py` now builds a `mailto:`
    with the same prefilled fields (business name, region, tier, why we
    should recommend you) whenever `config/sponsors.yaml`'s new
    `contact_email` is set, correctly percent-encoded for RFC 6068 (a
    first draft used `urlencode()`'s default `+`-for-space, which a mail
    client's subject/body shows as literal `+` characters, not spaces —
    caught before shipping, fixed with `quote_via=quote`). Deliberately
    **not** activated with a guessed or invented address: this is Ryan's
    own contact info, not something the build loop should choose, so
    `contact_email` ships unset and the CTA keeps falling back to the
    GitHub issue (worse, but never a dead link) until he sets it — same
    treatment as `newsletter.yaml`'s `buttondown_username`. One line in
    `config/sponsors.yaml` activates it.
    **Ryan set `contact_email` directly on `main` on 2026-09-16** (commit
    `d8fb8d7`) - the mailto: CTA is live now, real inbox and all. He
    flagged it himself as "for now": a personal Gmail on a public page
    gets scraped, and the config file's own comment now notes that
    swapping it for a forwarded `hello@withintenmiles.com` (Cloudflare
    Email Routing, free) later is a one-line change, no other code
    touches the value. A hosted form (Tally, Google Forms) is still the
    better second step whenever there's a moment to set one up, but
    isn't something this loop can create on its own either.

58. ✅ done, with an honesty caveat. **The money page states no audience
    numbers at all.** Confirmed: `/sponsor` asked $1,200–$5,000/year and
    never said how many people would see the placement.
    Added a stat line — regions covered, live updates indexed this week,
    "running since Aug 26, 2026" — computed from the same real counts the
    hub page already shows, reusing `total_events`/`region_summaries`
    already computed in `main()` rather than tracking anything new.
    **What this does not do**, and the original ask wanted: "monthly
    readers" and "sponsor-link clicks last month" aren't shown, because
    neither exists as real accumulated data anywhere in the pipeline yet
    — GoatCounter analytics (item 23) is a client-side tracking script
    with no build-time API integration reading numbers back, and sponsor
    click tracking (item 35) fires client-side events with nothing
    persisting them. Inventing plausible-looking numbers for either would
    be exactly the fabrication this project has consistently refused to
    do elsewhere (source health, weekly summaries, editor's picks). A
    real version of those two needs either a GoatCounter API call at
    build time or a click-log file accumulated the way
    `source_health.json` already is — left as real, separate future work,
    not done here.

#### P2 (new)

59. ✅ done. **Sponsor tiers: an orphan card and a price order that went
    nowhere.** Confirmed: four tiers in a CSS grid stranded "Event Promo"
    alone on row two, same defect class as the hub (PR #80), and the
    order ($1,200/yr → $5,000/yr → $50/wk → $20 one-time) climbed no
    ladder.
    Reordered low-to-high commitment (Event Promo → Weekly Spot → Annual
    Partner → Neighborhood Authority) and flagged Annual Partner
    `recommended` (a badge + accent border) — it's already called "the
    flagship option" in the copy above the grid, so this makes the
    recommendation visible, not just stated. `.tier-grid` switched from
    CSS grid to the same flex-wrap-with-`flex-grow` pattern PR #80 used
    for the hub's region cards, for the same reason: grid only collapses
    a column track with zero items in the *entire* grid, not one merely
    unused in one row, so it can't stretch a lone last-row card the way
    flexbox's per-line grow distribution does. `SPONSOR_KIT.md`'s pricing
    table (the human-facing sales doc `SPONSOR_TIERS` is meant to stay in
    sync with) reordered the same way.

60. ✅ done. **On mobile, the "My Weekend" pill sat on top of the sponsor
    card.** Confirmed: at 390px the floating "My Weekend (0)" chip
    overlapped the "Sponsor this spot" block's pricing sentence — the
    single monetized element on the page partly covered by a floating UI
    chip earning no value at 0 items.
    Took the roadmap's own suggested best option: the tray widget (in
    both `region.html.j2` and `weekend_hub.html.j2` — the same widget is
    duplicated in each) now stays `hidden` until `tray.length` is at
    least 1, instead of unconditionally showing "(0)" the moment JS runs.
    Star buttons on each card stay independently visible and clickable
    regardless, so saving the first item still works exactly as before —
    only the empty floating chip is gone.

**Worth recording as working:** PR #78's empty-state handling is a genuine
improvement — one quiet italic line and an immediate pivot to evergreen
content, instead of six identical apologies. The map fallback behaves
exactly as intended when the embed can't load.

#### Found in passing, 2026-08-30

61. ✅ done. **The orphan-card grid bug recurred on the guides index and a
    guide's own "What's inside" list.** Not from a new research pass -
    found while screenshotting the guides and directory pages after
    shipping #57-60, to check whether the fix pattern used there was
    needed anywhere else. It was: `.card-grid`, the CSS class shared by
    every event listing, the evergreen section, guides, and the
    directory (one class, defined once in `region.html.j2`, used at
    every `nav_current` view), was still plain CSS grid. Four guides in
    a three-column grid stranded "New to Town" alone on row two; four
    items in "Birthday Parties & Kids' Classes"'s own "What's inside"
    list stranded "Local party venues, entertainers & tutoring centers"
    the same way - both confirmed with real screenshots before and after.
    Same fix as the hub (PR #80) and sponsor tiers (PR #83): `.card-grid`
    switched from CSS grid to flex-wrap with `.card { flex: 1 1 260px; }`
    - grid only collapses a column track with zero items in the *entire*
    grid, not one merely unused in one row, so it can't stretch a lone
    last-row card; flexbox's per-line grow distribution can. The
    directory page has no listings yet so the bug wasn't visible there,
    but shares the same `.card-grid` markup and gets the fix for free.
    `weekend_hub.html.j2` has its own separate copy of the same CSS
    (each region's weekend section is its own grid) - fixed there too,
    on the same reasoning, before it had a chance to show up for real.

62. ✅ done. **A real automated accessibility audit (axe-core), not just a
    manual pass.** Item 31 (Phase 11 P3#10) was a manual accessibility
    pass; this session's unblocked work was otherwise exhausted, so
    this hour ran the real thing - `axe-core` via Playwright (installed
    from PyPI, which is reachable even though this sandbox's general
    network egress is blocked) against the hub, a region page, the
    sponsor page, and a guide. It found 5 real, fixable violation types,
    all now confirmed at **0 violations** across 8 page types
    (hub/region/sponsor/guide/weekend-hub/free/directory/guides-index)
    after the fix, verified with a second audit run, not assumed:
    - **`landmark-one-main`, `region`** (every page): no page had a
      `<main>` landmark, and the hero banner sat in no landmark at all.
      Added `<main>` around each page's primary content and changed the
      hero `<div>` to `<header>` (all 4 templates: `hub.html.j2`,
      `region.html.j2`, `sponsor.html.j2`, `weekend_hub.html.j2`).
    - **`nested-interactive`** (hub and region maps): the inline-SVG
      region map's `role="img"` told assistive tech "this is one static
      picture" while the SVG contains real `<a>` links to each region -
      a screen reader would announce one image and never expose the
      links inside it. Removed `role`/`aria-label` from the `<svg>`,
      added an explicit `aria-label` to each pin's own `<a>` instead
      (`hub.html.j2` and `region.html.j2`'s `region_map_svg()` macro).
    - **`color-contrast`** (hub's stat label, sponsor's new "Recommended"
      badge from item 59): `rgba(255,255,255,.9)` on `--accent-soft` was
      4.4:1, and white on `--accent-2` was 3.4:1 light / 2.4:1 dark -
      both below AA's 4.5:1 for text this small. Fixed the stat label to
      opaque white (4.99:1 light, 4.86:1 dark) and added a new
      `--accent-2-strong` token specifically for white-text-on-solid-fill
      use (`#96581f` light, `#8f5419` dark - both ≥6:1), distinct from
      `--accent-2-text` which exists for the opposite pairing (dark text
      on a light background) and doesn't work for this one.
    - **`heading-order`** (region and guide pages): the Editor's Pick
      and Sponsor cards' `<h3>` sat directly under the page's `<h1>`
      with no `<h2>` in between, unlike an event card's `<h3>` which is
      correctly nested inside a `<h2>`-titled section. Both are
      standalone top-level blocks, not sub-items of a section, so
      promoted to `<h2>` instead.
    Confirms item 31's manual pass caught the obvious things but missed
    real, mechanically-detectable issues a proper tool catches in
    seconds - worth treating as complementary, not either/or, going
    forward.

#### Research pass 2026-08-30 (thirteenth pass)

All twelfth-pass items shipped in PR #83, and the build loop has started
finding its own work (#84's orphan grids, #85's five real axe-core
violations) — a good sign. Item 57 was handled with unusually good
judgment: the `mailto:` infrastructure shipped but was **deliberately left
inactive rather than inventing Ryan's email address**. That is the right
call and should not be second-guessed.

This pass inspected the GEO artefacts and the flagship guide. The GEO work
is genuinely good — `llms.txt` is well-structured with regions, weekend
views, guides and sponsorship; `robots.txt` explicitly allows GPTBot,
ClaudeBot, PerplexityBot, OAI-SearchBot, Google-Extended and CCBot. No
notes there. The guide is a different story.

#### P1 (new)

63. ✅ done for all four regions: Mount Prospect, Arlington Heights, Des
    Plaines, and Palatine.
    **The guides contain no facts.** Confirmed, with one correction: the
    "no links at all" claim was only half right — 4 of the original 5
    cards already had a real `url` (verified in the generated HTML), just
    styled without an underline like every other card link on the site
    (`h3 a { text-decoration: none; }`), so they read as plain text at a
    glance. The deeper finding stood regardless: hedged, unlinked-feeling
    prose with no real specifics.
    "No specific district site has been confirmed" turned out to be
    solvable, not a hard limit — `WebSearch` isn't blocked here even
    though this sandbox's own network can't reach arbitrary domains
    (same technique that found item 32's real D57 calendar URL), and it
    surfaced real official pages for everything: District 57
    (`d57.org`) and Township High School District 214 (`d214.org`, the
    real district Prospect High School belongs to) as two separate
    cards with real links instead of one generic hedge; the Village's
    real "New Resident Information" page; the library's real
    "Get a Library Card" page with its actual proof-of-residency
    requirement and phone number; Public Works' real phone number.
    **It also caught a real factual error before it could ship**: the
    original card described "Village vehicle sticker requirements" as
    current, but the program was **permanently eliminated in the 2024
    budget** (confirmed via multiple independent local news sources —
    Daily Herald, Journal & Topics — reporting the November 2024 vote,
    a ~5% levy cut and ~$250/household savings). Older
    mountprospect.org news pages from 2018-2020 about the old $45
    fee/May 1 deadline are still findable, so a newcomer researching on
    their own could easily land on stale information; the guide now
    says the program was eliminated instead of citing a fee that no
    longer applies. This is exactly why a fee or deadline was never
    guessed here even under pressure to add "specifics" — the one time
    a supposedly-stable civic fact was checked, it had changed.
    Also fixed the smaller finding: the tray-star ("add to My Weekend")
    no longer renders on guide cards or the guides index (gated on
    `nav_current != "guides"` in `region.html.j2`'s shared card loop) -
    a guide item or a guide's own title was never something that
    belonged in a weekend-planning tray.
    **Real follow-up, done the next hour**: Arlington Heights got the
    same treatment. Same WebSearch-sourced technique, and it directly
    paid off twice more. First, confirmed a real regional pattern, not
    a Mount Prospect one-off: Arlington Heights **also** eliminated its
    vehicle sticker program *and dog licenses* in the 2024 budget,
    confirmed directly on the Village's own site
    (`vah.com/_T13_R289.php`) - worth checking before writing Des
    Plaines' and Palatine's guides too, since the same change may well
    apply there. Second, a research mistake was caught and fixed before
    shipping: a first draft named "Rolling Meadows and Arlington high
    schools" as District 214 schools serving Arlington Heights -
    Arlington High School actually closed in 1984, so that would have
    been wrong. The real currently-operating D214 school in Arlington
    Heights is John Hersey High School; corrected before the commit,
    same discipline as the vehicle-sticker catch, applied to my own
    draft this time rather than the source material.
    **Real follow-up, done a research pass later (fourteenth pass)**: Des
    Plaines got the same treatment, and it paid off a third time: Des
    Plaines eliminated its own vehicle sticker program too, back in July
    2020 (Journal & Topics, Patch) - earlier than Mount Prospect's and
    Arlington Heights' 2024 eliminations, extending the confirmed
    regional pattern to three of four regions built so far. It also
    surfaced a real, previously-invisible bug: `config/regions/des-plaines-60016.yaml`'s
    City News source and every guide/evergreen link pointed at
    `desplaines.org`, which doesn't resolve to the City at all (the
    build log's "Connection reset by peer" on that source, noted back in
    the ninth research pass, was never root-caused). The real City
    domain is `desplainesil.gov`, confirmed via WebSearch against the
    City's own "Access Your Government" and Media Services pages, with a
    real news list page at `desplainesil.gov/Residents/News`. Every
    `desplaines.org` reference in that config (the City News source, the
    evergreen City card, the trick-or-treat guide link, and the New to
    Town guide) was switched to the correct domain - not just a content
    rewrite this time, a real bug fix. The new-to-town guide itself also
    got real district names instead of a hedge: Community Consolidated
    School District 62 (elementary/middle, `d62.org`) feeding into Maine
    Township High School District 207's Maine West High School
    (`maine207.org`) for most of the city, with a note that pockets fall
    under East Maine SD 63 or Elk Grove's CCSD 59 instead - same
    "confirm by address" discipline as Arlington Heights' guide, since
    Des Plaines' district boundaries are genuinely more fragmented than
    the other two regions'.
    **Real follow-up, done the same research pass**: Palatine got the
    same treatment, closing out this item for all four regions. The
    vehicle-sticker pattern now holds 4 for 4: Palatine eliminated its
    own program in 2022 (Daily Herald), the earliest of the four
    (Des Plaines 2020, Palatine 2022, Mount Prospect and Arlington
    Heights both 2024). It also surfaced the same domain bug found in
    Des Plaines' config, independently: `config/regions/palatine-60067.yaml`'s
    Village News source and every guide/evergreen link pointed at
    `palatineil.gov`, a hostname that has never resolved (the original
    ninth-pass build log recorded a TLS `TLSV1_UNRECOGNIZED_NAME` error
    on it, never root-caused). The real Village domain is
    `palatine.il.us`, confirmed via WebSearch, with a real "News Flash"
    list at `palatine.il.us/CivicAlerts.aspx` and a real "New Residents"
    page at `palatine.il.us/667/New-Residents`. Every `palatineil.gov`
    reference in that config was switched to the correct domain. The
    guide's school-district cards also got real names/links: Community
    Consolidated School District 15 (elementary/middle, the
    third-largest in Illinois, spanning seven towns including Arlington
    Heights) feeding into Township High School District 211's William
    Fremd High School, with the same "confirm by address" note as the
    other three regions' guides, since D211's and D15's boundaries don't
    line up with village lines either.
    **Two real domain bugs found via this same research technique in one
    day (Des Plaines' `desplaines.org`, Palatine's `palatineil.gov`) is
    worth registering as a pattern**: every remaining region's civic
    source URLs are worth a WebSearch cross-check the next time that
    region comes up for any reason, not just its guide content - a wrong
    domain fails soft (skipped, logged) so it's invisible unless someone
    actually reads the build log's warnings, which is exactly how both of
    these sat unnoticed since each region was added.
    **Acted on that pattern the very next hour**: WebSearch-verified
    Mount Prospect's (`mountprospect.org`) and Arlington Heights'
    (`vah.com`) own Village domains against their real sites - both
    checked out clean, no bug to fix. Worth recording as a real negative
    result, not a gap: those two regions' persistent 403s and TLS errors
    in past build logs are genuine blocking/misconfiguration on the
    correct host, not the wrong-domain bug Des Plaines and Palatine had.

#### P2 (new)

64. ✅ done. **Consolidate what needs Ryan into one block at the top of
    Phase 11.** Added a "Needs Ryan" table right after Phase 11's intro
    paragraph: register a domain, set `contact_email` in
    `config/sponsors.yaml`, set `buttondown_username` in
    `config/newsletter.yaml` — each with a one-line reason and what it
    unblocks, including item 65's citation-migration-cost framing folded
    into the domain row rather than kept as a separate item.

65. ✅ done (folded into item 64's table, not a separate item). **Everything
    currently points at `github.io`, and the citations are accruing
    there.** The finding is real and worth keeping visible, but it's a
    reason the domain matters more each week, not a distinct task with
    its own fix — captured as the "why" column for the domain row in
    item 64's new table instead of its own roadmap line.

#### Research pass 2026-09-15 (fourteenth pass)

First pass after a two-week pause — both loops were stopped on 2026-08-30
and resumed today. Randhurst Village landed as a Mount Prospect source in
`ad7c846`, along with a per-source `default_tags` key so its
reliably-free community events actually reach the Free filter.

This pass found something time-critical rather than strategic.

#### P1 (new)

66. ✅ done. **The site will miss the biggest local event of the year, and
    it is three days away.** The Mount Prospect Downtown Merchants' **Fall
    Fest & Oktoberfest runs Friday–Saturday, 18–19 September 2026** at
    Emerson Street and Busse Avenue:
    - Fri 18th, 4–11pm: Oktoberfest, German food and drink, the band
      Paloma.
    - Sat 19th, **noon–1pm: a special-needs hour**, residents of all ages
      with special needs encouraged to come early and beat the crowds.
    - Sat 19th, 1–4pm: the Fall Festival — **a free family event** with
      crafts, hands-on activities and live entertainment.
    - Sat 19th, 4–11pm: Oktoberfest again.

    The site almost certainly shows none of it. `mpdowntown.com/events/`
    is configured but, per this region's own config header, returns **200
    with zero matching items** — reachable, nothing extracted. A dedicated
    `mpdowntown.com/oktoberfest-info/` page exists and is not configured
    at all.
    Immediate fix: add the Oktoberfest info page as a source, or find the
    real link structure on `/events/` and give it a `detail_link_pattern`
    the way the Village calendar got one. But the durable fix is item 67 —
    because this will happen again with the next marquee event, and
    "biggest weekend of the year, invisible on the weekend planner" is the
    failure mode that would most damage the thing being sold.
    Note the special-needs hour specifically: that is exactly the kind of
    concrete, human detail a generic aggregator never carries, and it is
    the difference between a listing and a recommendation.
    **Shipped same-day** (this loop was paused two weeks; this was the
    first item picked up on resume, 2026-09-15, three days before the
    event). Rather than patching the scraper - a 200-with-nothing source
    could just as easily happen again for the next marquee event - went
    straight to item 67's durable fix and seeded it (item 68) with these
    two confirmed dates. See those items below for what shipped.
    **Real follow-up, the scraper itself fixed too**: checking the actual
    production build log (same technique used for item 32's correction)
    showed `mpdowntown.com/events/` is still returning 200 with 0 items
    every single build, unrelated to Oktoberfest now being covered by
    `annual_events:`. Root-caused it via WebSearch rather than leaving it
    as a mystery: the page has real, current content - "Progressive
    Dinner," "56 Music Fix," "Progressive Pub" - none of which contain
    any of the configured keywords ("event," "festival," "concert,"
    "market," "sale," "sidewalk," "oktoberfest"), so the keyword fallback
    was matching nothing despite a working page. Also found the real
    per-event URL shape - `mpdowntown.com/events/progressive-dinner-fine-
    dining/`, a slug under `/events/`, not the default `/event/\d+`
    numeric pattern every other source here assumes - and added it as a
    real `detail_link_pattern`, which takes priority over keywords once
    it matches anything. Broadened `keywords` too, as a fallback for
    whatever event names the pattern doesn't cover. Not yet confirmed by
    a live fetch (same sandbox limitation as always); that confirmation
    comes from the next real build's job log.
    **That confirmation came back negative** (real build 34997970218,
    the very next one): still exactly 0 items, no transport error - the
    fetch reached the page and found nothing, same as before the fix.
    That rules out "wrong keywords" as the actual cause, since the new
    pattern and broader keywords didn't move the needle at all. Most
    likely explanation, consistent with `fetch_html_events`' own
    documented limitation: the `/events/` archive page's link list is
    rendered by JavaScript, which a raw-HTML fetch can never see,
    regardless of what pattern or keywords are configured - different
    from the individual event permalink page WebSearch found indexed
    (`.../progressive-dinner-fine-dining/`), which is presumably a normal
    static post; it's the *archive/listing* view specifically that
    appears to be JS-built. Not chasing a third pattern guess - same
    "don't guess with nothing behind it" discipline as District 214's
    PDF-only calendars - documented in the config as a real, undropped
    follow-up if a headless-browser fetch path is ever added to this
    pipeline. Worth remembering as a general lesson: a real detail link
    found via WebSearch confirms a page *exists*, not that a plain HTTP
    fetch of its parent listing page can *reach* it.

67. ✅ done. **Curated annual events, with dates — the missing third
    content type.** The site has two content types: *fetched* events
    (dated, scraped, best-effort) and *evergreen* entries (curated, but
    undated — venues and resources, not happenings). Nothing covered the
    category that matters most: **known, dated, recurring annual
    events**. That gap is why a scraper returning 200-with-nothing could
    silently erase Oktoberfest. Fail-soft fetching is right, and item
    51's health check now catches a source that *dies* — but neither
    helps when a source was never yielding the marquee event to begin
    with.
    Shipped as proposed: a new `annual_events:` list in `config/regions/
    *.yaml`, and `build_digest.py`'s `prepare_annual_events()` turns each
    entry into the *exact same event-dict shape* a fetched item gets
    (tags via `infer_tags`, `date_iso` via `parse_event_date_iso`,
    calendar links via the existing `build_ics_data_uri`/
    `build_google_calendar_url`) - so it's just another block, and every
    downstream consumer (weekend/today/free views, JSON-LD, sitemap,
    Editor's Pick) handles it with zero special-casing. Inserted first in
    the block list, ahead of fetched sources, since it's the
    highest-confidence content on the page.
    One deliberate simplification from the original proposal: a
    multi-day event (Oktoberfest spans two days with different
    programming each day) is modeled as **one `annual_events:` entry per
    day**, not a `date`/`date_end` range. Friday and Saturday genuinely
    have different content (Friday is just Oktoberfest; Saturday adds
    the special-needs hour and the free Fall Festival), so this reads
    better on the page too, and it needed zero changes to the existing
    single-date machinery — no new range-overlap logic in
    `filter_events_by_dates`, no risk introduced three days before the
    event it exists to protect.
    Confirmed working in the real build: Oktoberfest is now Mount
    Prospect's Editor's Pick (soonest dated item, tag-broken ties, and
    it wins outright), shows on the region page's new "Annual Events"
    section (first, above the fetched sections), on `/this-weekend/`
    (both the region and hub-level "This weekend near you" pages, since
    today's build genuinely falls on the Tue before that Fri–Sun), on
    `/free/` for Saturday's tagged entry, and in the region's
    `event_json_ld`. 205 tests pass (3 new).

#### P2 (new)

68. ✅ done, shipped in the same pass as item 67. **Seed the annual list
    with what research has already confirmed.** Seeded exactly the two
    entries with real, confirmed dates: Mount Prospect's Fall Fest &
    Oktoberfest, one `annual_events:` entry per day (Fri 18th Oktoberfest
    only; Sat 19th special-needs hour + free Fall Festival + Oktoberfest
    continuing), both linking to the real `mpdowntown.com/
    oktoberfest-info/` page found in item 66's research.
    **Deliberately not seeded**, per this item's own instruction not to
    invent unconfirmed dates: Randhurst Village Street Fest, Randhurst's
    Halloween Fall Festival, and the Lions Club Cruise Night at Randhurst
    — none has an established 2026 date, only prior-year sources. Real,
    undropped follow-up: worth a WebSearch pass close to each event's
    usual season, when a current-year date is more likely to be
    published, rather than now while guessing would be the only option.
    **Real follow-up, done the very next hour**: checked whether the
    other three regions had the same near-miss, and two of them did -
    with real urgency, since both events land on the *exact same
    weekend* as Mount Prospect's Oktoberfest (Sept 18-20, 2026), and
    neither region's own configured sources mention either one:
    - **Des Plaines Fall Fest** (Lake Park, 2200 Lee St) - the city's own
      annual festival, confirmed via `desplainesfallfest.org`'s own
      listing: Fri 6-11pm, Sat noon-11pm, Sun noon-7pm. Carnival rides,
      rock wall, petting zoo, food, and 10 live bands. Free admission.
    - **Rotary Club of Palatine's Oktoberfest** (N Smith St & W Slade St,
      Downtown Palatine) - confirmed via `palatinerotary.org`'s own
      Oktoberfest page: Fri 5pm-midnight, Sat (Family Day: games, crafts,
      kids' entertainment) noon-midnight, Sun noon-6pm. Free entry.
    Both seeded as three `annual_events:` entries each (one per day, same
    reasoning as Mount Prospect's two - each day's hours and programming
    genuinely differ, Saturday most of all).
    A third region's event is real but not this urgent: **Arlington
    Heights' Harmony Fest & Taste of Arlington Heights**, Downtown
    Arlington Heights' biggest fall festival, confirmed via
    `downtownarlingtonheights.us`'s own event page for Fri-Sat, Oct 2-3,
    2026 (Fri 5-11pm, Sat 3-11pm - free concerts in Harmony Park, food &
    drink from local restaurants, a kids' zone Saturday). Seeded as two
    entries even though it's over two weeks out, same discipline as
    seeding any confirmed date rather than waiting - there's no reason to
    let a known, real date sit unseeded until it becomes urgent too.
    Confirmed in the real build: all three regions' events now show as
    that region's own Editor's Pick (soonest dated item wins), Des
    Plaines' and Palatine's both correctly appear on `/this-weekend/`
    (region and hub-level) while Arlington Heights' correctly does not
    (Oct 2-3 isn't this weekend) - the date-window filtering behaved
    exactly as designed with zero code changes. 205 tests still pass; hub
    weekend page went from 1 region section to 3.
    **Real follow-up attempt, still not seeded**: re-checked Randhurst's
    Street Fest and Halloween Fall Festival now that both are closer in
    season, since a current-year date is more likely published now than
    two weeks ago. Street Fest surfaced a specific claim - "Saturday,
    June 22nd, noon-5pm," sourced from what looks like the venue's own
    page (`randhurstvillage.com/events/5th-annual-street-fest-`) - but it
    fails a basic sanity check: **June 22, 2026 is a Monday, not a
    Saturday** (verified directly with Python's `datetime`, not assumed).
    That mismatch means either the day-of-week or the date itself is
    wrong somewhere between the venue's page and what WebSearch surfaced
    - and `WebFetch` is blocked for this domain in this sandbox, so there
    is no way to resolve which one from here. Per this item's own
    standing rule, an inconsistent date is treated the same as an
    unconfirmed one: not seeded. Halloween Fall Festival still has no
    2026 date at all, only a 2017 one. Both remain real, undropped
    follow-up - worth trying again nearer each event, or from an
    environment where the venue's own page can actually be fetched and
    read directly rather than summarized secondhand.

#### P3 (new)

69. ✅ done. **The Porchlight rename (commit `953bd8a`) missed the .ics
    calendar's PRODID and the sponsor-outreach templates.** Checked the
    rename's own stated scope against the actual repo rather than
    assuming "renamed everywhere the site names itself" covered
    literally everything. It covered every page-facing string, but
    missed two real, live places: the RFC 5545 `PRODID` field emitted in
    every generated .ics file (both the server-side `build_ics_data_uri`
    and the client-side "export my tray" JS in `region.html.j2` and
    `weekend_hub.html.j2` - all three still said "Weekend Trip Planner"),
    and `OUTREACH_TEMPLATES.md`, which the rename commit's own message
    said covered "README and SPONSOR_KIT headings too" but didn't
    actually touch. That file is real content a human would send
    verbatim to a sponsor prospect - shipping it unrenamed would have had
    someone email "I run Weekend & Trip Planner" days after the live
    site started saying Porchlight.
    Fixed both, and fixed a second real staleness spotted in the same
    file while there: its own intro line still said "Mount Prospect
    (60056) or Arlington Heights (60005) businesses," two regions behind
    the site's actual four. Not a naming bug, but the same "the doc says
    something the product no longer does" shape, caught by reading the
    file rather than just grepping for the rename string. 211 tests
    still pass; build exits 0 with the new PRODID confirmed in generated
    output.

#### Research pass 2026-09-15 (fifteenth pass)

Items 66, 67 and 68 all shipped within hours of the fourteenth pass, and
the result is verified working: `annual_events` exists, and **Oktoberfest
now appears on both the Mount Prospect weekend view and the cross-region
one**, with calendar export and tray star, three days before the event.
PR #94 also caught two rename spots this loop had missed — the `.ics`
`PRODID` and the sponsor outreach templates.

Two findings below are new information the owner did not have when
deciding; the third is a defect visible on the highest-profile listing of
the year.

#### P1 (new)

69. **"PORCHLIGHT" is a registered trademark, held by a company that
    publishes a newsletter.** When the name was chosen, the flagged risk
    was Porchlight Music Theatre — a Chicago company, but a theatre, in a
    different line of work. The search turns up materially more than
    that:
    - **Porchlight Book Company** holds a registered PORCHLIGHT mark
      (reg. 6028585, serial 88614588) and **publishes a 20-page quarterly
      newsletter to roughly 60,000 readers**. That is publishing to a
      subscriber list — adjacent to what this site plans to do, not a
      different industry.
    - **The Porch Media Group, LLC** filed "THE PORCH CHICAGO — ONE PORCH
      AT A TIME" for entertainment media services.
    - Porch Light Public Relations and a 2025 PORCHLIGHT filing by
      Porchlight Rental Service also exist.

    **Stated plainly and with its limits:** this is search-result
    evidence, not legal advice, and trademark protection is scoped by
    registration class — a bulk bookseller's mark does not automatically
    bar a free local events site. But "registered mark + newsletter
    publisher" is a different risk profile from "a theatre shares the
    word," and the owner decided on the latter.
    What this changes, concretely: the domain should differentiate rather
    than compete (`porchlightweekends.com`, `porchlight.town`, or a
    two-word lockup like "Porchlight Local"), and a real trademark search
    is worth its small cost **before** money goes into a domain, signage,
    print or sponsor contracts — not after. Nothing needs changing on the
    site today; the name works as it stands.

70. ✅ **DONE — The single biggest traffic weekend of the year is in three
    days, and the email capture is inert.** Oktoberfest and the Fall
    Festival will have locals searching for exactly what this site now
    lists, and item 12's signup block is config-gated on a Buttondown
    username that is still unset — so the one moment with real inbound
    attention converts nobody. The research on festival-driven audience
    capture is unanimous and unsurprising: a marquee event is when an
    owned audience gets built, and the list is what every sponsor
    conversation turns on.
    This is a one-line owner action (`config/newsletter.yaml`), and unlike
    the domain it does **not** depend on anything else — a free Buttondown
    account takes minutes, and collecting addresses now works even though
    *sending* still waits on the domain for SPF/DKIM/DMARC (items 46, 47).
    Collect now, send later.
    **Resolved with time to spare:** `buttondown_username` was set
    2026-09-16 (item 74) and the live form shipped the same day — two days
    ahead of the Sept 18-19 Oktoberfest/Fall Festival weekend this item
    was worried about missing entirely. The urgency that justified this
    item's own existence is gone; nothing further to do here.

#### P2 (new)

71. ✅ done. **The marquee listing's title reads badly.** The two
    `annual_events` entries in `config/regions/mount-prospect-60056.yaml`
    were titled "Oktoberfest — Fall Fest & Oktoberfest weekend" and "Fall
    Festival & Oktoberfest — **Fall Fest & Oktoberfest weekend**" — the
    second said Oktoberfest three times. The suffix was authored into
    the `title` field, presumably to group the pair as one weekend.
    Shipped the second of the two proposed fixes (the better one, not
    the quick one): a new optional `series:` field on `annual_events:`
    entries, rendered as a small kicker line above the title - the exact
    same visual treatment as the Editor's Pick card's own label
    (`.editors-pick .label`), so it reads as one visual language rather
    than a one-off. `prepare_annual_events()` passes `series` straight
    through into the event dict (`None` when absent, so nothing renders
    for a standalone annual event); the card-grid loop in both
    `region.html.j2` and `weekend_hub.html.j2` got the same
    `{% if item.series %}` line and matching `.series` CSS.
    Titles simplified to just "Oktoberfest" and "Fall Festival &
    Oktoberfest," with `series: "Fall Fest & Oktoberfest Weekend"` on
    both - the detail line already carries the times, place and
    organiser, so nothing is lost. Confirmed in the real generated
    output on both the region page and the hub's cross-region weekend
    page. Deliberately left the Editor's Pick card itself alone: its
    title was already clean (no more repetition, since it renders the
    same de-duplicated `title` field), and stacking a second small-caps
    kicker next to its own "✏️ Editor's Pick" label risked clutter for a
    defect that was already fixed. 213 tests pass (2 new); build exits 0.

#### Research pass 2026-09-16 (sixteenth pass)

**The domain landed.** `withintenmiles.com` was registered 2026-09-15 and
its DNS is already live — verified from here: the apex resolves to all
four GitHub Pages addresses and `www` to the Pages IPv6 set. Items 39 and
46, open since the first day of the project, are closed, and with them the
hard prerequisite on the entire newsletter cluster.

*Not* verified, and worth someone loading the page: whether HTTPS actually
serves and the certificate issued. This sandbox's proxy 403s every
outbound request, so the DNS check is real evidence and the serving check
simply could not be made.

That changes what matters. A brand-new domain has two properties worth
planning around: **search engines do not know it exists**, and **it has no
sending reputation at all**.

| Angle | Finding | Consequence |
|---|---|---|
| **New-domain indexing** | Google Search Console (DNS verification is the durable method) plus Bing Webmaster Tools, which imports straight from GSC and feeds Yahoo and DuckDuckGo. Beyond that, **IndexNow** — a keyfile plus an HTTP ping, no account — notifies Bing, Yandex and Seznam the moment content changes | Three moves cover the English-speaking web, and one of them is fully automatable |
| **New-domain sending reputation** | A fresh domain sending production volume on day one "appears to be a spam operation and is treated accordingly." Standard guidance is a 4–8 week ramp from very low volume, with SPF/DKIM/DMARC in place *before* the first send | Argues for starting the newsletter early and tiny, not for waiting |

#### P1 (new)

72. ✅ **DONE — IndexNow: tell search engines the moment the site rebuilds.**
    This site regenerates several times a week with genuinely new events,
    and the third pass established that content refreshed within 30 days
    earns roughly 3.2× more AI citations. That advantage only pays if
    crawlers *know* something changed. IndexNow is the cheapest possible
    way to tell them: a static key file at the site root and one HTTP POST
    listing changed URLs — no account, no API key negotiation, no quota to
    manage. Bing, Yandex and Seznam consume it, and Bing's index feeds
    DuckDuckGo, Yahoo and ChatGPT's search.
    Implemented as `submit_indexnow()` in `scripts/fetchers.py` (same
    fail-soft try/except shape as every other network call there — a
    failed ping is logged and swallowed, never breaks the build) and wired
    into `build_digest.py`'s `main()` right after the sitemap/robots/
    llms.txt/CNAME writes: it writes `docs/<key>.txt` (the site's own
    sitemap URL list, via a new shared `collect_sitemap_urls()` helper so
    the two never drift apart) and POSTs the same list to
    `https://api.indexnow.org/indexnow`. The key
    (`f3b7799bed06aac4295ec9134d53b014`) was generated once with
    `secrets.token_hex(16)`, not hand-typed, and is fixed rather than
    regenerated per build since IndexNow verifies it against the published
    key file. Confirmed in a real local build: the key file wrote with the
    right content and the POST fired with all 40 site URLs (fails soft in
    this sandbox with the usual proxy 403, same as every other outbound
    call here — the real production build is the one that matters).
    **Zero recurring owner time.**

73. ✅ **DONE (GSC half) — Verify the domain in Google Search Console and
    Bing Webmaster Tools.** A new domain is invisible until it is
    announced; no amount of on-page work substitutes. DNS verification
    is the durable method and Ryan now controls DNS, so this was
    unblocked for the first time. Steps: verify in GSC, submit
    `sitemap.xml` under Indexing → Sitemaps, then add the property in Bing
    Webmaster Tools by **importing from GSC**, which skips re-verification
    entirely.
    **Ryan verified GSC and submitted the sitemap on 2026-09-16** (see
    the "Needs Ryan" block below for the real root cause behind GSC's
    initially-misleading error - it was the property name, not DNS).
    The Bing-import half is quick but genuinely still open - tracked
    under "Also worth doing, not blocking" in the same block rather than
    duplicated here.

#### P2 (new)

74. ✅ **DONE (capture only) — Start the newsletter small and early — do
    not accumulate a list and then blast it.** The warm-up research is
    blunt: a fresh domain that starts at volume looks like a spam
    operation, and the usual remedy is a 4–8 week ramp.
    **State the nuance honestly rather than importing the advice wholesale:**
    most of that literature concerns *cold outreach*, and an opt-in local
    newsletter to people who typed their own address in is a materially
    lower-risk profile. The practical conclusion is the same, though, and
    conveniently so — the first sends should be small, and a new site's
    natural subscriber curve supplies that ramp for free.
    The real consequence is a reversal of instinct: **waiting until the
    list is "worth mailing" is actively worse than sending at twenty
    subscribers**, because it converts a free, natural warm-up into exactly
    the cold-start blast the guidance warns about.
    `buttondown_username` was set 2026-09-16, so item 24's config-gated
    embed now renders live on the hub and every region page instead of
    "coming soon" — confirmed against the real build, form posts to the
    current `buttondown.com/api/emails/embed-subscribe/` endpoint. This
    is capture only: *sending* (items 24/31/36/37) still needs SPF/DKIM/
    DMARC on withintenmiles.com first (item 47), so the list warms up for
    free while that's pending — exactly the sequencing this item argued
    for.

75. ✅ **DONE — The Open Graph image is unblocked for the first time.**
    Phase 7 deferred it explicitly — it "ties to Phase 9 once there's a
    real domain/brand to design one around," and as of two days ago both
    exist. This matters more than it looks: item 33 ships a
    copy-pasteable summary for posting into local Facebook groups, and a
    link post with no image renders as a grey box, the lowest
    click-through unit in any feed. The distribution feature already
    built was running at a handicap the whole time this was missing.
    Implemented with Pillow (added to `requirements.txt`), which turned
    out to install cleanly and render text correctly once bundled with
    real font files (`assets/fonts/DejaVuSans{,-Bold}.ttf`, copied from
    the permissively-licensed `fonts-dejavu-core` package — see
    `assets/fonts/LICENSE-DejaVu.txt` — rather than relying on whatever
    font happens to exist on the CI runner, which can't be verified from
    here and would be a silent single point of failure if wrong).
    `render_og_image()` in `scripts/build_digest.py` draws a 1200×630
    image from the site's own CSS palette (cream background, the same
    olive/terracotta accents, a wrapped title + subtitle); `main()` calls
    it once per region plus one default and writes them to `docs/og/`.
    Every template (`hub`, `region` — which covers every region
    sub-view: weekend/today/free/guides/directory — `weekend_hub`,
    `sponsor`) now sets `og:image`, `og:image:width/height`, and
    `twitter:image`, and `twitter:card` is upgraded from `summary` to
    `summary_large_image`. Verified in a real local build: all 5 images
    render at the correct size with legible wrapped text (checked visually
    for both a short region name and the longest one, Arlington Heights),
    and the generated HTML for the hub, a region page, `/sponsor`, and
    `/this-weekend` all carry the right `og:image` URL.

#### Research pass 2026-09-16 (seventeenth pass)

The build loop shipped both sixteenth-pass items inside an hour (IndexNow
in #101, build-time Open Graph images in #102) and the newsletter signup
went live in `1c7ee86`. Independent confirmation for #102 turned up in
this pass's research: a correct OG preview lifts click-through **2–3×**
against a missing or broken one. That feature is already earning.

With capture live and the domain resolving, the bottleneck is no longer
features or infrastructure. It is that **nobody knows the site exists**.
This pass went looking at distribution.

| Angle | Finding | Consequence |
|---|---|---|
| **First-100 subscriber tactics** | Local media mention: **100–500 subscribers in a day**. Local Facebook group post: **30–100 each**, but only after two to three weeks of genuine contribution first. A local business sharing to its own followers: **100–300 from one post**. Meta geo-targeted ads: **$0.25–0.50 per subscriber** | The highest-yield action available is one email, and it is not a feature |
| **Facebook link mechanics** | Facebook has down-weighted posts containing external links since 2017 and still did through 2026. The standard workaround is to post the body **without** the link and drop the link in your own first comment. Separately, replies are weighted roughly **27× likes** | Item 33's shipped tool is built against the algorithm, not with it |

#### P1 (new)

76. ✅ **DONE — The group-summary tool is throttled by design — verified
    against its own output.** `docs/<region>/weekly-summary.txt` used to
    read:

        What's happening in Mount Prospect this weekend (Sep 18–20):
        - Sep 18 — Oktoberfest
        - Sep 19 — Fall Festival & Oktoberfest
        See everything: https://withintenmiles.com/mount-prospect-60056/
        (Updated automatically, several times a week.)

    The URL sat **in the post body**, which is precisely what Facebook
    demotes, and it closed on a parenthetical when replies are the signal
    that earns reach.
    Fixed exactly as prescribed: `build_weekly_summary_txt()` now emits
    **two clearly-labelled blocks** - a `POST` block with no URL that
    ends on a real question ("Anything I've missed this weekend?"), and a
    separate `FIRST COMMENT` block containing the link. Pure string
    formatting, no new dependency, as this item called for. Confirmed
    against the real generated output for Mount Prospect (the same
    region this item quoted):

        POST (paste this as your post - no link, so Facebook doesn't downrank it):

        What's happening in Mount Prospect this weekend (Sep 18–20):

        - Sep 18 — Oktoberfest
        - Sep 19 — Fall Festival & Oktoberfest

        Anything I've missed this weekend?

        FIRST COMMENT (reply to your own post with this right after - the link goes here instead):

        See everything: https://withintenmiles.com/mount-prospect-60056/
        (Updated automatically, several times a week.)

    2 new tests confirm the URL never appears before the `FIRST COMMENT`
    label and the post body always ends on the question. 226 tests pass;
    build exits 0.

77. **Pitch the local press — the highest-yield action now available, and
    it needs Ryan.** A local-media mention is worth 100–500 subscribers in
    a day; nothing else in the research comes close for a single email's
    effort. Mount Prospect is covered by **Journal & Topics** and the
    **Daily Herald**, both already surfaced in earlier passes as covering
    this exact beat, and the Daily Herald ran the Oktoberfest listing this
    loop used as a source.
    The angle is true, which is what makes it pitchable: a local parent
    built a free, automatically-updating weekend guide for four northwest
    suburbs that pulls together the village, library, park district and
    school-district calendars nobody else aggregates. The site is live,
    the signup works, and Oktoberfest weekend just gave it a news hook.
    ⚠️ **Template drafted, sending still needs Ryan.** Added
    "§7. Local press pitch" to `OUTREACH_TEMPLATES.md`, following the
    same format as the sponsor templates, naming Journal & Topics and
    the Daily Herald specifically. Sending it - picking a real reporter,
    personalizing it, hitting send - is a human action this loop
    shouldn't take on its own. **Added to Needs Ryan.**

#### P2 (new)

78. **Meta geo-targeted ads — a bounded test, and the first thing here
    that costs money.** Local targeting reportedly buys subscribers at
    $0.25–0.50 each, so $50 is roughly 100–200 local addresses: enough to
    answer "does anyone in these four towns actually want this" far faster
    than organic will.
    **Flagged honestly against the plan rather than slipped in:**
    `BUSINESS_PLAN.md`'s break-even logic assumes zero spend, and every
    prior item has respected that. This is a deliberate exception and the
    owner's call, not the loop's. It is also only worth doing **after**
    items 24/31 actually send — paying for subscribers and then not
    emailing them is the one way to waste the money completely.

79. ✅ **DONE — A real RSS feed of the site's own upcoming events (build
    loop's own pick, not from a research pass — the backlog above is
    exhausted or Ryan-blocked, and this is a real, self-contained,
    zero-dependency feature within the plan's constraints).** Distinct
    from item 48 (correctly skipped): that was about *republishing* this
    site's listings onto Eventbrite/AllEvents/Bandsintown, which is wrong
    because those are aggregated events run by someone else. This is the
    opposite direction - the site syndicating its *own* aggregated page*
    as a feed, served from its own domain, the same way any content site
    does. Costs nothing ongoing and feeds the same freshness/GEO strategy
    item 22 already bets on: a feed reader, local-news aggregator, or AI
    crawler that polls `/feed.xml` learns about new events without
    re-scraping the whole site.
    Honesty note baked into the design: this pipeline has no "date first
    seen" for an event (every build re-fetches from scratch), so this
    isn't a conventional "recently published" RSS feed - it's an
    upcoming-events calendar feed, ordered soonest-first, with each
    item's `<pubDate>` set to the event's own date rather than an
    invented publish timestamp. Documented as such in the code rather
    than pretending it's something it isn't.
    Implemented as `build_feed_xml()` in `scripts/build_digest.py`,
    fed by a `feed_items` list collected during the existing per-region
    loop (only events with a real title, url and resolved `date_iso` -
    the same filter every other structured-data feature already uses),
    written to `docs/feed.xml`, capped at 50 items sitewide. Added
    `<link rel="alternate" type="application/rss+xml">` autodiscovery to
    the hub page's `<head>` and a mention in `llms.txt`. Verified against
    a real local build: valid RSS 2.0 XML, items sorted soonest-first,
    each carrying the real event's title/url/date. New tests cover XML
    validity, item ordering, the title/url/date_iso filter, and the
    50-item cap.

80. ✅ **DONE — Real bug found via item 79's own output: some event links
    point at this site's domain instead of the source's.** Reading the
    real generated `feed.xml` from the actual GitHub Actions build (not
    this sandbox, which can't fetch anything) turned up
    `<link>/scheduling/reservation/223808</link>` for a real Arlington
    Heights library event - a page-relative href, correct for a browser
    already on `ahml.info` (where the raw HTML has
    `href="/scheduling/reservation/218675"`), but wrong once copied
    verbatim into this site's own pages. A reader's browser resolves a
    relative href against *this* site's domain, silently sending them to
    `withintenmiles.com/scheduling/reservation/...` - a 404, not the real
    library page. Checked and confirmed this wasn't new: the same broken
    link was already live on the region page itself and inside the
    "add to calendar" `.ics` download's `URL:` field - item 79 didn't
    cause this, it just was the first thing to make it visible.
    Root cause: `_EventLinkExtractor` in `scripts/fetchers.py` stored
    each `<a href>` verbatim with no resolution against the page's own
    URL. Fixed with a new `_resolve_urls()` helper (`urllib.parse.urljoin`)
    applied as the *last* step in `fetch_html_events()`, after dedup,
    `detail_link_pattern` matching and `_nearby_date_hint()` all run
    against the original raw href - those need to match substrings in
    the source page's actual HTML, which never had the resolved form.
    Applied the same defensive `urljoin` to `fetch_rss`'s `<link>` and
    `fetch_ics`'s `URL:` field too - both specs say those should already
    be absolute, so it's a no-op there, but it closes the same bug class
    pre-emptively for free. 3 new regression tests confirm a relative
    AHML-style href resolves correctly, an already-absolute href is left
    unchanged, and RSS `<link>` resolves too. 233 tests pass; build
    exits 0.

#### Housekeeping

**Items 39 and 46 are stale and now marked done.** Both still read as open
and describe the site as living on a `github.io` path. That stopped being
true on 2026-09-15: `withintenmiles.com` is registered, DNS resolves to all
four GitHub Pages addresses, and `SITE_BASE_URL` was migrated in `baf26ae`.
Leaving the project's two longest-standing blockers reading as blockers
would mislead both loops and the owner about what is actually in the way.

#### Research pass 2026-09-16 (eighteenth pass)

Both seventeenth-pass items shipped in #107 — the Facebook link placement
fix and the press-pitch draft. The build loop also added a real RSS feed
(#108) on its own initiative and, reading that feed's actual output from a
live build, caught a genuine bug (#109): `_EventLinkExtractor` stored every
`<a href>` verbatim, so a library event linking to
`/scheduling/reservation/223808` resolved against **this** site instead of
the library's. Worth being precise about blame: that predates the domain
migration — those links were always wrong, the migration only changed
which wrong domain they pointed at.

The newsletter cluster is the last large block with nothing in front of
it, so this pass researched what actually goes in the thing.

| Angle | Finding | Consequence |
|---|---|---|
| **Local newsletter structure** | Recommended sections include a **local business spotlight with an owner mini-interview**. Newsletters on a predictable cadence referencing a routine moment average ~34% opens; subject lines under 20 words; clarity beats cleverness; send **Thursday evening or early Friday**, with most opens 3–7pm | The highest-value *content* section and the *monetisation* are the same thing |
| **Local subreddits** | The 90/10 norm, 9–19 non-promotional contributions between promotional posts, mandatory disclosure, and **61% of the subreddits studied ban self-promotion outright** | Costs the one resource the business plan says the owner doesn't have |

#### P1 (new)

82. ✅ **DONE (prep — sending itself still ships with items 24/31) — Make
    the newsletter's sponsor slot a mini-interview, not a banner.**
    The recommended section list for local newsletters includes a business
    spotlight built around a short owner interview — which means the
    highest-value content and the monetisation are the same block. That is
    the natural extension of item 18's "recommendation, not an ad"
    positioning into the email, and it is the strongest argument the
    Annual Partner tier has: a member gets **a genuine feature written
    about them**, not an impression counted for them.
    Concretely, and within the time budget: three or four fixed questions
    the owner emails once and the business answers in their own words —
    how long they've been in town, the thing regulars order, something
    most people don't know. **The answers are the content**, so the
    writing cost is near zero, and it produces something a business will
    actually share to their own followers, which the seventeenth pass
    valued at 100–300 subscribers per post.
    Built the whole pipeline ahead of the first real sponsor, same
    pattern as item 36: an optional `spotlight` dict (`years_in_town`,
    `regulars_pick`, `hidden_gem`) on a sponsor's `config/sponsors.yaml`
    history entry, documented there with the exact three questions;
    `OUTREACH_TEMPLATES.md`'s booking-confirmation template (§3) now asks
    for them directly, framed as optional and answered "in your own
    words"; `email_digest.html.j2` renders each answered field verbatim
    inside the existing "Local Recommendation" block, independently
    optional per field so a business that only answers one question
    still gets a clean render - never fabricated to fill an empty one.
    No sponsor exists yet (`history: []` in every region), so this is
    infrastructure, not a claim anything is live - verified with a
    mocked sponsor dict via a real local build and a Playwright
    screenshot showing all three answers rendering cleanly under a real
    weekend's events. 3 tests cover the all-present, all-absent and
    single-field-answered cases (a `/code-review` pass the following
    hour caught this entry originally over-claiming "4 new tests" when
    the PR had actually shipped 2 - corrected here, and the third,
    genuinely missing case added). 241 tests pass; build exits 0.

#### P2 (new)

83. ✅ **DONE (subject-line half only — send time is a scheduling decision,
    not code) — Fix the send time and subject-line format before the
    first send, not after.** This refines item 31 rather than replacing
    it: the fourth pass's "Thursday afternoon" came from two analogues;
    the broader data says **Thursday evening or early Friday**, with
    opens concentrated 3–7pm. Either is defensible — the point is that a
    predictable cadence tied to a routine moment is itself worth roughly
    34% opens, so pick one and never move it. **Send time is a real
    scheduling decision Ryan makes when item 24 ships, not something to
    hardcode now — left open.**
    Subject lines: under 20 words, clarity over cleverness, no all-caps or
    exclamation stacking. A format that satisfies all of it:
    *"This weekend in Mount Prospect: Oktoberfest, a free fall fest, and 6
    more."* Names the town, leads with the specific, states the count.
    Worth settling now because subject-line habits calcify the moment a
    list exists and open rates become a trend somebody is judging.
    **Implemented as `build_email_subject_line()` in
    `scripts/build_digest.py`**, using real event titles rather than
    inventing descriptive phrasing like "a free fall fest" not grounded
    in the actual data - a real title is never wrong the way a guessed
    paraphrase could be, and clarity-over-cleverness holds either way.
    Wired into `render_email_digest()` and shown two places in
    `email-preview.html`: the `<title>` tag (visible in a browser tab)
    and a clearly-labelled "PREVIEW ONLY, NOT PART OF THE EMAIL" note at
    the top of the body, matching `weekly-summary.txt`'s own POST/FIRST
    COMMENT label pattern - Buttondown sending is a manual step, so the
    owner needs to actually see the exact subject to paste in. Verified
    with a real local build and a Playwright screenshot; 6 new tests
    cover the 0/1/2/3+ event cases and the honest empty state. 238 tests
    pass; build exits 0.

#### P3 (new) — a re-rank, and a recommendation against

84. **Reddit is lower-yield here than it looks — don't build a strategy
    for it.** Local subreddits rank well in Google and the audience is
    exactly right, which makes this tempting. The rules are the problem:
    the 90/10 norm, 9–19 genuine contributions between promotional posts,
    disclosure required, and 61% of the subreddits in one study banning
    self-promotion outright. That is **recurring human attention on a
    schedule**, which is precisely what `BUSINESS_PLAN.md` says this
    business does not have — the same reason idea #5 (a hand-written
    newsletter) was rejected on day one.
    The bounded version that does fit, and the only one worth doing: when
    someone in a local sub asks what's on this weekend, answer it usefully
    and say the site is yours. No schedule, no commitment, no karma
    farming. Rank it **below** the press pitch (item 77) and the Facebook
    groups (item 33), both of which return more per minute spent.

85. ✅ **DONE — Item 80's own fix had the same bug it fixed, one layer
    down.** A `/code-review` pass over the whole of `scripts/fetchers.py`
    (the backlog above is exhausted or Ryan-blocked, so this hour went
    looking for real bugs instead) found that `_resolve_urls()` and the
    inline `urljoin()` calls in `fetch_rss`/`fetch_ics` all resolved a
    relative href against the **pre-fetch** `url` parameter, not
    `resp.url` (the URL actually served, after redirects). A source that
    301s - moves domains, adds a trailing slash, switches http→https -
    would have every relative link on it silently resolved against the
    *old* host, even though the fetch itself succeeded and nothing looked
    wrong. Same failure shape as item 80, one layer further down the same
    code.
    Fixed by resolving against `resp.url` everywhere, and by collapsing
    the three near-duplicate "resolve unless falsy" implementations
    (`fetch_rss`'s inline conditional, `fetch_ics`'s `if e["url"]:` guard,
    `fetch_html_events`'s `_resolve_urls`) into one shared `_resolve_url()`
    scalar helper, so a future fix to this logic only has to land once.
    Also moved `fetch_ics`'s resolution to *after* slicing to `limit`
    (matching `fetch_html_events`'s existing order) rather than resolving
    every upcoming event and discarding most of the work.
    Real coverage gap closed too: no test exercised `fetch_ics`'s
    relative-URL branch at all (its sample fixture's `URL:` field was
    already absolute) - added one, plus a redirect-specific regression
    test for each of the three fetchers, since the whole point of this
    fix is behavior that only shows up when the served URL differs from
    the requested one. 244 tests pass; build exits 0.

#### Correction

The previous pass was dated **2026-09-17** in its heading. It ran on
**2026-09-16** at 06:33 UTC. Corrected in place — this file is the
continuity record for two loops, and "what was known when" is most of
what makes it useful.

**This pass's own items 79/80/81 collided with numbers the build loop
had already used an hour earlier** (79: the RSS feed; 80: the relative-
URL bug fix) - the research loop numbers sequentially from what it last
read, not knowing what the build loop shipped in between. Renumbered in
place to 82/83/84 (the mini-interview idea, the subject-line item, and
the Reddit re-rank respectively) so nothing in this file points at two
different things under one number.

#### Research pass 2026-09-16 (nineteenth pass)

Not a competitor pass. Ryan asked how to preview the newsletter before
having subscribers, so this pass **read the thing the build actually
renders** — `docs/mount-prospect-60056/email-preview.html`, from a live
`build_digest.py` run, screenshotted at 390px — rather than reasoning
about the template. Three findings, all from that one artifact. This is
the cheapest review window the newsletter will ever get: every one of
these is a five-line change now and a visible change of habit once a
list exists whose open rates somebody is trending.

| Angle | Finding | Consequence |
|---|---|---|
| **Rendered subject line** | `This weekend in Mount Prospect: Oktoberfest and Fall Festival & Oktoberfest` — two real, distinct events that happen to share a word, so the line reads like a stutter | Item 83 settled the *format*; the format is right and the *inputs* aren't deduped |
| **Rendered event rows** | Title + date only. `event.detail` is fetched, truncated, and already on the region page — the email template just never emits it | The email is strictly less useful than the page it advertises |
| **Empty sponsor slot** | The block is correctly hidden (`sponsor.is_active_sponsor` is false, and item 18's rule is that house ads never wear recommendation framing) — but unlike the region page, the email then shows *nothing at all* | Correcting my own first read: not a missing block, a missing **house ad** |

#### P1 (new)

86. ✅ **DONE — Dedupe near-identical titles in the email subject line.** The live
    subject for Mount Prospect this week is `This weekend in Mount
    Prospect: Oktoberfest and Fall Festival & Oktoberfest`. Both events
    are real and distinct, so this is not a data bug and dropping one
    would be wrong — the subject line just shouldn't pick two titles that
    read as the same thing.

    `build_email_subject_line()` (`scripts/build_digest.py:1474`) takes
    `weekend_events` in order and uses `titles[0]` and `titles[1]`
    verbatim. The fix is a selection rule, not a filter: when choosing the
    second title to name, skip candidates whose significant tokens are a
    subset or near-subset of the first's (case-folded, stopwords and
    `&`/`and` dropped), and fall back to the next distinct event. If every
    remaining title collides, name one and let the count carry the rest —
    `This weekend in Mount Prospect: Oktoberfest, and 7 more` is honest
    and reads cleanly. The `and {more} more` branch already exists, so
    this is a change to which titles get chosen, not to the format item
    83 settled.

    Worth a test with the real colliding pair as the fixture: it is the
    case that actually shipped, and a synthetic `Event A`/`Event B` pair
    would pass a broken implementation.
    Implemented exactly as prescribed: `_is_near_duplicate_title()`
    tokenizes both titles (lowercased, `[a-z0-9]+`, stopwords/"and"
    dropped - "&" disappears on its own since it isn't a word character)
    and treats a subset relationship either direction as a collision;
    `build_email_subject_line()` walks past every colliding candidate to
    find a genuinely distinct second title, falling back to naming just
    the first plus a count when none exists. Tested with the real
    colliding pair from the live build (`Oktoberfest` /
    `Fall Festival & Oktoberfest`) as the fixture, plus the
    all-candidates-collide fallback case. Verified against a second real
    build a day later, when Mount Prospect's weekend genuinely only had
    those two colliding events left: it correctly produced `This weekend
    in Mount Prospect: Oktoberfest, and 1 more` rather than naming the
    same event twice.

87. ✅ **DONE — Give email events their detail line.** Each event row in
    `templates/email_digest.html.j2` emits `event.title` and
    `event.date` and stops. `event.detail` is already fetched, already
    truncated (`truncate(item.get("detail", ""))`), already rendered on
    the region page, and already passed into this template inside the same
    `weekend_events` dicts — the template simply never reads it.

    Add one conditional row per event, matching the existing `{% if
    event.date %}` row's markup (inline styles on every cell, no
    flex/grid, per the template's own Outlook constraints), at ~13px in
    the muted `#766a58` rather than the `#96581f` the date uses, so the
    date stays the row's accent. Keep it to one line — these are already
    truncated, but a two-line detail in a six-event digest is the
    difference between a scannable email and a wall.

    This is the single largest gap between the email and the page it
    exists to advertise: today a subscriber gets titles and dates, which
    is the *index*, and has to click through for the thing that tells them
    whether to care. An email that can be judged without clicking is what
    makes the click worth it.
    Added exactly the prescribed row - same markup shape as the `{% if
    event.date %}` row, ~13px muted `#766a58` so the `#96581f` date stays
    the row's one accent color, one line since `detail` is already
    truncated upstream. Verified against a real build: the live Mount
    Prospect digest now shows "German food, drink & live music from the
    band Paloma..." under Oktoberfest instead of just a title and date.

#### P2 (new)

88. ✅ **DONE — Show the house ad in the email when there is no sponsor.** My first
    read of the preview was that the sponsor block was missing. It isn't —
    it is deliberately gated on `sponsor.is_active_sponsor`, and that gate
    is correct: item 18's rule is that "LOCAL RECOMMENDATION" framing is
    for a business that actually paid, never for an empty slot, and
    `build_region_sponsor()` already encodes exactly that.

    The gap is what happens *instead*. On the region page an unsold slot
    falls back to the house ad (`default_house_ad`, "Sponsor this spot").
    In the email it falls back to nothing, so the one artifact most likely
    to be forwarded to a local business owner is the one that never
    mentions the slot is for sale.

    Add an `{% else %}` to the existing `{% if sponsor and
    sponsor.is_active_sponsor %}` that renders the house ad in plainly
    different clothes — no "LOCAL RECOMMENDATION" label, no spotlight
    block, muted rather than the `#fdf3e4` sponsor fill — so the two can
    never be confused at a glance. Link it to the sponsorship page. One
    small honest line beats an empty space in the email a prospect reads.

    P2 and not P1 because it earns nothing until the list has readers,
    where 86 and 87 shape a habit that gets harder to change every week
    sending continues.
    Implemented as prescribed: an `{% elif sponsor %}` branch renders the
    house ad's real `title`/`detail`/`url` (already `default_house_ad`'s
    "Sponsor this spot" / the real `/sponsor/` URL, no invented content)
    in a dashed, muted card with a plain "SPONSOR THIS SPOT" label,
    distinct from the sponsor block's `#fdf3e4` fill and "LOCAL
    RECOMMENDATION" framing so a reader could never mistake one for the
    other. Verified against a real build and a Playwright screenshot: 6
    new tests across items 86-88 (the near-duplicate skip, the
    all-collide fallback, the detail line present/absent, and the house
    ad shown/omitted). 250 tests pass; build exits 0.

#### Housekeeping

The preview path is worth stating plainly in the docs, because it is
better than it looks: every build already writes
`docs/<region-id>/email-preview.html`, which means the current newsletter
is publicly readable at its URL with no Buttondown account, no list, and
no send — and the file carries its own generated subject line at the top,
labelled `PREVIEW ONLY`, for pasting into Buttondown's subject field.
That is a complete review loop for a newsletter with zero subscribers,
and nothing in the repo says so outside the template's comments.

#### Research pass 2026-09-16 (twentieth pass)

Two facts arrived from the owner that change sequencing, not scope.

**Buttondown's free plan can send this template after all.** The paid
"naked mode" gates pasting raw HTML *as HTML*, but markdown mode accepts
inline HTML, which is what `email_digest.html.j2` already is. The
constraint I was about to write up as a fork — pay, switch ESP, or
maintain a plainer second renderer — does not exist. Nothing needs
rebuilding and the just-finished DNS delegation stays.

**A real Gmail render test is now on the record.** The template went out
as a proper multipart message (HTML + plaintext alternative, preview
annotation stripped) to the owner's own inbox. Worth stating what that
does and doesn't prove: it tests *rendering*, in the client most
subscribers use. It proves nothing about deliverability, because
Gmail-to-self always authenticates.

#### P1 (new)

89. ✅ **Prove one newsletter can send before the press pitch goes out, not
    after.** These two are being tracked independently and shouldn't be.
    Item 77's press pitch is the highest-yield action available and the
    file has said so for four passes — but a local-media mention is a
    **one-shot**. It converts once, produces 100–500 signups in a day
    (seventeenth pass), and cannot be re-run next month because the
    newsletter got good in the meantime.

    So the risk is sequencing, and it is asymmetric. Pitch first and the
    send path isn't ready: several hundred people opt in, receive nothing
    for a fortnight, and most are gone before the first issue — the
    single most expensive way to acquire a dead list. Send first and pitch
    a week later: the cost is a week.

    The gap is genuinely small, which is what makes this worth saying now
    rather than treating it as a phase. Three things, none of them
    building:

    - Confirm Buttondown shows `withintenmiles.com` verified (item 47 —
      the records are in place and confirmed; this is a look).
    - Send **one** real issue through Buttondown, in markdown mode, to a
      list of one. That is the only test that exercises the whole path
      at once: authentication, Buttondown's own rendering, the injected
      unsubscribe footer, and inbox placement. Everything before it has
      tested one layer.
    - Check it landed in the inbox and not Promotions or spam. A
      brand-new sending domain has no reputation, and the sixteenth
      pass's finding stands: send early and small rather than
      accumulating a list and blasting it.

    Then pitch. Items 86 and 87 (subject-line dedupe, detail lines) should
    land in the same week — they are small, and they decide what those
    100–500 people judge the product by on day one.

    ✅ **DONE — same day, by the owner, exactly as asked.** The very next
    research pass (twenty-first, 2026-09-16) recorded the result: the
    owner sent one real issue through Buttondown to a real Yahoo
    address that same afternoon, and it **landed in the primary inbox**
    with DMARC live at `p=quarantine` — stronger authentication than
    this item required, confirmed by direct resolver query, not
    assumed. That real send is exactly what surfaced the four findings
    the twenty-first pass logged (subject line, MX record → item 93,
    Yahoo dark mode, the `PREVIEW ONLY` leak) — the whole point of
    testing the real path before the one-shot press pitch instead of
    after. Never got its own closing marker even though the very next
    paragraph in this file already recorded it happening; adding one
    now for the same reason item 24's does.

#### Housekeeping

The trademark search (item 69) is a **spend** gate, not a launch gate. It
blocks signage, print and sponsor contracts; it does not block the press
pitch, the newsletter, or anything currently in flight. Worth keeping the
distinction explicit so it doesn't accrete blocking weight it never had.

#### Research pass 2026-09-16 (twenty-first pass)

Item 89 said to send one real issue before the press pitch, because the
first send tests layers nothing before it could. The owner sent it the
same afternoon — through Buttondown, to a Yahoo address — and it found
four things. This is the entire argument for item 89 in one data point:
every one of these would have hit 100–500 press-driven subscribers
instead.

**It landed in the Yahoo primary inbox**, which is the result that
mattered most, and DMARC is live at `p=quarantine` (verified here by
direct resolver query) — stronger than the `p=none` starting posture
item 47 allows. Authentication and placement are working.

| Finding | Severity | Root cause |
|---|---|---|
| Subject line advertises **"Half-Day Student Attendance (Grades 1-8)"** | **High** | Item 86's own fix, working as written |
| Replies to `hello@withintenmiles.com` vanish | High | No MX record on the apex |
| Yahoo dark mode inverts the whole email into brown | Medium | The template's stated defense does not work |
| The `PREVIEW ONLY` row was sent as email body copy | Medium | The annotation ships inside the pasteable file |

#### P1 (new)

90. ✅ **Events need an `attendable` / `informational` distinction, and only
    attendable ones may headline.** The live subject line right now is
    `This weekend in Mount Prospect: Oktoberfest, Half-Day Student
    Attendance (Grades 1-8), and 1 more`. A school half-day is being
    advertised as a reason to leave the house, in the most visible line
    of text the product has.

    This is item 86's fix working exactly as specified and producing a
    worse result than the bug it replaced. Before, the near-duplicate
    Oktoberfest pair occupied both slots and crowded the school item out;
    the dedupe freed a slot and the next thing in the list took it. Worth
    being precise, because it argues against the obvious patch: the D57
    feed is **not** a mistake to filter away. `config/regions/
    mount-prospect-60056.yaml` says no-school days are a deliberate
    inclusion and "a real gap no local competitor" covers, and that is
    correct — a parent planning a Friday genuinely wants to know school
    lets out at noon.

    So the fix is a **classification, not a filter**. A half-day belongs
    on the page as context; it must never be a headline, a subject-line
    pick, or a `My Weekend` star. Add an `attendable` boolean (inferred
    in `scripts/tagging.py` from title patterns — no school, half day,
    early dismissal, institute day, holiday — closing, no refuse
    collection, and settable per-source in region YAML for feeds like
    D57 that are mostly informational), then:

    - `build_email_subject_line()` picks only from attendable events.
    - The email body groups informational items under a short "Also this
      week" line rather than interleaving them as equals.
    - The region page keeps showing them, visually secondary.

    Fall back gracefully: if a weekend has no attendable events at all,
    the existing "what's coming up" subject is already the right answer.

    ✅ **DONE.** `scripts/tagging.py` gained `INFORMATIONAL_KEYWORDS` +
    `is_informational()` (deliberately specific phrases like "half day",
    "no refuse collection" — not bare "holiday" or "closing", which would
    misclassify a real "Holiday Craft Fair" or an exhibit's "closing
    weekend"). `fetch_region_sections()` now attaches an `attendable`
    boolean to every event: `False` when the title/detail matches, or
    unconditionally when a source sets `informational: true` (the
    override exists but was deliberately *not* applied to D57 — that
    feed's own config comment says it also carries real concerts, which
    are attendable, so a blanket source-level override would have
    misclassified those). `build_email_subject_line()` now filters to
    attendable titles before picking, so the real regression case
    (Oktoberfest + its near-duplicate + the half-day) resolves to `This
    weekend in Mount Prospect: Oktoberfest, and 1 more` — verified via
    `test_build_email_subject_line_never_names_an_informational_event`,
    which asserts `"Half-Day" not in subject`. `render_email_digest()`
    splits `weekend_events` into `attendable_events`/`informational_events`
    and `templates/email_digest.html.j2` renders the latter under an
    "ALSO THIS WEEK" line (own section whether or not there are any
    attendable events, so the content never just disappears) rather than
    as an equal-weight event card — no link, no date/detail rows, just
    the title. `templates/region.html.j2` gives a non-attendable card a
    `card-informational` class (muted fill, no hover-lift, no `My
    Weekend` star) and an "Informational" label instead of a date kicker.
    12 new tests added (`test_tagging.py` ×4, `test_build_digest.py` ×8);
    `python -m pytest tests/ -q` → 262 passed; `python
    scripts/build_digest.py` → real build, `docs/` restored after
    (sandbox network is proxy-blocked, so no live D57 half-day fetched
    here to show in the generated file — the subject-line/template unit
    tests are the real evidence). Deliberately left `build_weekly_summary_txt`
    (the Facebook-post text) untouched — item 90's own spec named three
    surfaces (subject line, email body, region page) and the Facebook
    post wasn't one of them; it can still list an informational item as
    a plain bullet today, which is a real but smaller gap than the one
    this closes, worth its own follow-up rather than scope creep here.

91. ✅ **Emit a separate `email-send.html` with no preview annotation.** The
    test email went out with `PREVIEW ONLY, NOT PART OF THE EMAIL —
    SUBJECT LINE: …` rendered as the first line of body copy, above the
    wordmark, visible to the reader.

    The annotation is mine and the intent was right — whoever previews
    the file needs to see the exact subject to paste. The mistake is
    where it lives: it sits inside the only artifact there is, and the
    workflow the annotation itself describes is *select all, copy, paste
    into Buttondown*, which ships it. A warning that is inside the thing
    it warns about will be pasted along with it every time. That is a
    design defect, not user error, and it will recur weekly.

    Write two files per region: `email-preview.html` (annotated, for
    reading in a browser) and `email-send.html` (byte-identical minus the
    annotation row — the one to paste). Put the subject line in a third
    place that cannot be pasted by accident: it is already the `<title>`,
    so `weekly-summary.txt` gaining a `SUBJECT:` line at the top costs
    nothing and matches that file's existing `POST`/`FIRST COMMENT`
    convention.

    ✅ **DONE.** `render_email_digest()` gained a keyword-only
    `preview: bool = False` argument, passed through to the template as
    `preview`; `templates/email_digest.html.j2` now wraps the annotation
    `<tr>` in `{% if preview %}`. The build loop calls it twice per
    region — once for `email-send.html` (default, no annotation) and
    once with `preview=True` for `email-preview.html` — from the same
    already-computed args tuple, so the two stay byte-identical apart
    from that row by construction, not by hand-keeping two templates in
    sync. `build_weekly_summary_txt()` now prepends `SUBJECT: {subject}`
    (via the existing `build_email_subject_line()`) ahead of its
    `POST`/`FIRST COMMENT` blocks. Verified against a real build: `diff
    docs/mount-prospect-60056/email-send.html
    docs/mount-prospect-60056/email-preview.html` shows only the
    annotation `<tr>` added on the preview side, and
    `docs/mount-prospect-60056/weekly-summary.txt` now opens with
    `SUBJECT: This weekend in Mount Prospect: Oktoberfest, and 1 more`
    (that region's real annual-events fixture, not fetched network
    data — this sandbox's network is proxy-blocked). 5 new tests added
    to `test_build_digest.py`; `python -m pytest tests/ -q` → 265
    passed. `docs/` restored and the newly-generated, not-yet-tracked
    `email-send.html` files removed (`git clean -f docs/`) before
    committing, per the standing rule against hand-committing generated
    output — CI regenerates and commits `docs/` after merge.

#### P2 (new)

92. ✅ **The template's dark-mode defense does not survive Yahoo — fix it or
    stop claiming it.** `email_digest.html.j2`'s header comment states
    that setting every color explicitly (`bgcolor` attribute *and* inline
    style, on every cell, plus `meta color-scheme: light`) prevents
    clients' auto-invert from producing broken combinations. The Yahoo
    screenshot disproves it: the cream `#fffcf5` card came through as
    dark brown, the `#f6efe1` page background near-black, and the body
    text inverted to near-white. It is legible but it is not the brand,
    and the green CTA against brown is the one element that reads as a
    mistake rather than a theme.

    Yahoo, AOL and Outlook.com apply **forced** color inversion that
    rewrites declared colors rather than honoring `color-scheme` — which
    is why the current approach cannot work in principle, not just in
    this test. The known handles are client-specific: `[data-ogsc]` /
    `[data-ogsb]` attribute selectors for Outlook.com's rewriter, and a
    `prefers-color-scheme` block for the clients that respect it.
    Neither is universal.

    The honest options are to implement those handles and accept partial
    coverage, or to design a palette that inverts acceptably and stop
    fighting it. Either is fine; what is not fine is the comment
    continuing to assert a guarantee that a real client just broke.
    Whichever is chosen, **update that comment** — it is load-bearing
    documentation for anyone who touches this file next.

    ✅ **DONE** (partial coverage, honestly documented). Took the first
    option: implemented both known handles rather than redesigning a
    palette that inverts acceptably, since restoring the *existing*
    brand colors needs no new design work and no new untested judgment
    call about what "acceptable" inverted colors would even look like.
    Added a `<style>` block in `<head>` with two rule sets, each
    restating colors already set inline (nothing new to design): a
    `[data-ogsc]`/`[data-ogsb]` set (Outlook.com's rewriter adds these
    attributes to `<body>` when it force-applies its own colors) and a
    `@media (prefers-color-scheme: dark)` set, both keyed to nine new
    `wt-*` utility classes (`wt-bg`, `wt-card`, `wt-card-sponsor`,
    `wt-cta-bg`, `wt-ink`, `wt-muted`, `wt-accent`, `wt-brand`,
    `wt-border`) added alongside the existing inline styles on every
    colored element, title link, card, and border in the template.
    `!important` is required and used throughout — a stylesheet
    `!important` rule beats a non-important inline style in the CSS
    cascade, which is the whole mechanism this depends on.

    Verified the testable half for real rather than trusting the CSS by
    inspection: rendered the actual generated
    `docs/mount-prospect-60056/email-send.html` in headless Chromium
    (Playwright, pre-installed in this sandbox) with
    `page.emulate_media(color_scheme="dark")` and read back computed
    styles — `body` background `rgb(246, 239, 225)` (`#f6efe1`), `.wt-
    card` background `rgb(255, 252, 245)` (`#fffcf5`), `.wt-ink` color
    `rgb(43, 35, 24)` (`#2b2318`), `.wt-cta-bg` background `rgb(82, 107,
    63)` (`#526b3f`) — every one the original light value, not an
    invert. Ran a control to rule out a false positive (Chromium simply
    ignoring the media query rather than the rule genuinely firing):
    changed the dark-mode rule's color to red in a scratch copy, same
    emulation, and the computed background came back `rgb(255, 0, 0)` —
    confirms the mechanism is live, not coincidental. Did **not** add
    this as an automated pytest test, and said so directly in the
    template's own comment: it would make Playwright and a browser
    binary a CI dependency for one template's worth of coverage, which
    is a worse trade than a manually-verified, documented check. The
    `[data-ogsc]`/`[data-ogsb]` half has no equivalent verification and
    the comment says so too — Outlook.com's rewriter is proprietary and
    this sandbox cannot open a real client, so that half rests on
    documented third-party reports of the attribute names, not a
    confirmed render. Rewrote the header comment end to end to make
    exactly this distinction (what's fixed for Gmail/anything honoring
    `color-scheme`, what's mitigated-and-verified for
    `prefers-color-scheme` clients, what's mitigated-but-unverified for
    Outlook.com, what's still a known gap for Yahoo/AOL) rather than the
    blanket guarantee that shipped before. `python -m pytest tests/ -q`
    → 266 passed (unchanged - no new automated test, by the above
    reasoning); `python scripts/build_digest.py` → real build, `docs/`
    restored after.

93. **A `From:` address that cannot receive replies is a liability, not
    just an inconvenience.** Buttondown sends as
    `hello@withintenmiles.com`. Resolver queries confirm
    `withintenmiles.com` publishes **no MX record**, so that mailbox does
    not exist. Replies fall back to the apex A record (RFC 5321 implicit
    MX), which points at GitHub Pages — four addresses that do not answer
    on port 25 — so the sender queues and retries for 24–48 hours before
    generating a bounce. Silence now, a delayed-delivery notice later.

    Cloudflare Email Routing (free) publishes the MX records and forwards
    `hello@` to a real inbox; it was discussed on 2026-09-16 and never
    enabled. See the Needs Ryan table.

    Beyond the owner missing mail, two reasons this ranks above cosmetic:
    a reply is the **highest-value** thing a local subscriber can send —
    it is how a resident tells you about an event no feed carries, which
    is precisely the content moat this business claims — and major
    mailbox providers' bulk-sender guidance expects a working reply path,
    so a blackholed `From:` is a reputation signal on a domain that has
    none yet.

#### Housekeeping

The test used a **stale copy** of the preview file, pasted before PR #115
merged at 11:57. Its subject named both halves of the Oktoberfest
near-duplicate and its event rows had no detail lines — items 86 and 87
respectively, both already fixed and verified working in current code
(`build_email_subject_line` now returns `Oktoberfest, Fishing Derby, and
2 more` for that input). Nothing to do; recorded so the screenshot is not
read later as evidence those fixes failed. Item 91's `email-send.html`
also reduces the chance of this recurring, since a file named for sending
invites a fresh copy each week.

#### Research pass 2026-09-16 (twenty-second pass)

Three angles never covered before — real estate as a *priced* sponsor
category, Substack's network as a growth channel, and current email
design floors — plus a periodic re-check of the target query and of the
AI-citation assumptions item 22 was built on. That re-check produced a
**retraction**, which is the most useful thing in this pass.

Context for prioritising: the product now sends, authenticates, and lands
in a primary inbox. Every open question has moved from "does it work" to
"can it be found, can it prove an audience, can it keep one" — so this
pass deliberately contains no new UI features.

| Angle | Finding | Consequence |
|---|---|---|
| **Real estate as a sponsor category** | Average agent marketing spend is **>$14,200/yr**; a first neighborhood newsletter budgets **$400–700**; geo-targeted Meta ads **$200–400/mo** for a 1-mile radius. But **Nextdoor sells ZIP-exclusive "featured agent" placement at $30–150/ZIP/month** | The budget exists. The **$5,000/yr tier has a cheap, famous anchor sitting next to it** (item 95) |
| **Substack's network** | **40% of all new subscriptions now originate inside Substack**, and Recommendations is the primary growth engine for publications under 10k subs | Buttondown has no equivalent. Growth here must come from press, SEO and local partnerships — by structure, not by neglect (item 96) |
| **Local growth tactics, priced** | First 1,000 come from asking directly. Local press: 100–500 in a day (confirms the seventeenth pass). **Barter: 3–5 local businesses, and one restaurant with ~2,000 IG followers drives 100–300 subscribers in a single post** | The barter play is free, fits the time budget, and *is* sponsor prospecting (item 94) |
| **AI Overviews, re-checked** | ~47% of US searches overall, but **only ~7% of local-intent searches** — and **15% of local *event* queries**, where they "replace the local pack". Citation is selected on **content structure, claim clarity and entity authority, not organic rank** | Item 22's premise was right in direction, overstated in size. The selection criteria are winnable by a new domain; rank is not |
| **`llms.txt`, re-checked** | Google has **explicitly stated no Search system reads or acts on it**; no major AI provider has committed to reading it as of Q1 2026; crawlers largely are not fetching it | **Retracts half of item 22.** See item 98 |
| **Email design floors** | **55%+ of opens are mobile**, 50% delete what is not optimised, readers give an email **~10–51 seconds**, and the stated body-copy floor is **16px** | The template ships 15px titles and 13px dates/details — under the floor (item 97) |
| **Target query, re-checked** | Eventbrite and AllEvents still own "things to do in Mount Prospect this weekend"; `mpdowntown.com` ranks for the festival itself. Within Ten does not appear | Expected at four days old. Re-check monthly, not weekly |

One incidental find worth keeping, because it is the moat in miniature:
this weekend's Oktoberfest includes a **welcoming, inclusive hour (noon–1
p.m.) for children with special needs and their families**. No aggregator
carries that. It is exactly what item 87's detail lines exist to surface,
and exactly what a ticketing platform's listing will never contain.

#### P1 (new)

94. ✅ **Trade a mention for a mention with 3–5 local businesses — the
    cheapest subscriber acquisition available, and it is sponsor
    prospecting wearing a different hat.** The tactic: offer a business a
    mention in the newsletter in exchange for them promoting it to their
    list or followers. One restaurant with ~2,000 Instagram followers can
    drive **100–300 subscribers from a single post**.

    Why this ranks with the press pitch rather than below it. It costs
    nothing, takes a handful of emails (inside the 30–60 min/month
    budget), and is **repeatable** — where the press mention is one-shot
    (item 89), this can be run again next month with five different
    businesses. And the conversation is the sponsor conversation: you are
    contacting precisely the dentist, ice cream shop and tutoring centre
    `BUSINESS_PLAN.md` names as the target sponsor list, with an opening
    offer that costs them nothing and asks for nothing. A business that
    has already been featured once is a materially warmer lead for the
    $1,200 Annual Partner tier than a cold email.

    Needs a template in `OUTREACH_TEMPLATES.md` — a new §8, short,
    written for a busy owner, leading with what they get. Draftable by
    the build loop; sending stays with Ryan. Sequence it **after** the
    first real send, same as item 89: the pitch is "here is the thing",
    and there needs to be a thing.

    ✅ **DONE (draft, sending is Ryan's).** Added §8 to
    `OUTREACH_TEMPLATES.md`: a note on cadence/sequencing (send after a
    real issue exists, 3–5 businesses/month, repeatable unlike the press
    pitch), then a short subject + body leading with what the business
    gets — the mention itself — with the share-to-their-list ask framed
    as optional, not a condition of the mention. No code changes; this
    is copy only, so no test/build cycle to run.

95. ✅ **The $5,000 Neighborhood Authority tier needs an answer to Nextdoor,
    or it needs repricing.** `BUSINESS_PLAN.md` prices this tier against
    the realtor "neighborhood farming" budget of $500–1,500/month, and
    that budget is real — average agent marketing spend is over
    $14,200/yr. But **Nextdoor sells the same headline promise — be *the*
    featured agent in this ZIP — for $30–150 per ZIP per month.** The
    tier asks ~$417/month. That is 3–14× a competitor the prospect has
    certainly heard of and probably already been pitched.

    This is not an argument to drop the price. It is an argument that the
    tier currently has **no written answer to the obvious objection**,
    and the first realtor who asks will end the conversation. The honest
    differences are real and none of them are in `SPONSOR_KIT.md`:
    Nextdoor sells an ad slot beside user posts, this sells **editorial
    placement inside content the reader opted into**; Nextdoor's audience
    is rented and its rules can change, a subscriber list is owned; and
    the Annual Partner benefits — permanent directory listing, seasonal
    guide spotlight, a live SEO backlink — are assets that persist, not
    impressions that expire.

    Concretely: add a short "compared to" section to `SPONSOR_KIT.md`
    naming Nextdoor and Meta geo-ads with their real prices, and stating
    what this offers that neither does. Naming a competitor's lower price
    yourself is stronger than being caught by it, and the kit currently
    reads as though no alternative exists. Also worth stating plainly:
    **until there is an audience number to put next to the price, no tier
    is sellable at any price** — which is why 94 and the press pitch
    outrank every monetisation item on this list.

    ✅ **DONE.** Added "Compared to Nextdoor and Meta geo-ads" to
    `SPONSOR_KIT.md`, right after the pricing table: names Nextdoor's
    real $30–150/month featured-agent price against this tier's
    ~$417/month up front rather than waiting to be caught by it, then
    three honest differences (editorial placement vs. an ad slot, an
    owned list vs. a rented audience, persistent assets vs. expiring
    impressions) — and one explicit non-claim, that this isn't an
    argument the price is low. Deliberately did *not* put the roadmap's
    other point ("no tier is sellable at any price until there's an
    audience number") into the customer-facing kit itself — true and
    worth stating, but it belongs in this planning document's own
    prioritization reasoning (which is exactly where it already lives,
    two sentences up), not in a document written to make the sale.
    Copy only — no code changes, no test/build cycle to run.

#### P2 (new)

96. ✅ **Name the Substack trade-off out loud, then keep Buttondown.** 40%
    of all new Substack subscriptions now originate inside its own
    network, and Recommendations is the main growth engine for
    publications under 10,000 subscribers. Buttondown has no network at
    all — a subscriber arrives only if something outside the platform
    sends them.

    The recommendation is still **stay**, and it is worth writing down
    why so this does not get re-litigated every time growth is slow. The
    business owns its domain, its list, its HTML template and its
    deliverability posture (`p=quarantine`, verified this afternoon);
    Substack takes 10% of paid revenue and owns the reader relationship,
    which is a bad trade for a business whose revenue is *local sponsor
    memberships*, not reader subscriptions. The network would help growth
    and hurt the actual business model.

    But the consequence must be accepted rather than ignored: **this
    newsletter has no organic growth channel.** Every subscriber comes
    from press (one-shot), barter (item 94), SEO (slow), or paid (item
    78). That is the whole list, it is short, and it is why items 94 and
    77 are the top of the file. Worth a line in `BUSINESS_PLAN.md`'s
    scale-strategy section, which currently discusses scaling regions
    without addressing where readers come from.

    ✅ **DONE.** Added a new paragraph to `BUSINESS_PLAN.md`'s Scale
    strategy section, right after the existing few-regions-sold-well
    reasoning: names the Substack Recommendations stat, states the
    trade-off honestly (a network would help growth and hurt the actual
    membership-based business model), reaffirms **stay on Buttondown**
    with the ownership reasoning already established for item 47's
    deliverability posture, then states the accepted consequence in the
    item's own words - no organic growth channel, four sources total,
    which is why the press pitch and barter template outrank every
    monetization item in the current backlog. Copy only - no code
    changes, no test/build cycle to run.

97. ✅ **Raise the email's body type to the 16px floor.** The template sets
    event titles at 15px and dates, details and the footer at 13px. The
    stated mobile floor is **16px**, 55%+ of opens are mobile, and half
    of readers delete an email that does not read well on a phone — and
    this is a newsletter for parents checking their phone on a Thursday
    evening, which is the mobile case exactly.

    Titles to 16px, secondary lines to 14px, footer may stay at 13px.
    Check it does not push the six-event digest past a comfortable
    scroll; if it does, that argues for grouping (item 90's "Also this
    week" split already creates the structure to do it). Small, testable,
    and it interacts with 90 and 87 — worth doing in the same pass as
    those rather than separately, since all three change the same rows.

    ✅ **DONE.** Event titles 15px→16px, event dates/details 13px→14px.
    Applied the same floor to every other title-style and secondary-line
    row in the template for consistency, not just the event cards the
    item's own description named: the evergreen-highlight title link and
    the sponsor-recommendation title link (both were 15px, same visual
    role as an event title) went to 16px; the "Also this week"
    informational lines and the sponsor spotlight quotes (both were
    13px, same role as an event's date/detail) went to 14px. Left the
    wordmark, the footer, and the small-caps eyebrow labels ("LOCAL
    RECOMMENDATION", "ALSO THIS WEEK", "SPONSOR THIS SPOT", the
    preview-only annotation) alone — those are deliberately small
    kickers, not body copy, matching the item's own "footer may stay"
    allowance. On the comfortable-scroll check: no action needed yet —
    item 90 already ships the "Also this week" grouping this item
    anticipated needing, and a real generated file
    (`docs/mount-prospect-60056/email-send.html`) is still 191 lines,
    same order of magnitude as before. One new test
    (`test_render_email_digest_body_type_meets_the_16px_mobile_floor`)
    asserts no `font-size:15px` survives and spot-checks the specific
    16px/14px rows; `python -m pytest tests/ -q` → 266 passed. `python
    scripts/build_digest.py` → real build, confirmed the generated
    `email-send.html` contains the new sizes; `docs/` restored after
    (no untracked stragglers this time, unlike item 91's pass).

#### P3 (new) — a retraction

98. ✅ **`llms.txt` does not work, and item 22 should stop implying it
    does.** I recommended it. The current evidence is that Google has
    **explicitly stated no Google Search system reads or acts on
    `llms.txt`**, that no major AI provider — OpenAI, Google, Anthropic
    or Meta — has committed to reading it as of Q1 2026, and that AI
    crawlers largely are not fetching it at all.

    What to actually do, in order:

    - **Keep the file.** `build_llms_txt()` generates it from the same
      `region_summaries` the sitemap uses, so its marginal cost is zero
      and it cannot drift. Deleting working, self-maintaining code to
      make a point is worse than leaving it.
    - **Stop counting it as progress.** Item 22 is marked "first slice
      done" largely on its strength. That slice bought less than claimed.
    - **Correct item 22's premise while there.** It argues from "AI
      Overviews now trigger on roughly half of all queries" — true
      overall (~47%), but **local** intent is ~7%, and local *event*
      queries 15%. Still worth pursuing, at roughly a third of the
      implied size.
    - **Move the effort to what the same research says decides
      citation**: content structure, claim clarity, and entity
      authority — explicitly *not* organic rank. The site already has
      schema.org `Event` and `FAQPage`; the gap is entity clarity
      (consistent naming of "Within Ten" as a publisher across pages,
      an `Organization` entity, a real About page stating who publishes
      this and from where). That is the work item 22 should have been
      pointing at, and it is winnable by a four-day-old domain in a way
      that out-ranking Eventbrite is not.

    The robots.txt half of item 22 — explicitly naming GPTBot,
    ClaudeBot, OAI-SearchBot and the rest — stands. Allowing crawlers
    that do exist is unaffected by a convention file that nothing reads.

    ✅ **DONE.** Added a correction block directly inside item 22 above
    (not a silent edit — the original text stands, with a dated
    correction appended, matching this file's own established pattern
    from the seventh research pass's FAQPage correction) covering the
    first three bullets: kept `llms.txt` (already true — it's derived,
    self-maintaining, zero marginal cost, nothing to gain by deleting
    it), stated plainly that it shouldn't have counted as progress, and
    corrected the ~50%-of-queries premise to the real ~7%/~15% local
    figures. The fourth bullet — moving effort to entity clarity
    (`Organization` schema, a real About page) — is genuine new work,
    not a documentation fix, so it is **not** implemented in this same
    pass: bundling a real feature into a retraction would blur which
    part is "fixing a false claim" and which part is "shipping
    something new." Spun out as item 99 below instead, in this pass, so
    the concrete next step exists rather than being left as a sentence
    inside a correction no one re-reads. Copy only in this item itself —
    no code changes, no test/build cycle to run.

99. ✅ **Add `Organization` schema and a real About page — the entity-
    clarity work item 22 should have been pointing at.** Item 98's
    retraction found the actual lever for AI-search citation is content
    structure, claim clarity, and entity authority, not organic rank or
    a convention file nothing reads. The site already has real
    structured data (`Event`, `FAQPage`, `WebSite`) and a consistent
    `SITE_NAME` (item 22's PR #49); what's missing is the thing that
    tells a crawler or an AI *who* is publishing all of it and *why
    they should trust it* — exactly the kind of signal a four-day-old
    domain can win on a level field, unlike out-ranking Eventbrite for
    "things to do this weekend."

    Concretely: an `Organization` JSON-LD block (name, url, logo if one
    exists, `sameAs` for any real social/directory profile) referenced
    from each page's existing `WebSite`/`WebPage` graph via `publisher`,
    plus a genuine About page — who runs this, why it exists, how it's
    built (the automated-freshness story item 22 already tells is
    itself a real trust signal, not filler) — linked from the site
    footer/nav so it's discoverable, not an orphan page. No fabricated
    facts: whatever the About page states about who/why has to be true
    and sourced from what this file already knows (the owner, the
    ZIP-based service area, the automated weekly rebuild), the same
    discipline every other GEO item in this file already holds itself
    to.

    ✅ **DONE.** New `templates/about.html.j2` + `render_about_page()`,
    written to `/about/` alongside the sponsor/hub pages in the main
    build loop. Content is exactly the four things the item asked for
    and nothing invented beyond them: what the site is (reusing the
    real four-ZIP list already in `SPONSOR_KIT.md`), who publishes it
    ("a local parent," the same public self-description already used
    in the real press-pitch template rather than a new bio), why it
    exists (the near-zero-time constraint from `BUSINESS_PLAN.md` and
    the same stale-guide problem item 22 already argued from), and how
    it's built (real sources, never-invents-content, open source, with
    a link to the actual GitHub repo). No logo, no `sameAs` - neither a
    logo asset nor a real social profile exists, so neither is claimed.

    `Organization` schema (`build_organization_json_ld()`) is defined
    once, on this page, with a stable `@id`
    (`ORGANIZATION_ID = SITE_BASE_URL + "about/#organization"`).
    `build_freshness_json_ld()`'s `WebSite` node (every region page)
    now carries `"publisher": {"@id": ORGANIZATION_ID}` instead of
    naming the site with no publisher at all - the standard schema.org
    pattern of referencing one entity by `@id` rather than duplicating
    its full definition on every page. `/about/` added to
    `collect_sitemap_urls()` (flows into both `sitemap.xml` and the
    IndexNow submission automatically, no separate wiring needed) and
    to `build_llms_txt()`'s own map. Linked from the footer of all four
    page templates (hub, region, weekend hub, sponsor) - not an orphan
    page.

    7 new tests (`test_build_digest.py`); one existing test
    (`test_build_freshness_json_ld_names_the_site_consistently`) updated
    for the new `publisher` field. `python -m pytest tests/ -q` → 272
    passed. `python scripts/build_digest.py` → real build; confirmed in
    the actual generated output: `docs/about/index.html` contains the
    real `Organization` JSON-LD with the right `@id`,
    `docs/mount-prospect-60056/index.html`'s `WebSite.publisher`
    references that same `@id`, `docs/sitemap.xml` and `docs/llms.txt`
    both list `/about/`, and the IndexNow submission count went from 40
    to 41 URLs in this build's own log line - the new page reached
    every place a URL is supposed to reach without hand-editing any of
    them individually. `docs/` restored and the newly-generated
    (previously untracked) `docs/about/` directory removed before
    committing, per the standing rule against hand-committing generated
    output.

#### Research pass 2026-09-17 (twenty-third pass)

The build loop cleared 92 and 94–98 overnight and added 99 off item 98's
tail, so the open P1s are 90 and 91 (both its work) and 93 (Ryan's). With
the backlog that thin, this is a deeper batch rather than a token one.

Angles: youth-sports and family scheduling as a *surface*, the parenting-
local category's one real exit, retention benchmarks, and a design
re-check. No new UI features again — and item 103 exists specifically to
keep it that way.

| Angle | Finding | Consequence |
|---|---|---|
| **Family scheduling load** | Parents average **30.4 hrs/week** on the mental load of scheduling, **17.5 communications/week** about kids' schedules, **11.5 activities/week** per child. The products winning here **feed the calendar the family already keeps** rather than being another destination | The site emits per-event `data:` ICS downloads and **no subscribable feed** — verified, `find docs -name "*.ics"` returns nothing (item 100) |
| **Newsletter retention** | News-vertical churn is **5.47%/month** (among the lowest of any category). Regular openers are **2× more likely to still be subscribed at 12 months**. MailerLite, across ~1.4M campaigns: **monthly to twice-weekly** is the band where opens hold without abnormal churn | The planned weekly Thursday send is **validated, not a guess** — and the metric to watch is open *frequency*, not open rate (item 102) |
| **Category exit** | Red Tricycle — local family activity guides across US cities, i.e. this exact product — **sold for $6.5M in 2020**; the buyer wanted parent-audience access for brand advertisers | The asset is the audience. Reinforces item 96 |
| **Seasonal monetisation** | Q4 is the strongest publisher window of the year; local businesses pay **$500–5,000/season** to sponsor community markets | The fall guide exists but **punts on the one thing everyone searches** (item 101) |
| **Design, re-checked** | 2026 direction is typography-as-interface and **restraint**: "identify the two or three directions that fit, execute with craft, resist the rest." Refined serif headings signal editorial polish | The site already does this — Fraunces + Inter, generous whitespace. The risk is **adding**, not lacking (item 103) |

#### P1 (new)

100. ✅ **Publish a subscribable `calendar.ics` per region — the strongest
     retention mechanism available, and a static file.** Today the site
     offers a per-event "Add to calendar" `data:` URI: a one-time copy
     that goes stale the moment anything changes and requires a fresh
     decision per event. What it does not offer is a **subscription** —
     one click, and every future event in that region appears in the
     family's own calendar forever.

     Why this ranks as P1 rather than a nice-to-have. Retention is the
     open question the product has never addressed, and the numbers
     around the target reader are stark: 30.4 hours a week of scheduling
     load, 11.5 activities a week per child. Youth sports has already
     standardised on ICS subscription — leagues, SportsEngine and school
     calendars all expose subscribe links, and hardware like Skylight
     ingests them directly. **A parent who subscribes once is retained
     without ever opening an email**, which is the only retention channel
     that survives a bad subject line, an inbox move, or a busy month.

     It also fits this architecture better than almost anything proposed
     here: `build_digest.py` already serialises events to RFC 5545
     (`_ics_escape`, the per-event builder) — this is the same data
     written to `docs/<region-id>/calendar.ics` once per build instead of
     inlined per card. No framework, no service, nothing to maintain.

     Specifics worth getting right, because a calendar feed is judged
     harshly: stable `UID` per event (slug + date, so re-fetches update
     rather than duplicate), `SEQUENCE` bumped on change, a sensible
     `X-WR-CALNAME` ("Within Ten — Mount Prospect"), `REFRESH-INTERVAL`
     and `X-PUBLISHED-TTL` of `PT12H`, and `DTSTAMP`/`LAST-MODIFIED` set.
     Offer it as both `webcal://` (which Apple and Google follow into
     the subscribe flow) and plain `https://`. Apply item 90's
     `attendable` split here too — a school half-day belongs in a
     calendar feed even more naturally than in an email, but as a
     transparent all-day entry, not a timed event.

     One honest dependency: this is only as good as the data's stability.
     The relative-URL bug (#113) and the duplicate-title issue both
     showed the pipeline can emit noisy records, and a calendar
     subscriber sees every correction as a notification. Ship it after
     90, not before.

     ✅ **DONE.** `build_region_calendar_ics()` writes every dated event
     across every block (fetched sources + curated annual events, not
     weekend-filtered - a subscription is the whole calendar) to
     `docs/<region-id>/calendar.ics`, reusing `_ics_escape` from the
     existing per-event `data:` URI builder. Shipped after 90 as
     instructed: item 90's `attendable` split applies here too - a
     non-attendable event renders as a transparent, all-day
     `DTSTART;VALUE=DATE` entry instead of a timed one a calendar app
     would mark "busy" for. Stable per-event `UID` (region + event date
     + a sanitized title slug) so a rebuild updates the same entry
     rather than duplicating it - verified directly:
     `test_build_region_calendar_ics_stable_uid_across_rebuilds` builds
     the same event at two different `now` timestamps and asserts the
     `UID` line is byte-identical. `X-WR-CALNAME`, `REFRESH-INTERVAL`,
     and `X-PUBLISHED-TTL` all set to `PT12H` as specified. Region page
     gained a "📅 Subscribe once, get every event automatically" block
     (main page only, `nav_current == "all"`) with both a `webcal://`
     link (via a `replace` filter on the `https://` URL, no second URL
     built) and a plain `https://` download link. `/calendar.ics` added
     to `build_llms_txt()` under a new "## Calendars" section (not
     added to `sitemap.xml` - a calendar file isn't a page a search
     engine indexes).

     **`SEQUENCE` is always `0` — a documented simplification, not an
     oversight.** Correctly bumping it on a real content change needs a
     persisted per-event revision counter this pipeline doesn't keep
     anywhere (`source_health.json` tracks fetch success/failure, not
     event content); building that just for this would be new state-
     tracking infrastructure, not a byproduct of the feature. A
     subscribed calendar client re-fetches and diffs by `UID` + content
     on every periodic refresh regardless, which covers the common case
     here - stated directly in the function's own docstring rather than
     silently shipping a partial `SEQUENCE` implementation.

     8 new tests (`test_build_digest.py`); `python -m pytest tests/ -q`
     → 296 passed. `python scripts/build_digest.py` → real build, then
     **genuinely validated the output**, not just grepped it: parsed
     `docs/mount-prospect-60056/calendar.ics` with the `icalendar`
     Python package (RFC 5545 compliant, confirmed installed in this
     sandbox) and printed the parsed `VEVENT`s back out - two real
     annual events (`Oktoberfest`, `Fall Festival & Oktoberfest`, this
     sandbox's own network being blocked means only curated/annual
     content resolves here) came back with correct `UID`/`SUMMARY`/
     `DTSTART`/`DTEND` values. `docs/` restored and the four newly-
     generated `calendar.ics` files removed before committing.

101. ✅ **Publish the four villages' official trick-or-treat hours on one
     page, before mid-October.** The fall guide currently handles this by
     pointing at the City's news page and saying the hours get posted
     there each October. That is the honest thing to write when you have
     no data — but it punts on **the single highest-volume hyperlocal
     query of the fourth quarter**, and it is the exact query the civic-
     feed moat was built to win.

     No competitor aggregates this. Eventbrite and AllEvents list
     ticketed events; trick-or-treat hours are a municipal announcement,
     which is precisely the category this site claims and they ignore.
     Four villages' hours on one page, cross-linked from each region, is
     a page that has no competition, answers a real question, and is
     genuinely useful to a parent deciding which town to take the kids
     to — which is the "trip across a few nearby towns" promise made
     concrete for the one night of the year everyone does exactly that.

     Timing is the whole point: villages typically post in late September
     or early October, the query peaks in the two weeks before the 31st,
     and a new domain needs lead time to get indexed. **This is a
     two-week window and it opens now.** Q4 is also the strongest
     sponsor window of the year, which makes it the best possible page
     to have a Halloween-relevant sponsor on.

     Implementation is ordinary: four URLs into the existing `guides:`
     structure, `Event` schema with real dates once the hours are known,
     and the standing "check the village's page" line kept as a fallback
     for any village that has not posted yet. Honest handling of the
     not-yet-posted case matters more than completeness — a confidently
     wrong trick-or-treat time is the worst error this site could make.

     ✅ **DONE** (shell shipped now, real hours still pending - as
     expected on 2026-09-17). Each region's YAML gained a structured
     `trick_or_treat: {url, hours}` block (`hours: null` for all four
     right now - no village has posted yet, which is the honestly
     correct state this early). New `templates/trick_or_treat.html.j2` +
     `render_trick_or_treat_page()`, written to `/trick-or-treat/`:
     one row per town, showing the real hours in place once `hours` is
     set, or "Not yet posted for this year — check the village's page"
     linking to that village's real news/notices URL (already verified
     in each region's fall-guide entry, reused rather than re-derived)
     until then. Each region's fall-family-guide "Official trick-or-
     treat hours" item now links to this combined page instead of
     straight to the village source - the "cross-linked from each
     region" the item asked for - and the new page itself still links
     out to each village's real source as the fallback.
     `/trick-or-treat/` added to `collect_sitemap_urls()` (flows to both
     `sitemap.xml` and IndexNow automatically) and to `build_llms_txt()`.

     **`Event` schema deliberately deferred, not shipped partial.** The
     item asked for "Event schema with real dates once the hours are
     known," but `hours` is a free-text string
     (e.g. "3:00–7:00 PM, Saturday, October 31") - parsing that into a
     machine-readable date reliably enough to trust in structured data
     is its own small problem, not a byproduct of this one. Once a real
     village posts real hours, that's the moment to add a proper
     `date`/`start_time`/`end_time` field and generate `Event` JSON-LD
     from those, rather than regex-guessing a free-text string now for
     data that doesn't exist yet.

     6 new tests (`test_build_digest.py`); `python -m pytest tests/ -q`
     → 288 passed. `python scripts/build_digest.py` → real build;
     confirmed in the actual generated output: `docs/trick-or-treat/
     index.html` lists all four towns in the honest not-posted state,
     `docs/sitemap.xml` and `docs/llms.txt` both list the new URL, the
     IndexNow submission count went from 41 to 42 URLs in the build
     log, and `docs/mount-prospect-60056/guides/fall-family-guide/
     index.html`'s trick-or-treat item links to `/trick-or-treat/` as
     intended. `docs/` restored and the newly-generated `docs/trick-or-
     treat/` directory removed before committing.

#### P2 (new)

102. ✅ **Record the cadence as validated, and put churn in the sponsor
     kit.** Two numbers arrived that answer open questions rather than
     raising them. MailerLite's data across roughly 1.4 million campaigns
     puts **monthly to twice-weekly** as the band where opens and clicks
     hold up without driving abnormal churn — so the planned weekly
     Thursday send (items 31/83) is inside the validated zone and should
     stop being revisited. And **News-vertical churn runs 5.47%/month**,
     among the lowest of any category, which is the benchmark this
     business will actually be measured against.

     Two consequences. First, the retention metric to watch is **open
     frequency, not open rate** — regular openers are 2× more likely to
     still be subscribed at twelve months, which makes "how many people
     open most weeks" the leading indicator and a single week's open rate
     mostly noise. Second, `SPONSOR_KIT.md` should carry the churn
     benchmark next to the open-rate benchmarks item 24 already put
     there. A sponsor buying an **annual** membership is buying next
     August's audience, not this week's, and a stated retention figure is
     the only honest way to describe what they are getting. It is also a
     better argument than a subscriber count, which is the one number
     this business will be weakest on for months.

     ✅ **DONE — and found item 24's own follow-up had never actually
     shipped.** Item 24 said "those same numbers belong in
     `SPONSOR_KIT.md`" back when the send itself was built, but the
     open-rate benchmark was never added there - checked directly
     (`grep` for the 20-30%/40% figures in the kit came back empty)
     rather than assumed. Added a new "Reach & retention" section,
     right before "Placements & pricing" so it's read before the price
     table: the open-rate benchmark item 24 always intended to land
     there, the 5.47%/month news-vertical churn figure, the "an annual
     membership buys next August's audience, not this week's" framing,
     and a plain statement that a subscriber count is deliberately not
     the lead number this early. Also names the weekly Thursday cadence
     as sitting inside the validated monthly-to-twice-weekly band,
     closing the "should this cadence be revisited" question the item's
     own title raised. Copy only - no code changes; `python -m pytest
     tests/ -q` → 309 passed (unchanged, confirming nothing else broke).

103. ✅ **Write down the design principles, so the build loop stops adding.**
     The 2026 research is unusually clear that the failure mode for a
     site like this is accumulation: "the strongest websites will not try
     to use twelve trends at once — identify the two or three directions
     that fit the audience, execute those with craft, and resist the pull
     of everything else." Typography as primary interface and generous
     whitespace are the two directions; refined serif headings are what
     signal editorial polish rather than template.

     The site already does this. Fraunces for headings, Inter for body,
     a beige/green palette, no framework, no motion for its own sake —
     that is the restrained editorial direction the research describes,
     arrived at already. So the finding is not a change; it is a
     **defence**, and it needs writing down precisely because nothing
     currently protects it. Eleven UI features have shipped and each one
     was individually justified.

     A short `DESIGN_PRINCIPLES.md` — the two directions, what they rule
     out, and a standing question ("does this earn its place, or is it
     one more thing?") — costs one file and gives every future pass
     something to argue against. Pair it with a real constraint: **new UI
     features need a stated reason a reader would miss them**, and
     "competitors have it" is not one. The site already has most features
     its competitors have; what it does not yet have is readers.

     ✅ **DONE.** Added `DESIGN_PRINCIPLES.md` at the repo root: the two
     directions (typography as the primary interface; restraint over
     accumulation) named against what the site already does (Fraunces/
     Inter, beige/green palette, no framework, the one View Transitions
     animation framed explicitly as a progressive enhancement rather
     than a feature) rather than as a hypothetical target. A concrete
     "what this rules out" list (a component library, decorative
     animation/parallax, stock photography, a third accent color or
     second display face, dashboard-density layouts) so the defence is
     checkable, not just aspirational. Closes with the item's own
     standing question and the "competitors have it" non-justification,
     stated as a rule for future PRs/commits to answer against, not
     just prose to have read once. Copy only - no code changes; `python
     -m pytest tests/ -q` → 309 passed (unchanged).

#### P3 (new)

104. ✅ **The seasonal-circuit guide exists in one region out of four.**
     `config/regions/mount-prospect-60056.yaml` carries a
     `seasonal-circuit-guide`; Arlington Heights, Des Plaines and
     Palatine each have `fall-family-guide`,
     `birthday-parties-and-kids-classes` and `new-to-town`, and no
     circuit guide. Farmers markets and seasonal circuits are among the
     most reliable recurring draws a suburb has, and they are the kind of
     thing a resident of one town will happily drive to the next town
     for — the cross-region promise again.

     Cheap to close: YAML only, no code, following the existing
     civic-source-only discipline the other guides observe. P3 because
     it is breadth on something already working rather than a new
     capability, and because item 101's Halloween window closes first.

     ✅ **DONE.** Added a `seasonal-circuit-guide` to Arlington Heights,
     Des Plaines, and Palatine's YAML (same position as Mount
     Prospect's: between `birthday-parties-and-kids-classes` and
     `new-to-town`), each with three real, WebSearch-verified (2026-09-
     17) items - a downtown/city annual-festival organizer, a village/
     city seasonal-events hub, and the Park District's own seasonal
     programming:

     - **Arlington Heights**: Downtown Arlington Heights (Harmony Fest
       / Sounds of Summer, linked at the org's root rather than a
       year-specific event page, since this guide is evergreen), the
       Village's events page, Arlington Heights Park District.
     - **Des Plaines**: the City's own "City Sponsored Events" hub
       (Fall Fest) and its Taste of Des Plaines page, Des Plaines Park
       District. **Deliberately omitted a farmers market entry** - the
       search results on one were conflicting (a stale "ended in 2016"
       report alongside directories still listing it active), and
       asserting an unconfirmed fact would break every other guide's
       own discipline. Two confirmed items plus the Park District was
       judged better than three items where one is guessed.
     - **Palatine**: the Rotary Club of Palatine (Oktoberfest's real
       organizer, already used for this year's dated `annual_events`
       entries), the Palatine Farmers' Market's real stable page
       (`/663/Farmers-Market`, not one of the site's transient per-
       event calendar links), Palatine Park District.

     YAML-only as scoped - no code changes. `python -m pytest tests/ -q`
     → 309 passed (unchanged, confirming nothing broke). `python
     scripts/build_digest.py` → real build; confirmed all four regions
     now show 4 guides each in the build log, and spot-checked the real
     generated `docs/<region>/guides/seasonal-circuit-guide/index.html`
     for all three new regions - each shows the real title, summary,
     and the correct organizer URLs (`downtownarlingtonheights.us`,
     `desplainesil.gov`'s City Sponsored Events page, `palatinerotary.org`).
     `docs/` restored and the three newly-generated guide directories
     removed before committing.

#### Research pass 2026-09-17 (twenty-fourth pass — owner-requested build)

Not a research pass. The owner enabled Cloudflare Email Routing (MX now
resolves to `route1/2/3.mx.cloudflare.net` with
`v=spf1 include:_spf.mx.cloudflare.net ~all`, confirmed by resolver
query — item 93 closed) and asked for an automated Thursday send, which
was built here rather than queued: `scripts/send_newsletter.py`,
`.github/workflows/send-newsletter.yml`, and a `send:` block in
`config/newsletter.yaml`.

The apex SPF now carries Cloudflare's include and **not** Buttondown's,
which is correct and worth recording: Buttondown's records live in its
delegated subdomain, DMARC is `aspf=r`, and the first real send landed in
a Yahoo primary inbox — so alignment is carried by DKIM. Adding a second
sender on the apex later would need this re-checked rather than assumed.

Two deliberate choices, both reversible in one line, both the owner's to
overrule:

- **`mode: draft`, overruled to `send` the same day.** It shipped on
  draft: an email cannot be unsent and the pipeline had just shipped a
  wrong subject line (item 90). The owner overrode it with a better fact
  than the caution rested on — he is the only subscriber, so the blast
  radius of a bad issue is his own inbox, and a live weekly send tests
  more than a draft nobody judges. Worth recording that the override has
  an expiry: the reasoning stops holding the moment the list has anyone
  else on it, which the press pitch (item 77) or the barter play (item
  94) could cause in a single day. Revisit before either goes out.
- **Thursday 12:00 UTC** (07:00 CDT). The owner asked for mornings; item
  31's research puts peak opens at 3–7pm. Built as asked, with the
  alternative cron named in a comment.

#### P2 (new)

105. ✅ **A combined multi-region email, or an honest reason there isn't
     one.** The send workflow mails **one** region's digest — Mount
     Prospect, the home region with the most sources — because
     Buttondown's free plan is a single list with no segmentation, and
     mailing four separate emails to one undifferentiated list would be
     worse than mailing one.

     But the signup form is on **every** region page. Someone who
     subscribed from the Palatine page is currently going to receive
     Mount Prospect's weekend, which is not what they asked for and is a
     good way to earn an unsubscribe from the first issue. That is a real
     defect the moment the list has anyone outside Mount Prospect on it —
     which the press pitch (item 77) could cause in a single day.

     Two honest routes, and the cheap one is probably right:

     - **A combined email**: one issue, four short region blocks, each
       with its own heading and link. The data is already merged for
       `docs/this-weekend/`, so the template is the work, not the
       pipeline. Longer, but every subscriber finds their town, and the
       cross-region browse is the product's actual promise.
     - **Per-region lists**: correct, and it needs either Buttondown tags
       (plan-gated, unverified) or four newsletters, which multiplies the
       owner's weekly click by four. Against the time budget.

     Recommend the combined email, sequenced **before** the press pitch
     rather than after, for the same reason item 89 sequenced the first
     send before it: the mention converts once.

     Until it ships, `config/newsletter.yaml` should say plainly that
     non-Mount-Prospect subscribers are getting the wrong region — the
     comment there currently explains the constraint but not the
     consequence.

     ✅ **DONE — and this closes a live gap, not a theoretical one.**
     Picked up ahead of items 102-104 because `send.mode` is now `"send"`
     (the owner's own 2026-09-17 instruction, made when he was the only
     subscriber) with the explicit instruction to "revisit this before
     [the press pitch or the barter play] goes out, not after" — both
     of which have shipped templates ready to go. Waiting for either to
     actually go out first would have meant fixing this after a real
     subscriber had already received the wrong region's email once.

     Took the recommended route: `render_combined_email_digest()` +
     `templates/combined_email_digest.html.j2`, one issue with a short
     block per region (heading linking to that region, up to 4
     attendable events, item 90's "Also this week" grouping for
     informational ones, that region's own active sponsor if any, a
     "See everything in X" link). Every region appears every week, even
     one with nothing dated (falls back to its own free evergreen
     highlights, then an honest empty state) - "every subscriber finds
     their town" from the item's own reasoning, taken literally.
     `build_combined_email_subject_line()` names every region with an
     attendable event this weekend (`_join_names()` for natural "X, Y,
     and Z" phrasing), falling back to naming every covered region with
     the same "what's coming up" honesty as the single-region version
     if none have one. The per-region data (`weekend_events`,
     `evergreen`, `sponsor`) was already computed once per region in
     `main()`'s existing loop for other outputs - collected into a new
     `combined_email_sections` list alongside the existing
     `hub_weekend_sections`, not fetched or computed twice.

     `scripts/send_newsletter.py` gained a `COMBINED_REGION = "combined"`
     sentinel: `send.region: "combined"` reads
     `docs/combined-email-send.html` instead of one region's own file.
     **Set `config/newsletter.yaml`'s `send.region` to `"combined"`
     in this same change** - implementing the template without pointing
     the live sender at it would leave the actual defect unfixed. Left
     `send.mode: "send"` exactly as the owner set it; this only changes
     *which* content a send carries, not whether one happens.

     14 new tests across `test_build_digest.py` and
     `test_send_newsletter.py`; `python -m pytest tests/ -q` → 306
     passed. `python scripts/build_digest.py` → real build; the
     generated `docs/combined-email-send.html` correctly lists all four
     regions (Arlington Heights, Des Plaines, Mount Prospect, Palatine)
     with the real subject `This weekend across Des Plaines, Mount
     Prospect, and Palatine` (Arlington Heights had nothing dated this
     particular build); `diff` against `docs/combined-email-preview.html`
     shows only the one annotation block added, same pattern as item 91.
     Then ran the actual send script for real: `python
     scripts/send_newsletter.py --dry-run` against that real generated
     file printed `Region: combined` / the correct subject / a real byte
     size, and made no network call - genuine evidence the wiring works
     end to end, not just that the template renders. `docs/` restored
     and the two newly-generated combined-email files removed before
     committing.

#### Housekeeping

A `/code-review` pass over the newly-live-send-critical code
(`combined_email_digest.html.j2`, `send_newsletter.py`) - worth doing
now that a real send actually goes out on this path - found two real
bugs the tests up to that point hadn't caught, both confirmed against
real generated output before being called real:

- **The combined email's house ad never rendered, for any region,
  ever.** The template checked `{% if sponsor and is_active_sponsor %}`
  with no `{% elif sponsor %}` fallback, unlike `email_digest.html.j2`
  and `region.html.j2`, which both fall back to the "SPONSOR THIS SPOT"
  house ad item 88 added specifically so the email is never the one
  artifact that fails to mention a slot is for sale. Confirmed live,
  not hypothetical: re-running the real build showed the actual sent
  email (the one behind `em_5hgyjgfytf8hws9xxpw6b0fesk` above) would
  have had **zero** sponsor mentions across all four regions, since
  none currently has a paying sponsor. Fixed with the same house-ad
  block the other two templates already use.
- **A region with only a non-attendable event and nothing else silently
  dropped it.** The "ALSO THIS WEEK" block was nested inside the
  `{% if attendable_events %}` branch only, so a region with a school
  half-day/closure and no attendable events or evergreen highlights
  showed neither the closure notice nor anything else - exactly the
  content item 90 required to always surface, just never as a headline.
  Hoisted the check out so it fires independently of which branch
  covers the attendable/evergreen/empty state, matching how
  `email_digest.html.j2` already checks it in both of its branches.

A third, lower-severity finding from the same pass: `send_newsletter.py`
logged the Gmail 102KB clip-limit check against `len(html)` (character
count) instead of the real UTF-8 byte size - harmless while every
character is single-byte ASCII, but the templates are full of em
dashes/arrows/curly quotes, and the gap is real: the actual combined
email's character count (18,279) undercounts its real byte size
(18,301) already, today, with only four regions. Extracted into a
tested `html_byte_size()` helper rather than left inline.

Not from the research loop - found by choosing to review the riskiest
recent code now that it is live-send-critical, rather than waiting for
a research pass to flag it or a real subscriber to notice a missing
sponsor block. 5 new tests; `python -m pytest tests/ -q` → 314 passed.
`python scripts/build_digest.py` → real build; confirmed the fixed
house-ad block actually appears four times in the real generated
`docs/combined-email-send.html` (once per region) where it previously
appeared zero times, and confirmed the real byte-vs-character gap
directly against that same file. `docs/` restored after (no untracked
stragglers this time).

#### Research pass 2026-09-17 (twenty-fifth pass)

The newsletter now actually sends — workflow run `35176614362`, Buttondown
id `em_5hgyjgfytf8hws9xxpw6b0fesk`, the combined all-regions template,
not a dry run. Every question this file has carried since the third pass
about *whether it can mail anyone* is closed.

Which changes what matters. For twenty-four passes the binding
constraint was "can it send". It is now "what happens to the person who
subscribes" — and the honest answer today is **up to six days of
silence**, then a four-town email they did not quite sign up for. Both
are cheap to fix and both get materially more expensive the moment the
press pitch lands.

| Angle | Finding | Consequence |
|---|---|---|
| **Welcome emails** | Average **34.79% open**, up to **4× the opens and 5× the clicks** of a standard newsletter; automated sends beat scheduled campaigns (**38%** vs. campaign baseline); a welcome *series* converts ~**4%** against ~0.87% for one-off blasts | The single highest-open email this business will ever send does not exist yet (item 106) |
| **Local Facebook groups** | **70/30** promotional norm, designated promo days are common, and the reliable move is **asking the admin first** rather than posting and hoping | The weekly Facebook post is *already generated* (`weekly-summary.txt`). What is missing is permission and a target list (item 107) |
| **Event syndication** | Eventbrite is free and unlimited and auto-feeds Bandsintown | Not usable here, for a reason worth writing down (item 109) |
| **Signup copy vs. what ships** | The form on every region page promises "The weekly digest"; since item 105 it delivers all four towns | A promise mismatch introduced yesterday, on the page where expectations are set (item 108) |

#### P1 (new)

106. **Set up the welcome email — the highest-open message this business
     will ever send, and it currently does not exist.** Someone who
     subscribes on a Saturday hears nothing until Thursday. That is up to
     six days of silence at the exact moment their interest is at its
     peak, and it is the first impression the product makes.

     The numbers are unusually lopsided: welcome emails average **34.79%
     opens** and run up to **4× the opens and 5× the clicks** of a
     regular newsletter, and automated sends beat scheduled campaigns on
     both engagement and revenue. This is the cheapest engagement in
     email marketing and the business is currently declining it.

     It also fits the architecture better than almost anything: **it does
     not need to be dynamic.** A welcome email is evergreen — what this
     is, which four towns it covers, when it arrives (Thursday morning),
     a link to the reader's region page, a link to the current
     trick-or-treat page while that is seasonal, and an explicit invitation
     to reply with an event no feed carries. That last line matters more
     than it looks: replies now work (Cloudflare Email Routing, item 93),
     a reply is the highest-value thing a local subscriber can send, and
     resident-supplied events are the content moat competitors cannot
     copy. One-time setup in Buttondown's UI, zero recurring owner time,
     no code.

     Two honest dependencies. Confirm Buttondown's free plan exposes a
     welcome/greeting email (the API works, but that is not evidence
     about this feature). And the one-off-vs-series finding — three
     emails generate ~90% more orders than one — is an **e-commerce**
     benchmark; do not port a three-part drip onto a local events
     newsletter, where it would read as pushy. One good welcome email.

     **Narrowed the first dependency by WebSearch (docs.buttondown.com is
     egress-blocked from here, same as every other real fetch this
     sandbox can't make directly), without fully resolving it.**
     Buttondown has two structurally different features that could
     satisfy this item, and they are not the same cost:

     - **"Automations" / a welcome *sequence*** (`docs.buttondown.com/
       welcome-sequence`) is a paid add-on, confirmed consistently across
       multiple independent search results — **$29/month**, part of the
       Standard tier. This is the multi-email, branching-timing feature,
       and it is overkill for this item anyway: it was never asking for a
       sequence, just one email.
     - **A distinct, simpler "welcome email"** is its own toggle under
       **Settings → Subscribing → Welcome**, described in Buttondown's
       own docs (`transactional-emails-welcome`) as a *transactional*
       email — sent once, automatically, right after a subscriber
       confirms — a different feature category from "automations"
       entirely (siblings: a confirmation email, this welcome email, and
       a "premium welcome email" for paid-subscription upgrades, which
       does not apply here). This is the one-off email item 106 actually
       wants.

     What search couldn't settle: whether *this* toggle/its customization
     is free-plan-available or itself needs the Standard tier — results
     disagreed (one described transactional-email customization broadly
     as Standard-gated; the welcome email's own doc page didn't repeat
     that restriction). Real uncertainty, not resolved by more searching
     — the honest next step is a 30-second look at the actual toggle in
     the live account, not another guess. Updated the "Needs Ryan" row
     with the exact setting path and the corrected cost framing, so
     whoever checks it isn't tempted to reach for the $29/month
     automation when the free toggle may already do the job.

107. ✅ **Ask three local Facebook group admins for permission — the channel
     where this audience actually is, and the weekly post is already
     written.** `build_weekly_summary_txt()` has emitted a
     Facebook-shaped `POST` / `FIRST COMMENT` pair for every region for
     weeks (the comment carries the link so the post itself is not
     downranked). Nobody has ever posted one. The asset exists and is
     idle.

     Worth distinguishing this from item 84, where Reddit was **rejected**
     on exactly this territory. Reddit's 90/10 norm requires 9–19
     non-promotional contributions between promotional posts and 61% of
     the relevant subreddits ban self-promotion outright — a recurring
     cost against the one resource `BUSINESS_PLAN.md` says the owner does
     not have. Facebook's norm is the softer **70/30**, many local groups
     run a designated promo day, and critically the reliable path is
     **one conversation with an admin**, not sustained participation. A
     standing "yes, post it weekly" from three suburban group admins is a
     fixed cost of three messages, and it is exactly the kind of thing
     that converts for a genuinely useful free local resource.

     Needs a short admin-outreach template — `OUTREACH_TEMPLATES.md` §9,
     draftable by the build loop — that leads with the group's interest
     rather than the newsletter's: this is a free, automatically updated
     list of what is happening locally, here is the page, may I post it
     weekly or would you rather post it yourself. Offering the admin the
     option to post it themselves is worth including; it costs nothing
     and converts a gatekeeper into a distributor.

     Sequence it alongside the press pitch rather than behind it. Both
     are the owner's to send, neither blocks the other, and unlike the
     press mention this one is **repeatable and compounding**.

     ✅ **DONE (draft, sending is Ryan's).** Added §9 to
     `OUTREACH_TEMPLATES.md`: leads with the group's own interest (a
     free, always-current local events list), offers the admin the
     option to post it themselves instead of granting posting rights,
     and notes the 70/30-vs-Reddit's-90/10 distinction from item 84 so
     a later pass doesn't re-litigate why this channel is different.
     Sending to the three admins stays with the owner. No code changes;
     copy only, so no test/build cycle to run.

#### P2 (new)

108. ✅ **The signup form promises one town and now delivers four.** Every
     region page carries "The weekly digest, emailed once a week" beside
     that region's own events. A reader on the Palatine page reasonably
     concludes they are subscribing to Palatine. Since item 105 shipped
     yesterday they receive all four towns.

     Item 105 was the right fix — the alternative was a Palatine
     subscriber receiving *only* Mount Prospect, which is strictly worse.
     But it changed what the product delivers without changing what the
     form claims, and the form is where the expectation is set. A
     subscriber whose first issue is not what they thought they signed up
     for is the textbook first-issue unsubscribe, and it will arrive
     alongside the press-pitch traffic rather than before it.

     Cheap and entirely in `config/newsletter.yaml`: make the `detail`
     name the scope plainly — one email on Thursday mornings covering
     all four towns, with the reader's own region first. Then make the
     combined template honour that by **ordering the reader's region
     first** where it can be inferred, or by stating the running order
     plainly where it cannot. Naming the breadth is also the better
     pitch: "everything worth doing within ten miles" is the actual
     promise the brand makes, and a four-town email delivers it where a
     one-town email does not.

     ✅ DONE (2026-09-17). Checked feasibility first: ordering the
     reader's own region first needs to know which town the reader is
     in, and item 105 already established that Buttondown's free-plan
     form has no per-region segmentation — every signup lands on the
     same undifferentiated list regardless of which region page it came
     from. So only the fallback applies: state the running order
     plainly instead of inferring it. `config/newsletter.yaml`'s
     `detail` now reads "One email, Thursday mornings, covering
     Arlington Heights, Des Plaines, Mount Prospect, and Palatine." —
     naming the scope (all four towns) and the fixed order, which
     matches `load_regions()`'s alphabetical sort in
     `scripts/build_digest.py` (the same order the combined email
     itself already renders blocks in), so the promise and the product
     agree. Added a comment at `load_regions()` documenting why that
     order is the one named in the config, so a later change to the
     sort doesn't silently break the claim. Verified against the real
     generated `docs/index.html` and `docs/mount-prospect-60056/index.html`
     that the new copy renders on both the hub and a region page.
     314 tests still pass; no test changes needed since this is
     copy + a comment, not new behavior.

#### P3 (new)

109. skipped — **Syndicating events to Eventbrite/AllEvents/Bandsintown.**
     Mechanically attractive: Eventbrite lists unlimited events free and
     auto-syndicates music events onward to Bandsintown, and those two
     platforms are precisely what currently outranks this site for
     "things to do in Mount Prospect this weekend".

     Rejected, and recorded rather than deleted so a later pass does not
     re-derive it. **This site does not own the events it lists.** They
     belong to the village, the library, the park district and the
     downtown merchants. Submitting another organisation's event to a
     third-party platform under this account misrepresents who is running
     it, is against those platforms' norms, and would be a genuinely bad
     thing to do to the civic sources this business depends on keeping
     good relations with.

     There is also a strategic objection even setting ethics aside: it
     would hand the aggregated civic calendar — the actual moat, the
     thing no competitor has — to the competitors currently outranking
     the site, in a machine-readable form, for free.

     The legitimate version of this idea is the reverse and already
     exists: item 100's subscribable `calendar.ics`, which lets the data
     travel into readers' own calendars rather than into a competitor's
     index.

#### Research pass 2026-09-17 (twenty-sixth pass)

This pass opened by checking whether the first scheduled send had fired.
It had not — and the reason turns out to be the most consequential thing
in this file today, because it means **the newsletter does not go out
when anyone here thinks it does.**

`build-digest.yml` has had `cron: "0 12 * * 1"` — Monday 12:00 UTC — for
weeks. Its three recorded scheduled runs:

| Scheduled | Actually fired | Late by |
|---|---|---|
| 2026-08-31 12:00 UTC | 18:54 UTC | **6h 54m** |
| 2026-09-07 12:00 UTC | 17:27 UTC | **5h 27m** |
| 2026-09-14 12:00 UTC | 17:52 UTC | **5h 52m** |

Three for three, never under five hours. And `send-newsletter.yml`'s
first scheduled run, due 12:00 UTC today, had not started at 12:33.

This is not this repo's bug. GitHub documents schedules as best-effort,
delays cluster at `:00`, and 2026 reporting has them getting worse —
hours late, sometimes dropped. The blunt version from that research:
**GitHub Actions cron is not appropriate for time-sensitive tasks**, and
a weekly newsletter with a researched send window is a time-sensitive
task.

| Angle | Finding | Consequence |
|---|---|---|
| **Actions scheduling** | Measured 5–7h delay, 3/3, in this repo. Moving off `:00` is the standard advice but explicitly "makes no difference when the backlog runs to hours" | The "7am Thursday" send actually lands early afternoon (item 110) |
| **Dropped runs** | High load can drop a scheduled run entirely, producing **no run and therefore no failure** | `build-digest.yml`'s "failure emails the owner" safety net cannot catch a week that never ran (item 111) |
| **Restaurant weeks** | **Chicago Northwest Restaurant Week runs Feb 27 – Mar 8**, across the Northwest suburbs — precisely these four towns. Main Line Today, already this file's model for the send slot, **produces its own** and sells it partly on "email blasts to opt-in subscriber lists" | A dated, in-territory seasonal window, and a glimpse of the mature business (item 112) |
| **Design standards** | Godly: restrained, editorial, typographic, craft over novelty. Awwwards: experimental animation, immersive storytelling | `DESIGN_PRINCIPLES.md` says "restraint" abstractly; these give it a named referent (item 113) |

#### P1 (new)

110. ✅ **Let Buttondown schedule the send, so a late Actions run stops
     mattering.** The owner asked for Thursday mornings. What actually
     happens, on the measured evidence above, is that the job fires
     somewhere between 17:00 and 19:00 UTC — roughly **12pm–2pm
     Chicago** — and the variance is over ninety minutes week to week. A
     newsletter whose send time moves by an hour and a half is one whose
     open rate cannot be read as a trend, which undercuts item 102's
     whole point about watching open frequency.

     The fix is to stop asking GitHub to be punctual and start asking it
     only to be *eventually* on time. Buttondown accepts a scheduled
     status with a send time: create the email with a `publish_date` of
     the next Thursday 07:00 CDT and let **Buttondown** hold and deliver
     it. The workflow then only needs to run *sometime* in a multi-hour
     window beforehand — which is exactly what GitHub reliably provides.
     Move the cron to Wednesday at an offset minute (`37 22 * * 3`), both
     to dodge the `:00` spike and to leave a full night of slack, and a
     six-hour delay becomes harmless instead of defining the send time.

     This also buys something the current design cannot have: a window in
     which a bad issue can be caught. An email scheduled for Thursday
     morning and created Wednesday night sits visible in Buttondown for
     hours before it goes. That is a real safety margin, and it costs
     nothing.

     `send_newsletter.py` already isolates the API shape in one place, so
     this is a status value plus a date field, and the same
     surface-errors-verbatim posture applies — Buttondown's scheduled
     status and date field name are unverified from this sandbox, exactly
     like `X-Buttondown-Live-Dangerously` was, and will announce
     themselves on the first run the same way.

     ✅ DONE (2026-09-17). Added `send.mode: "schedule"` alongside
     `draft`/`send`: it posts `status: "scheduled"` with a `publish_date`
     computed by the new `next_thursday_morning()`, timezone-aware via
     `zoneinfo` so CDT/CST is handled automatically rather than drifting
     an hour every November/March the way the old fixed-UTC cron did.
     `config/newsletter.yaml`'s `send.mode` is now `"schedule"` (this
     week's issue had already gone out via manual dispatch before the
     switch, so nothing was skipped or double-sent), and
     `send-newsletter.yml`'s cron moved exactly as this item specified -
     `37 22 * * 3`, Wednesday night - with the comment rewritten to
     explain why. As flagged above, `publish_date`/`STATUS_SCHEDULED` are
     this session's best-documented guess, not a confirmed API response
     the way `about_to_send`'s header was; the module docstring says so
     explicitly, and the first scheduled run is the real test. 331 tests
     pass, including one that reproduces the exact local-day bug this
     kind of timezone math tends to hide: a UTC timestamp a few hours
     into the next calendar day but still Thursday evening in Chicago,
     verified to still compute a Thursday `now` rather than mis-rolling
     off a UTC-derived Friday. `--dry-run` was run against the real
     current build and correctly prints the actual computed
     `publish_date`.

111. ✅ **A scheduled run that never happens is currently invisible.**
     `build-digest.yml` carries a deliberate comment explaining that a
     failing job emails the owner at no cost, which is a sound safety net
     for a run that *fails*. It cannot catch the failure mode the
     research above describes: a run that is **dropped**, producing no
     job, no conclusion, and no email. The site would quietly serve last
     week's events, and the newsletter would quietly not go out.

     Cheap detection that fits a static site: have the build write its
     completion timestamp into the generated output — `llms.txt` and the
     RSS feed already carry generated-at metadata — and have the *send*
     job refuse to mail a digest whose build timestamp is older than
     about four days, failing loudly rather than mailing stale events.
     That converts a silent non-event into an email the owner already
     gets. It also protects the send independently of item 110.

     ✅ DONE (2026-09-17), with an honest caveat. Added
     `read_build_timestamp()` (parses `docs/feed.xml`'s `<lastBuildDate>`,
     already written fresh on every build - no new metadata needed) and
     `assert_build_is_fresh()`, wired into `main()` right after the built
     email is read, refusing to proceed if the build is older than
     `MAX_BUILD_AGE` (four days). Verified against the real repo: manually
     rewrote `docs/feed.xml`'s timestamp to 5 days old and confirmed
     `send_newsletter.py --dry-run` refuses with a clear message and exit
     code 1, then restored the real file.

     The caveat, worth recording rather than glossing over: `send-
     newsletter.yml` already rebuilds fresh in the same job immediately
     before this check runs, so under the *current* workflow the check
     should never actually trip - it's insurance against a future
     refactor that separates build and send, or a manual run against a
     checkout whose build step didn't run as expected, not a live
     safeguard against send-newsletter.yml's own cron being silently
     dropped. That specific scenario remains genuinely undetectable from
     inside a job that never starts - no code running inside the workflow
     can observe its own absence. Recording this now so a future pass
     doesn't assume the gap is closed and stop looking for a real
     mitigation (an external uptime-style check, or a low-frequency
     watchdog workflow checking the Actions API for the last successful
     run, are the two honest options and neither is cheap enough to add
     opportunistically).

#### P2 (new)

112. ✅ **Start the Chicago Northwest Restaurant Week guide now, and write
     down the seasonal calendar while doing it.** Restaurant Week runs
     **Feb 27 – Mar 8** across the Northwest suburbs — all four regions,
     dated, annual, and exactly the kind of thing residents search for
     and no civic feed carries.

     That is five months out, which is the point. Item 101's
     trick-or-treat page was caught roughly two weeks before its window,
     which worked but only because someone noticed. The systematic fix is
     a short seasonal-windows list in the repo — Halloween (late Sep),
     holiday lights and Santa visits (Nov), Restaurant Week (Jan, for a
     late-Feb event), summer camps (Feb–Mar), farmers markets (May) —
     with the lead time each needs to be published and indexed *before*
     the query peaks. Macaroni KID's seasonal guides were flagged in the
     very first competitor review as the flagship monetisable product;
     twenty-odd passes later they are still being discovered one at a
     time.

     The longer-range note, recorded because it reframes the business
     rather than because it is actionable now: **Main Line Today produces
     its own Restaurant Week**, and sells sponsorship partly on email
     blasts to its opt-in list. This file has cited Main Line Today for
     several passes as the model for *when to send*. It is also a model
     for what this becomes at scale — the publisher that runs the local
     event rather than listing it. Not for this year, and not with one
     subscriber, but worth knowing that the analogue's endgame is
     something other than more listings.

     ✅ DONE (2026-09-17), the calendar half; the guide itself
     **deliberately deferred**, with the reasoning worth keeping. Added
     `SEASONAL_CALENDAR.md` - the systematic fix this item asked for,
     naming all five windows (trick-or-treat, holiday lights/Santa,
     Restaurant Week, summer camps, farmers markets) with lead times and
     current status. Tried to start the Restaurant Week guide itself in
     the same pass and stopped: two separate web searches for the next
     edition's dates returned two different specific date ranges for
     what was presented as the same event, and the source page itself
     couldn't be fetched directly to settle it (this sandbox's egress
     proxy blocks it, same as every other outbound HTTP call here). That
     is exactly the failure mode `SEASONAL_CALENDAR.md` and item 104
     before it both name: a synthesized answer stating a specific date
     with more confidence than the sources support. Publishing a guessed
     date range on a real page would have been worse than not publishing
     one - so the guide is recorded as not-yet-started with a named
     reason, and `SEASONAL_CALENDAR.md`'s own "start by" column (January)
     means there's no urgency lost by waiting for a pass close enough to
     the window to verify the real dates directly from
     chicagonorthwest.com.

     Writing the calendar down surfaced a real, unrelated bug in the
     process: fact-checking the trick-or-treat row against the actual
     site found that `/trick-or-treat/` has been live and in the sitemap
     since item 101 shipped, but **no region or hub page ever linked to
     it** - reachable only by a crawler, never by an actual visitor,
     during the exact window it exists to serve. Fixed the same day
     rather than filed for later: `is_trick_or_treat_season()` in
     `build_digest.py` gates a new footer link (region and hub pages
     both) to September 1 - November 5, past which the page would just
     be a permanent link to an empty "not posted yet" state -
     `DESIGN_PRINCIPLES.md`'s standing question said that doesn't earn
     its place. Verified against the real generated `docs/index.html`
     and `docs/mount-prospect-60056/index.html` that the link renders
     today (in season) with the correct absolute/relative URLs. 338
     tests pass (7 new: season-boundary cases for
     `is_trick_or_treat_season()`, and in-season/out-of-season link
     presence on both `render_region_page()` and `render_hub_page()`).

     🔴 **Correction, 2026-09-22: this item's own "precisely these four
     towns" claim was never actually verified and turns out to be
     wrong.** Checked while fixing an unrelated stale-count bug
     elsewhere in this file (WebSearch, cross-confirmed with a second,
     independent query): Chicago Northwest Restaurant Week's real
     participating towns are **Arlington Heights, Elk Grove Village,
     Itasca, Rolling Meadows, Roselle, Schaumburg, Streamwood, and Wood
     Dale**. Of this site's five regions, only **Arlington Heights** is
     actually on that list — Mount Prospect, Des Plaines, Palatine, and
     Wheeling are not. The original claim was written when this repo
     had exactly four regions and appears to have been a "same general
     area" assumption dressed as a confirmed participant list, the same
     failure mode item 104 and this item's own later paragraph both
     warn against, just not caught at the time it was made.
     `SEASONAL_CALENDAR.md`'s Restaurant Week row is corrected with the
     same finding. Consequence for whenever this guide gets built: it
     is at most an Arlington Heights-only seasonal note, not the
     all-region page this item and `SEASONAL_CALENDAR.md` both assumed
     — worth re-confirming the town list itself, not just the dates,
     against chicagonorthwest.com when that pass happens, since a
     participant roster is exactly the kind of thing that can also
     change year to year.

#### P3 (new)

113. ✅ **Give `DESIGN_PRINCIPLES.md` a named referent instead of an
     adjective.** Item 103 shipped the file on the finding that the
     failure mode for a site like this is accumulation. "Restraint" is
     hard to argue against and equally hard to apply.

     Two showcases make it concrete by disagreeing with each other.
     **Godly** is curated by a small team at 2–3 sites a week and favours
     craft over novelty — restrained, editorial, typographically
     considered. **Awwwards** judges on experimental animation, immersive
     storytelling and technical showcase. Both are "good design"; only
     one is right for a page a parent opens on a phone on a Thursday to
     find out what is on this weekend.

     Name Godly and SiteInspire as the standard the site is held to, and
     name the Awwwards direction as explicitly **not** the target —
     scroll-driven animation, immersive intros, anything that delays the
     first event appearing. That gives a future pass something specific
     to check a proposal against, which an adjective does not. It also
     pre-empts a predictable drift: item 19's `animation-timeline:
     view()` experiment already failed real CI on LCP and TBT once, and
     the next such idea will arrive dressed as modern.

     ✅ DONE (2026-09-17). Added a "The named referent" section to
     `DESIGN_PRINCIPLES.md`, naming Godly and SiteInspire as the
     standard and Awwwards explicitly as not the target, with the
     concrete rule that follows (no scroll-driven animation, no
     immersive intro, nothing that delays the first event appearing) and
     the item 19 precedent as evidence this isn't hypothetical caution.
     Docs-only change; 331 tests still pass, no build affected.

#### Research pass 2026-09-17 (twenty-seventh pass)

**Today's newsletter never went out.** Not late — never. The previous
pass predicted it would land early afternoon; that was wrong, and the
reason is worth the space because it is a trap this repo will fall into
again.

| Time (UTC) | What happened |
|---|---|
| ~02:00 | `cron: "0 12 * * 4"` pushed to `main` |
| 12:00 | Scheduled fire time — **no run recorded** |
| 13:01 | Item 110 shipped, replacing it with `cron: "37 22 * * 3"` |
| 18:33 | `send-newsletter.yml` schedule-event runs: **total_count 0** |

Two explanations fit, and the honest position is that this pass cannot
distinguish them: either the 12:00 run was sitting in GitHub's backlog
(consistent with the measured 5–7h delays) and was **discarded when the
workflow's cron changed out from under it at 13:01**, or a newly-added
cron had not activated yet and the first occurrence was simply skipped.
Both are documented GitHub behaviours.

Either way the lesson is the same and it is uncomfortable: **the fix for
unreliable scheduling ate the send it was meant to protect**, and nothing
anywhere reported a problem. No run, no failure, no email — exactly the
blind spot item 111 described, arriving the same day it was filed. The
next send is now Wednesday 2026-09-23 22:37 UTC. That is a **six-day
gap** in a weekly newsletter, and the only reason it is known is that
this pass went looking.

| Angle | Finding | Consequence |
|---|---|---|
| **Changing a cron** | Editing a scheduled workflow's cron drops occurrences pending under the old one; a newly-added cron may also skip its first fire | Schedule changes need a manual run to cover the gap (item 114) |
| **ICS feeds as a source** | Feeds can carry descriptions, locations and organiser notes beyond what a site displays, and a public subscription URL is unauthenticated | Item 100 must whitelist fields, not pass through (item 115) |
| **Local event SEO** | Ranking pages reinforce geography with **neighbourhood, landmark and venue names**, not just the town | This site's venue mentions are a **byproduct of whichever events fetched this week** (item 116) |

#### P1 (new)

114. ✅ **Nothing confirms a send happened, so a missed week is invisible.**
     Item 111 proposed a staleness guard on the *build* timestamp, which
     is the right instinct aimed at the wrong artifact. Today proves the
     gap is on the other side: the build ran fine all day; it was the
     **send** that silently did not occur, and no guard on freshness
     would have caught it, because there was no send job in which to run
     a guard.

     What is missing is a positive record. On every successful send,
     append to `data/send_history.json`: timestamp, subject line, the
     Buttondown id returned, and the region/mode. That file is small,
     diffable, committed like `data/source_health.json` already is, and
     it answers three questions nothing currently can — did this week go
     out, when did it actually go out (item 110's whole premise), and
     how many issues have shipped. The last one stops being trivia the
     moment a sponsor conversation starts: "we have published N
     consecutive weekly issues" is a claim, and right now it could not be
     substantiated from the repo.

     Pair it with the cheap alarm: a second scheduled workflow, on a
     different day and an offset minute, that fails if the newest entry
     is more than nine days old. A failing job emails the owner — the
     same mechanism `build-digest.yml` already relies on, pointed at the
     failure mode that actually occurred.

     And an operational rule worth writing into the workflow comment:
     **after changing the cron, trigger a manual run.** The schedule
     change is exactly when a fire gets dropped, and that is precisely
     when nobody is watching for it.

     ✅ DONE (2026-09-17). `send_newsletter.py` gained `load_send_history()`/
     `record_send()`/`save_send_history()`, wired into `main()` right
     after a successful (2xx) `post_to_buttondown()` response - a
     positive record can only mean the API actually accepted it, not
     merely that this script attempted it. `scripts/check_send_history.py`
     is the alarm: it finds the most recent `send`/`schedule` record
     (deliberately not `draft` - a standing draft nobody sent isn't
     evidence the newsletter went out) and fails if it's missing or
     older than nine days. A new workflow, `send-watchdog.yml`, runs it
     on Sunday 15:13 UTC - a different day and offset minute than both
     `build-digest.yml` (Monday 12:00) and `send-newsletter.yml`
     (Wednesday 22:37), on purpose: a watchdog sharing a schedule with
     the thing it watches would miss exactly the failure mode that
     motivated it. Three days after a normal Thursday send, so a missed
     one is caught with about a week of margin before the next is due.

     Seeded `data/send_history.json` with one real record rather than
     leaving it empty: the actual successful live send from earlier
     today (workflow run `35176614362`, Buttondown id
     `em_5hgyjgfytf8hws9xxpw6b0fesk`, already verified against real
     GitHub Actions logs and recorded in this file's own Needs Ryan
     section) - a backfill of an already-confirmed fact, not a guess,
     and it means the watchdog starts meaningful instead of in a
     permanent false-failure state for a send that genuinely happened
     before this tracking existed. Confirmed with a real run:
     `check_send_history.py` against the seeded file reports "OK: last
     delivery 15h55m ago" and exits 0; verified `--dry-run` leaves the
     file's checksum unchanged (no record written without a real send).
     354 tests pass. The operational rule item 114 asked for - trigger
     a manual run after changing a cron - is recorded here rather than
     in a workflow comment, since it's a process note for whoever edits
     the schedule next, human or otherwise, and this file is where that
     history already lives.

     **Self-correction, same day.** The fix above shipped with a real
     bug: `send-newsletter.yml` had `permissions: contents: read` and
     no commit step, so `send_newsletter.py` writing
     `data/send_history.json` on the ephemeral runner never made it
     back to the repo - the whole positive-record mechanism would have
     silently done nothing in production the first time it actually
     ran, while every local test and manual check kept passing, because
     none of them exercised the missing commit step. Caught by
     rereading the workflow itself rather than trusting that "tests
     pass" meant "the fix works end to end" - the same gap that let
     item 110's cron change eat a send in the first place. Fixed:
     `permissions: contents: write`, and a `Commit send history` step
     mirroring `build-digest.yml`'s own (`if: always()`, same
     reasoning: don't let an unrelated later failure withhold a record
     that did get written). `send-watchdog.yml` stays `contents: read`
     - it only ever reads the file.

     **Live-verified the workflow itself, not just the script, 2026-09-20
     - the same gap that let item 13's bug hide.** Every check above ran
     `check_send_history.py` locally against a seeded file; none of them
     actually exercised `send-watchdog.yml` running on GitHub's own
     infrastructure, with its own dependency install and its own
     permissions, the exact category of gap that let item 13's PR-
     creation failure go unnoticed until this session actually fired it.
     `send-watchdog.yml` had **zero runs ever** in this repo's Actions
     history, and its first real scheduled fire (Sunday 15:13 UTC) hadn't
     happened yet today - so rather than wait and hope, manually
     triggered it via its `workflow_dispatch` trigger (run
     `35490203761`). Every step succeeded, including "Check the
     newsletter has actually gone out recently" - confirmed real, not
     assumed, ahead of its first live scheduled run.

115. ✅ **Item 100's `calendar.ics` must whitelist fields, not pass feeds
     through — decide this before it ships, not after.** The plan is to
     republish the aggregated events as a subscribable calendar. The
     inputs are other organisations' ICS feeds: District 57, the park
     district, the library.

     A consumed feed can carry materially more than the title this site
     displays — full descriptions, room-level locations, organiser or
     contact names, internal notes. The site's HTML only ever renders the
     truncated fields it chose, so none of that is visible today. A
     naive `calendar.ics` that forwards the parsed event wholesale would
     publish all of it, at a **public, unauthenticated URL** that anyone
     can subscribe to and read in full.

     Nothing here is a leak of anything secret — these are public feeds.
     But "public on the district's own calendar page" and "republished
     by a commercial aggregator in a form anyone can subscribe to" are
     not the same thing, and this business depends on staying welcome
     with exactly these civic sources. The rule should be explicit and
     narrow: emit only `SUMMARY`, `DTSTART`, `DTEND`, `LOCATION`, `URL`
     and a stable `UID`, built from the same truncated fields the page
     already shows, and **never** copy through `DESCRIPTION`,
     `ATTENDEE`, `ORGANIZER` or `X-` properties from the source. Include
     the source link in `URL` so the feed drives traffic back rather than
     substituting for it — the attribution norm this site already
     follows in HTML.

     ✅ VERIFIED (2026-09-17) - the worry doesn't describe the shipped
     code, checked directly rather than assumed. Two things make it
     already safe: (1) `fetch_ics()` in `fetchers.py` never extracts
     `ORGANIZER`/`ATTENDEE`/`LOCATION`/`X-` properties into the internal
     event dict in the first place - only `SUMMARY`, `DESCRIPTION`,
     `URL` and `DTSTART` are parsed at all, so there is nothing for
     `build_region_calendar_ics()` to copy through even if it tried; (2)
     `event["detail"]` (emitted as ICS `DESCRIPTION`) is truncated to
     `DETAIL_MAX_LEN` (160 chars) at construction time in `main()`,
     before `build_region_calendar_ics()` ever sees it, and
     `region.html.j2` renders that exact same already-truncated string
     with no further truncation - so the HTML page and the ICS feed
     show byte-identical text, not a fuller one. Added two regression
     tests to guard both halves against silent regression:
     `test_fetch_ics_never_captures_organizer_attendee_or_x_properties`
     (fetchers.py) and
     `test_build_region_calendar_ics_never_emits_organizer_attendee_or_x_properties`
     (build_digest.py, feeding the function a deliberately over-stuffed
     event dict to prove it's a field allowlist, not a passthrough,
     regardless of what a future change to the event shape might add).
     One real gap against the item's own wish list, left alone rather
     than added speculatively: `LOCATION` is never emitted, since
     `fetch_ics()` doesn't parse it from source feeds at all - worth
     picking up only if a real source's calendar actually carries it
     and a person wants it in the subscription; not blocking, since the
     leak risk this item raised is what mattered before ship, and that
     risk was never real.

#### P2 (new)

116. ✅ **The site's geographic signal is as volatile as this week's event
     list.** Local event pages rank on naming neighbourhoods, landmarks
     and venues, not just the town. Counting on the live Mount Prospect
     page: "Randhurst" appears 5 times, "Busse" 9, "Emerson" 11 —
     and "Melas" and "Lions Park" zero, despite both being real Mount
     Prospect venues that have carried events in this very digest.

     The mentions that exist are **accidents of what fetched this week**.
     Next Thursday the fixtures change and Randhurst may vanish
     entirely. That is an unstable entity signal for a domain trying to
     establish that it is *about* Mount Prospect, and it is exactly the
     kind of thing item 98's retraction said to redirect the AI-citation
     effort toward — entity clarity, which is winnable, rather than
     out-ranking Eventbrite, which is not.

     The `<meta name="description">` is currently "Village news, library
     events, and park district programs" — true, generic, and naming no
     place at all. Fix both halves together, since they are the same
     sentence: give each region a short, stable, hand-written line in its
     YAML naming its actual places (Randhurst Village, Melas Park, Lions
     Park, downtown Emerson & Busse, the library, the park district), use
     it as the meta description, and render it as the one-line "what's in
     here" statement above the listings. That statement was recommended
     in the **first** competitor review, has never shipped, and is the
     rare change that serves a human reader and a crawler with the same
     words.

     Guard it against drift: a test asserting each region config carries
     the line and that it names at least two venues. Volatility is the
     defect; a config field the build cannot silently drop is the fix.

     ✅ DONE (2026-09-17). Rewrote each region's own `tagline` field
     (not a new parallel field - `tagline` was already wired to exactly
     the two places this item asked to fix, the meta description via
     `page_description` and the on-page "Issue for [date] — ..."
     statement in `region.html.j2`, plus two more it hadn't named: the
     hub page's region cards and each `llms.txt` region line) rather
     than adding a second field that would need to stay in sync with
     it. Every named venue is one already independently sourced
     elsewhere in that same region's config - a configured source
     (Randhurst Village), an annual event's real location (Emerson &
     Busse, Lake Park, Harmony Park, Downtown Palatine), or a WebSearch-
     verified civic landmark from item 104 (the Palatine Train Station
     farmers' market lot) - not invented for this. "Melas" and "Lions
     Park" for Mount Prospect are exactly the two this item itself
     already verified as real by counting them live on the page; used
     directly rather than re-verified from this sandbox, where the
     network is blocked anyway.

     Added the drift guard exactly as specified:
     `test_every_region_tagline_names_at_least_two_real_venues` loads
     the real `config/regions/*.yaml` files (not fixtures) and asserts
     each tagline both differs from the old generic sentence and names
     at least two of a hand-curated, per-region venue list. Verified
     against the real generated site, not just the test: `docs/index.html`'s
     hub cards, `docs/mount-prospect-60056/index.html`'s meta
     description and on-page "Issue for ..." line, and `docs/llms.txt`'s
     region entries all correctly show the new venue-naming text after
     a real `build_digest.py` run. 355 tests pass.

117. ✅ DONE (2026-09-17). **Dependabot's first batch — 9 version-update
     PRs, all merged.** `.github/dependabot.yml` (added this same day)
     opened PRs #146–#154 within hours: three GitHub Actions bumps
     (`setup-python` 5→7, `github-script` 7→9, `create-pull-request`
     6→8), one more Actions bump found alongside them (`checkout` 4→7,
     PR #154) plus four pip lower-bound bumps (`pillow` →12.3.0,
     `setup-node` 4→7, `jinja2` →3.1.6, `pyyaml` →6.0.3, `requests`
     →2.34.2). Checked each one's "Tests" GitHub Actions run actually
     passed on its head SHA via `actions_list`/CI status before merging
     — not just "Dependabot opened it" — and specifically re-verified
     that PR #150's target, `actions/setup-node`, is a genuine dependency
     (`tests.yml` uses it for `npm ci` / `npx lhci autorun`, the
     Lighthouse CI performance-budget check) rather than a stray
     leftover, before merging it. Squash-merged all 9 with no human
     review, per this file's working agreement.

     Two of the nine (#151 pyyaml, #153 requests) returned a `405
     Pull Request has merge conflicts` error on first merge attempt,
     right after #149 and #152 had each just changed the same
     `requirements.txt` line context. Rather than manually rebasing a
     bot-owned branch, re-checked each PR minutes later: both now
     reported `mergeable_state: "unstable"` (checks running, not a real
     conflict) and merged cleanly on retry — GitHub's own mergeability
     computation lagging behind the base branch update, not an actual
     content conflict. Worth remembering: a `405` on a Dependabot PR
     right after a sibling PR touching the same file merged is worth a
     short retry before assuming a real conflict needs resolving.

     After all 9 merged, reset the local branch onto the new `origin/main`,
     reinstalled `requirements.txt` (`--ignore-installed PyYAML`, since
     this sandbox's PyYAML is Debian-managed and plain `pip install`
     can't uninstall it), and reran the full suite against the bumped
     versions: 355 tests pass, and a real `build_digest.py` run
     completes with exit 0 (the sandbox's proxy blocks every external
     fetcher host here regardless of dependency versions, so those
     warnings are pre-existing sandbox noise, not a regression from the
     bumps).

#### Research pass 2026-09-18 (twenty-eighth pass)

Two overdue re-checks, and one of them **corrects something this file has
been asserting for six passes.**

| Angle | Finding | Consequence |
|---|---|---|
| **Sponsorship thresholds** | Direct-sold B2C newsletter sponsorship conventionally wants **10,000–20,000 subscribers**. But also: "a small, high-quality community often attracts more sponsorship than a huge list with lukewarm engagement", and the standard opener is a **discounted rate for the first few** | Those thresholds price a **list**. Two of the four tiers price the **site**, which is live now (item 118) |
| **Google structured data, 2026** | **FAQ rich results were deprecated in May 2026.** Rich-result eligibility also narrowed to pages where schema describes the **primary content purpose** | 16 guide pages carry `FAQPage` for a rich result that no longer exists (item 120) |
| **Event schema placement** | Counted on the live build: `Event` appears on **13** pages — region, `this-weekend`, `free` — and **zero** on the hub | Already correct under the new "primary content purpose" rule. Confirmed, not a defect |

#### P1 (new)

118. ✅ **Correct the monetisation gate: two of the four tiers were never
     waiting on subscribers.** Item 95 ended with "until there is an
     audience number to put next to the price, no tier is sellable at any
     price", and items 94/96/107 have repeated that framing since. It is
     half wrong, and the half that is wrong has been keeping the whole
     revenue side parked.

     The conventional thresholds — 10,000–20,000 subscribers for direct
     B2C sponsorship — price **a list**: an ad slot, measured in opens
     and clicks. Read `BUSINESS_PLAN.md`'s tiers against that and they
     split cleanly:

     - **Weekly Spot ($50/wk)** and **Event Promo ($20)** are list
       products. Top-of-newsletter placement, judged on who sees it.
       These genuinely do need an audience, and the framing holds.
     - **Annual Partner ($1,200/yr)** and **Neighborhood Authority
       ($5,000/yr)** are almost entirely **site** products: a permanent
       directory listing, a seasonal-guide spotlight, a live SEO
       backlink, priority Editor's Pick. Not one of those is delivered by
       an email. They are delivered by a live, indexed, four-region site
       with GSC verified, a sitemap submitted, and a trick-or-treat page
       positioned for the Q4 query — all of which exist **today**.

     So the honest statement is narrower and much more useful: the
     **newsletter** tiers are audience-gated; the **membership** tiers
     are traffic-gated, and traffic is a thing the site can evidence now
     rather than in six months. A local business buying an Annual
     Partnership is buying a backlink and a directory listing on the only
     site that aggregates their village's civic calendar — a proposition
     that does not improve much at 10,000 subscribers and does not fail
     at one.

     Concretely: `SPONSOR_KIT.md` should stop leading with audience and
     lead per-tier with what actually delivers that tier — search
     presence and page traffic for the memberships, reach for the weekly
     spot — and say plainly that the newsletter is young. Understating a
     new list is credible; quietly implying it is large is the thing that
     ends a local relationship permanently.

     ✅ DONE (2026-09-18). Rewrote `SPONSOR_KIT.md`'s "Reach & retention"
     section to say the split explicitly (list-gated newsletter tiers vs.
     traffic-gated membership tiers) rather than one blanket audience
     caveat covering all four, and added a "Gated by" column to the
     pricing table so the split is visible at a glance, not just in prose.
     Didn't touch `BUSINESS_PLAN.md`'s tier table — that's the internal
     planning doc this item's fix is *about* correcting the downstream
     effect of (items 94/96/107's repeated "no tier is sellable" framing),
     not the thing a prospect reads; `SPONSOR_KIT.md` and the live
     `/sponsor` page are. Added the same `gated_by` label to each
     `SPONSOR_TIERS` entry (`scripts/build_digest.py`) and rendered it on
     each tier card in `templates/sponsor.html.j2`, so the live page
     carries the identical split, not just the markdown. Verified
     against the real generated site, not just the source: `docs/sponsor/index.html`'s
     tier cards each show a "Gated by:" label matching `SPONSOR_KIT.md`'s
     table after a real `build_digest.py` run.

119. ✅ **Offer a founding-partner rate, and say why it exists.** The
     standard opener for a first sponsor is a discounted rate, and it
     solves a problem this business specifically has: the first sponsor
     takes all the risk of an unproven product, and has no comparable to
     price against.

     Make it explicit and finite — the first three businesses per region
     get a founding rate held for their first two years, in exchange for
     a testimonial and permission to name them as a founding partner.
     Both sides of that trade matter. The discount is honest compensation
     for buying something unproven, and the testimonial plus the named
     logo is the **social proof the fifth conversation needs and the
     first cannot have**. A local business owner deciding whether this is
     real will be convinced by two neighbours already in it far more than
     by a subscriber count.

     Worth being disciplined about the number rather than inventing one:
     the tiers are already researched, so a founding rate should be a
     stated percentage off the published price with an end date, not a
     new tier and not an open-ended negotiation. A permanently negotiable
     price is how a $1,200 membership becomes a $300 one.

     ✅ DONE (2026-09-18), shipped with item 118. **25% off Annual Partner
     or Neighborhood Authority, first 3 businesses per region, held for
     their first two years, for a testimonial + naming permission** —
     added to `SPONSOR_KIT.md`'s new "Founding partner rate" section and
     to the live `/sponsor` page's pricing note (`templates/sponsor.html.j2`),
     so a prospect sees the identical offer whether they got the outreach
     doc or found the page directly. A stated percentage with an end date
     ("until a region's third spot is filled"), not an open-ended
     negotiation, exactly as asked. No live per-region counter yet —
     there are zero real sponsors today, so every region's three founding
     spots are honestly still open; a real counter is future work once
     the first sponsor signs. `test_render_sponsor_page_states_the_founding_partner_rate`
     guards the live page's copy. 359 tests pass; verified live in
     `docs/sponsor/index.html` after a real `build_digest.py` run.

#### P2 (new)

120. ✅ **`FAQPage` is the second retracted search bet — keep the markup,
     stop counting it, and make that a standing rule.** Google
     **deprecated FAQ rich results in May 2026**. The build emits
     `FAQPage` on 16 guide pages, added under item 22 as part of the
     GEO/SEO effort. Those pages will not get the rich result they were
     marked up for.

     The recommendation is exactly item 98's, for the same reasons:
     `build_guide_faq()` generates it from real content at zero marginal
     cost, the answers are genuine and useful to a reader, and structured
     content still helps machine extraction even where it earns no SERP
     feature. **Keep it; stop treating it as progress.**

     The other half of the 2026 change is worth confirming rather than
     fixing: eligibility narrowed to pages where the schema describes the
     page's **primary content purpose**, and supplementary schema on
     off-topic sections no longer qualifies. Counted on the live build,
     `Event` appears on 13 pages — region pages, `this-weekend`, `free` —
     and on **zero** hub pages. That is already the right shape. Nothing
     to change; worth a test asserting it stays that way, because the
     tempting future change (Event markup on the hub to "help the home
     page rank") is now actively counter-productive.

     The pattern is the point. `llms.txt` (item 98) and `FAQPage` are the
     **second and third** search-surface bets this file has had to walk
     back inside a month — the first being item 22's overstated AI
     Overview reach. Worth a line in the working agreements: **do not
     count an unverified rich-result or AI-surface feature as shipped
     progress.** Mark it speculative when added, and re-check it each
     quarter. The cost of being wrong is small; the cost of believing a
     dead channel is working is a backlog that looks healthier than it is.

     ✅ DONE (2026-09-18). Left `build_guide_faq()`/`build_faq_json_ld()`
     untouched — this item's own recommendation was to keep the markup,
     not remove it, since it's real content at zero marginal cost. Added
     the standing working agreement below verbatim. Added the guard test
     this item asked for, at the level that actually matters: not a count
     ("13 pages") that drifts with every new guide or region, but a
     structural assertion that neither hub-level template can ever emit
     Event schema, regardless of input —
     `test_render_hub_page_never_embeds_event_json_ld` and
     `test_render_weekend_hub_page_never_embeds_event_json_ld`, both
     passing real events/region data through `render_hub_page()` and
     `render_weekend_hub_page()` and asserting `"@type": "Event"` never
     appears in the output. Re-verified the count itself too, against
     this sandbox's own (network-blocked, lower-volume) build: `Event`
     appears on 11 region-scoped pages, 0 on `docs/index.html` or
     `docs/this-weekend/index.html` — same shape as the twenty-eighth
     pass found on the live site, just fewer events fetched here. 359
     tests pass.

#### P2 (new)

121. ✅ **DONE (build loop's own pick, not from a research pass — the
     backlog above is exhausted or Ryan-blocked, so this hour went
     looking at code not recently reviewed instead).** **Four real
     substring false positives in `scripts/tagging.py`'s heuristic
     tagger, found by deliberately trying plausible real event titles
     against `infer_tags()`, not by reading the code and guessing.**
     Four of the unpadded keywords are literal prefixes of common,
     unrelated words: `"kid"` ⊂ "Kidney" (a "Kidney Foundation Walk"
     tagged kid-friendly), `"pup"` ⊂ "puppet"/"puppetry" (a library
     puppet show — a genuinely common, non-dog kids' program — tagged
     dog-friendly), `"hall"` ⊂ "Halloween" (a Halloween parade, usually
     outdoor, tagged indoor), and `"art"` ⊂ "party"/"smart"/"start"/
     "apartment"/"heart"/"chart" (a plain "Neighborhood Block Party"
     tagged arts & culture). This is the exact same bug class the file
     already fixed once for `"teen"`/`"tween"` (padded to avoid matching
     inside "thirTEEN"/"beTWEEN") — that fix just never got generalized
     to the other short, prefix-prone keywords sitting right next to it.

     Fixed with the same padding idiom already established in the file
     rather than introducing regex for a few keywords: `"kid"` → `" kid
     "`, `"pup"` → `" pup "`, `"hall"` → `" hall "` (all whole-word,
     since each has a real word that *extends* it and must be excluded
     on both sides), and `"art"` → `" art"` (leading space only, since
     "arts"/"artist"/"artistic"/"artwork" are legitimate extensions that
     must still match — only words *preceded* by another letter, like
     "p-art-y", were ever the problem). Confirmed each fix doesn't cost
     real recall: "Kids' Fun Run", "Bring your pup", "Village Hall
     Budget Meeting", "Art in the Park", and "Arts and Crafts Festival"
     all still tag correctly, since the already-separate plural/adjacent
     keywords (`"kids"`, `"puppy"`) and the leading-space-only rule cover
     the common real phrasing. 8 new regression tests, one pair per
     keyword (false-positive-excluded + legitimate-match-preserved). 367
     tests pass; a real `build_digest.py` run still exits 0.

#### P1 (new)

122. ✅ **DONE (build loop's own pick — a security review of
     `scripts/parse_event_submission.py`, the one file in this repo that
     parses public, attacker-controlled input, since it hadn't been
     looked at with that lens before).** **A real field-boundary
     injection, demonstrated with an actual crafted submission before
     fixing it, not assumed from reading the code.** The Issue Form
     (`.github/ISSUE_TEMPLATE/event-submission.yml`) has one multi-line
     field — "Short description" (`type: textarea`); `title`/`url`/`date`
     are single-line `input` fields that can't contain a newline at all.
     `_extract_field()` finds a label's `### <Label>` heading by
     searching the *whole* rendered body from the start, every time - so
     a submitter who types a line starting with `### Link` inside their
     own description gets that fake heading found *first*, before the
     real one GitHub renders later in the body, silently substituting
     whatever URL they put there for the real Link field's answer.
     Confirmed exploitable with a real crafted body: the parsed `url`
     came back as the injected `http://attacker.example/phish`, not the
     genuine `https://real-organizer.example/...` sitting under the
     actual "### Link" heading a few lines later.

     This isn't a bypass of anything downstream (`build_digest.py`
     autoescapes template output; the URL scheme allowlist from an
     earlier pass still applies) - the real damage is to the **specific**
     security boundary this file names as its whole defense: "a person
     always reviews before it goes live." GitHub renders a heading typed
     inside a textarea identically to a real field heading, so the
     rendered issue a reviewer looks at can visually show two "Link"
     sections with no indication which one actually got written to the
     region file - the injection attacks the reviewer's trust in what
     they're looking at, not the code path around them.

     Fixed with a property GitHub's own rendering guarantees rather than
     trying to parse markdown headings more cleverly: a real submission
     always renders **exactly** `len(_FIELD_LABELS)` (5) `### ` headings,
     one per configured form field, even an unanswered optional one
     (`_No response_` still gets its own heading). `_assert_no_injected_headings()`
     counts them and raises `SubmissionError` on any mismatch, before any
     field is extracted - a submission with an injected extra heading
     gets rejected outright with a message telling the submitter to
     remove any line starting with `###`, rather than silently mis-
     parsed. 2 new regression tests: the exact crafted-injection body
     above is rejected, and a legitimate real multi-line description (no
     injected heading, just an ordinary line break) still parses
     normally - the fix counts headings, not newlines. 369 tests pass; a
     real `build_digest.py` run still exits 0.

123. ✅ **DONE (build loop's own pick — re-running item 62's real
     accessibility audit, since several UI changes have shipped since
     it last ran, plus closing a real gap in what it covered).**
     `axe-core` via Playwright (same tooling item 62 used, still
     available from this sandbox) against a real local build, this
     time across **10** page types (the original 8, plus `/about/` and
     `/trick-or-treat/`, both shipped after item 62's audit and never
     checked): **0 violations everywhere**, including on the pages
     changed most recently (`/sponsor/`'s new "Gated by" labels and
     founding-partner note from items 118/119, `/mount-prospect-60056/`'s
     rewritten itinerary-tray JS from the DOM-XSS fix). Item 62's fixes
     have held.

     Closed a real coverage gap while at it, not just re-running the
     same check: axe's default `page.new_page()` renders in the
     browser's **light** color scheme, so item 62's audit never actually
     exercised any of this site's dark-mode CSS - a genuine blind spot,
     since `color-contrast` was exactly the violation type item 62 found
     and fixed. Re-ran the same 10 pages with Playwright's
     `color_scheme="dark"` explicitly: also **0 violations**. Manually
     spot-checked the specific new small-text elements most likely to
     regress contrast first - `.gated-by`'s `--muted` on `--card` comes
     to 5.16:1 light / 6.99:1 dark, both clearing AA's 4.5:1 floor for
     text this size with room to spare.

     Nothing to fix, so nothing shipped except this record - matching
     item 120's own working agreement about not overclaiming, this
     records a real negative result (checked, clean) rather than a
     fabricated positive one. Worth keeping this pairing (light **and**
     dark) in mind for the next audit, since a plain re-run of item 62's
     exact script would have kept missing dark mode indefinitely.

#### Research pass 2026-09-18 (twenty-ninth pass)

This pass looked at the two local publications item 77 names as press
targets, and found a competitor sitting in both of them. The headline
finding is uncomfortable and overdue: **"nobody is doing this" is no
longer true at the newsletter level**, and this file has been repeating
it since the first competitor review.

| Angle | Finding | Consequence |
|---|---|---|
| **PatchAM** | Auto-generates a local newsletter for **any US ZIP**, including 60056, generated on demand "even if you are the only subscriber". 14,000 towns, ~1M subscribers on the product. Explicitly targeting suburbs | A competitor is already in this market without having entered it (item 124) |
| **Patch's sources** | "Aggregation, automated event calendars, and **posts from Nextdoor**." CEO: a utility, not journalism | The moat survives — but it is the *specific civic feeds*, not the idea (item 124) |
| **Patch's revenue** | A **3–10% cut** of sponsorships, memberships and **community-calendar listings** | Independent evidence that local calendar listings monetise — supports item 118's tier split |
| **Journal & Topics** | Runs a submission-based Event Calendar covering Mount Prospect and Palatine | The #1 pending owner action pitches a competitor (item 125) |
| **Source transparency** | The three civic sources appear on the region page only as **section headings**; nothing states where the data comes from or why that matters | The one durable differentiator is invisible to a reader (item 126) |

#### P1 (new)

124. ✅ **Re-state the moat honestly: it is the civic feeds, not the idea.**
     The competitors table has carried Patch since the first review as
     "hyperlocal news + community calendar" whose worth-stealing was
     user-submitted events and a business directory. That is badly out of
     date. PatchAM now builds a newsletter for **practically any ZIP in
     the country**, on demand, including this one — meaning the
     "aggregated local events newsletter for Mount Prospect" product
     exists already and required nobody to decide to build it.

     The differentiation is still real, and it is worth being precise
     because the imprecise version will lose an argument with a reporter
     or a sponsor. Patch's newsletters are assembled from **aggregation,
     generic automated event calendars, and Nextdoor posts**. This site
     is assembled from **hand-verified feed URLs for the village, the
     public library and the park district** of each specific town — the
     three sources `BUSINESS_PLAN.md` identified as where a family
     actually finds the weekend, and the ones a national template
     applied to 14,000 towns does not have. Patch's own CEO describes the
     product as a utility rather than journalism; the honest read is that
     it is *broad and shallow by design*, and shallow is the opening.

     So the claim changes from "no one aggregates this" — false — to "no
     one aggregates **these**, and the generic approach demonstrably does
     not reach them." That is narrower, defensible, and checkable. Two
     concrete consequences:

     - Update the competitors table entry and anywhere the file leans on
       the unqualified version, including `BUSINESS_PLAN.md`'s "currently
       has no single aggregator" line, which is now wrong as written.
     - **Both the press pitch and `SPONSOR_KIT.md` need an answer to
       "isn't this just Patch?"** Neither has one today, and it is the
       first question an informed local reporter or a business owner who
       already gets the Patch email will ask.

     Worth noting what this does *not* change: Patch taking a 3–10% cut
     of community-calendar listings is independent evidence that this
     category monetises locally, which strengthens item 118 rather than
     weakening it.

     ✅ DONE (2026-09-18). Corrected `BUSINESS_PLAN.md`'s "currently has
     no single aggregator" line to the narrower, checkable claim (no
     aggregator built from hand-verified village/library/park-district
     feeds specifically), with a pointer back here rather than silently
     rewriting history. Replaced the stale original "Patch" competitors-
     table row (which predated PatchAM's auto-generation and was flatly
     out of date) with the twenty-eighth pass's re-assessed row, rather
     than leaving both side by side contradicting each other. Added
     "Isn't this just Patch?" as its own section in `SPONSOR_KIT.md`
     (same objection-handling genre as the existing "Compared to
     Nextdoor and Meta geo-ads" section) and folded the same answer into
     the press-pitch email itself (`OUTREACH_TEMPLATES.md` §7, alongside
     item 125's changes below) - both now say what actually differs
     (hand-verified per-town civic feeds vs. generic aggregation +
     Nextdoor) instead of the now-false "no one else aggregates this."
     369 tests pass; no code changed, verified the new copy renders via
     a real `build_digest.py` run.

125. ✅ **Pitch the Daily Herald first, not Journal & Topics — they are not
     interchangeable.** Item 77 has named both for five passes as though
     picking either were a coin flip. They are not. **Journal & Topics
     runs its own Event Calendar with a "Submit Your Event" form**,
     listing park district, library and history centre events across a
     coverage area that includes Mount Prospect and Palatine. Pitching
     them a story about a site that aggregates park district, library and
     village events is pitching a publication its own competitor.

     That is not automatically fatal — a local paper can still find a
     resident's automation project a good story — but it is a materially
     harder sell than the pitch template assumes, and it should not be
     the first attempt. The **Daily Herald** covers Mount Prospect as
     community news across a regional operation; a "local parent
     automates the village calendar" story there competes with nothing
     they sell.

     Two changes to `OUTREACH_TEMPLATES.md` §7: order the targets
     explicitly with the reason, and add a line the current draft lacks —
     what the site does that a submission-based calendar structurally
     cannot. A submitted calendar lists what an organiser remembered to
     submit; an aggregated one lists what is actually published. That
     difference is the story, it is true, and it is also the polite way
     to raise the overlap rather than hope nobody notices.

     If Journal & Topics is approached later, the honest framing is
     complementary rather than competitive, and there is a real version
     of that: their calendar is submission-based and regional, this is
     automated and town-specific. Item 109's rule still binds — do not
     submit other organisations' events to their form.

     ✅ DONE (2026-09-18). `OUTREACH_TEMPLATES.md` §7 now opens with the
     ordering rationale explicitly (Daily Herald first, why; Journal &
     Topics later, framed as complementary if approached at all) instead
     of naming both as if picking were a coin flip. Added the exact line
     this item asked for to the pitch email body itself - "pulled
     straight from each town's own feeds rather than a submission form -
     so it lists what's actually published, not just what an organiser
     remembered to submit" - replacing the email's own overclaiming "No
     one else aggregates all of those together for this area" line,
     which item 124's finding made false as written. Updated the "Needs
     Ryan" table's press-pitch row to match the new ordering so a future
     pass doesn't read it as still-ambiguous. Sending is still a human
     action (unchanged from item 77) - this shipped the corrected
     template, not a send.

#### P2 (new)

126. ✅ **Say where the data comes from, on the page.** Counted on the live
     build: "Village of Mount Prospect", "Mount Prospect Public Library"
     and "Mount Prospect Park District" each appear three times on the
     region page — entirely as **section headings**. Nothing anywhere
     states that this page exists *because* those three feeds are pulled
     automatically several times a week, and nothing tells a reader why
     that is different from any other events page they have seen.

     Item 124 makes this urgent rather than nice: the differentiator
     against a nationally-generated newsletter is provenance, and
     provenance is currently implicit. A reader who already receives the
     Patch email for 60056 has no way to tell these apart from the page.

     This is the same sentence item 116 asked for and it should be
     written once, doing both jobs: a one-line statement above the
     listings naming the real sources and the real places. Something
     with the shape of *"Pulled automatically from the Village of Mount
     Prospect, the Public Library and the Park District — plus Randhurst
     Village, Melas Park and downtown Emerson & Busse — several times a
     week."* That single line supplies the stable venue names item 116
     wants for entity clarity, the provenance claim item 124 needs, and
     the "what's in here" statement recommended in the **first**
     competitor review and still unshipped twenty-eight passes later.

     Trust research is consistent that naming sources raises credibility,
     and it costs one line of config per region. The reason to do it now
     rather than later is that it is also the answer to the question
     every press and sponsor conversation is about to ask.

     ✅ DONE (2026-09-18), merged into item 116's own field exactly as
     asked - "written once, doing both jobs" - rather than adding a
     second field that would need to stay in sync with it. Rewrote all
     four regions' `tagline` to lead with "Pulled automatically from
     the [Village/City], [Library], and Park District — plus [venues]
     — several times a week," so the provenance claim and the stable
     venue names item 116 wanted are now the same sentence, rendered in
     all four places `tagline` already reaches: the on-page "Issue for
     ..." statement, each hub card, every page's meta description, and
     `llms.txt`. `test_every_region_tagline_names_at_least_two_real_venues`
     (item 116's own drift guard) still passes unmodified - every
     rewritten tagline still names at least two of that region's
     hand-curated real venues, it just also now says where the data
     comes from. 369 tests pass; verified against the real generated
     site (`docs/mount-prospect-60056/index.html`'s on-page statement
     and meta description, `docs/index.html`'s hub card, `docs/llms.txt`'s
     region line) after a real `build_digest.py` run, not just the
     source YAML.

127. ✅ **DONE (build loop's own pick — a real crafted-input test of the
     .ics generator, since it hadn't been probed with an untrusted-input
     lens before, only checked for correctness).** `_ics_escape()`
     escaped backslash, comma, semicolon, and bare `\n` per RFC 5545, but
     not a bare `\r` (a carriage return not paired with `\n`) - and
     `fetch_ics()`'s own parsing already neutralizes this by running
     incoming text through `splitlines()` (which treats a lone `\r` as a
     line boundary), but `fetch_rss()`'s `item.findtext(...)` does not -
     it takes an RSS `<title>`/`<description>` value as-is, only
     `.strip()`-ing the ends. Confirmed exploitable with a real crafted
     title before fixing it: `"Fake Event\rDTSTART:...\rSUMMARY:Injected"`
     produced a `SUMMARY:` line with the raw `\r` bytes still embedded,
     which many real-world calendar parsers treat as leniently as a full
     CRLF line break - reading as extra, attacker-controlled ICS
     properties injected into the same `VEVENT` a fetched RSS title
     could reach.

     Fixed by normalizing `\r\n` and a bare `\r` to `\n` *before* the
     existing escape substitutions run, so the already-correct `\n`
     handling now also covers CR - one shared helper, both call sites
     (`build_ics_data_uri()`'s per-event download link and
     `build_region_calendar_ics()`'s subscribable feed) fixed at once.
     1 new regression test reproducing the exact crafted title above and
     asserting the resulting `SUMMARY:` line contains no raw `\r`. 370
     tests pass; a real `build_digest.py` run still exits 0.

128. ✅ **DONE — a self-correction from item 126's own change, found by
     re-reading a nearby function this build loop hadn't touched
     directly.** Item 126 rewrote every region's `tagline` to lead with
     "Pulled automatically from ... several times a week." That tagline
     renders inline, as the first sentence of `build_answer_block()`'s
     on-page GEO paragraph (`<p class="answer-block">`) - and that same
     function's own next sentence still said "This page rebuilds
     automatically, usually several times a week, and links directly
     to..." The same fact, in different words, twice in one paragraph:
     "Pulled automatically ... several times a week. This page rebuilds
     automatically, usually several times a week..." - exactly the kind
     of repetitive AI-answer-block text the item 22 feature this
     function serves is supposed to avoid.

     Dropped the now-duplicated automation/frequency clause, kept the
     one thing it said that `tagline` doesn't - that each listing links
     back to its official source - so nothing informative was lost, just
     the repetition. Updated the one existing test that had been passing
     against a now-unrealistic generic tagline fixture (a leftover from
     before item 116/126 rewrote every real tagline), and added a
     regression test asserting "automatically" appears exactly once and
     the frequency claim isn't repeated after the tagline. 371 tests
     pass; verified against the real generated site
     (`docs/mount-prospect-60056/index.html`'s `.answer-block` paragraph)
     after a real `build_digest.py` run.

129. ✅ **DONE — the same inconsistency as item 128, one rendering
     surface over.** After fixing the answer block's redundant
     automation claim, went looking for the same "how often does this
     update" statement everywhere else on the site to check none of the
     others had drifted. Found one that wasn't repetitive - it was
     **wrong**: `build_og_images()`'s per-region Open Graph caption
     ("What's happening in Mount Prospect — updated **weekly**") is what
     a shared region link actually shows in a link-preview card on
     Facebook/Slack/etc., and "weekly" contradicts the "several times a
     week" cadence every other surface states (`tagline`, the answer
     block, `llms.txt`'s intro, the Facebook post's own closing line).
     Changed to "updated several times a week", matching the rest of the
     site. Confirmed it still fits the image's 2-line wrap cap for every
     real region name, including the longest ("Arlington Heights") -
     rendered and visually inspected, not just measured. 1 new
     regression test capturing the subtitle string passed to
     `render_og_image()` (no OCR needed) and asserting it says "several
     times a week", not "weekly". 372 tests pass.

#### Research pass 2026-09-18 (thirtieth pass)

A follow-on from yesterday's Patch finding, and it changes the framing
again — this time in this site's favour, but only if something gets
fixed first.

The automated-local-content category had a bad 2026. **Prism News ran
more than 200 AI-generated "local news" sites and suspended them in
August** after investigations found plagiarism, fabrications, and
articles published under **fake AI-generated bylines** with quotes lifted
from real local reporting. NewsBreak has 40+ documented AI-generated
stories containing real inaccuracies about real communities. Even Patch
defends itself on this ground, conceding that asking an AI to "build a
newsletter for this town" fails on accuracy and trust, and that theirs
runs on a vetted corpus instead.

That is the neighbourhood this site's product description puts it in, and
it cuts both ways.

| Angle | Finding | Consequence |
|---|---|---|
| **Category credibility** | 200+ fake local sites shut down in August; fake bylines were a central finding | "Automated local guide, no named author" now pattern-matches to the thing that just got exposed (item 130) |
| **The defensible claim** | Checked on the live build: **19 of 19** event cards carry an external link to the source, and the pages already say events are pulled "automatically from the Village, Public Library, and Park District" | This site **generates no prose about events at all** — a claim Patch structurally cannot make (item 131) |
| **Accuracy posture** | The failures were accuracy failures. Replies now work (item 93) and nothing invites one | A visible corrections path is cheap and reinforces the only claim that matters (item 132) |

#### P1 (new)

130. **Put a real name on the About page — the cheapest trust signal
     available, and currently missing.** The About page says Within Ten
     is "written and run by **a local parent**." That was a reasonable
     default. It is now a liability: an automated local-events site with
     no named human behind it is, at a glance, indistinguishable from the
     200+ sites that were just shut down for publishing under invented
     bylines.

     Three separate things need this and none of them proceeds well
     without it:

     - **The press pitch (items 77/125).** A reporter is not going to
       write "a local parent built a website." The story item 77 is
       selling *is* the person — a Mount Prospect parent with a full-time
       job and two small kids who automated the village calendar. Remove
       the name and there is no story left.
     - **Sponsor conversations (items 118/119).** A local business owner
       buying a $1,200 annual membership is buying from somebody. The
       founding-partner pitch in particular is a personal ask.
     - **Item 124's differentiation.** "We are not one of those AI sites"
       is much easier to demonstrate than to assert, and a name with a
       town attached does most of the demonstrating.

     This is **the owner's decision, not the loop's** — it trades privacy
     for credibility and belongs in Needs Ryan. Worth naming the middle
     options rather than presenting it as all-or-nothing: a first name
     and last initial, or a name with no street-level detail, still beats
     anonymity by a wide margin. The contact email already on the site
     carries the surname anyway, so the marginal privacy cost of a byline
     is smaller than it looks.

     ⚠️ **Owner's decision, added to Needs Ryan — not something this loop
     should do on its own.** Whether and how to attach a real name (or
     first-name-plus-initial) to the About page's "written and run by a
     local parent" line trades the owner's own privacy for credibility,
     which is exactly the kind of call item 130 itself says belongs to
     him, not the build loop. Items 131 and 132 below - both real content
     changes with no privacy trade-off - shipped this same pass instead.

131. ✅ **State plainly that nothing here is written by a machine — it is
     the one claim competitors cannot copy.** Checked on the live build:
     **19 of 19** event cards link out to the source that published the
     event. The site fetches real listings from named civic feeds and
     reproduces title, date and a truncated detail, with a link home.
     **It generates no prose about events whatsoever.**

     That is a categorically different thing from an LLM writing local
     news, and it is exactly the distinction the Prism and NewsBreak
     failures have made legible to ordinary readers. Patch summarises and
     generates; this does not. The claim is checkable by anyone who
     clicks a link, which is what makes it worth making.

     Say it in one sentence, on the About page and in the sponsor kit:
     *nothing on this site is written by AI — every listing comes from
     the village, library, park district or school district's own
     calendar, and every link goes back to them.*

     **Be precise rather than triumphant**, because an overclaim here
     would be worse than silence. The pipeline does apply heuristic
     tagging (`infer_tags`), truncates source-written detail text, and
     selects which events lead. That is light editorial processing, and
     the sentence has to survive someone noticing it — "we don't write
     the listings" is true; "we don't touch anything" is not. The honest
     version is stronger anyway, because it can be defended.

     Related: "updated automatically" appears across the site as a
     feature. In the current climate it is ambiguous — it could mean
     "fetched from official feeds" or "written by a bot." Prefer the
     explicit phrasing the region pages already use ("automatically from
     the Village, Public Library, and Park District") everywhere the bare
     word appears.

     ✅ DONE (2026-09-18). Added the exact sentence this item asked for
     to the About page's "How it's built" section - "Nothing on this
     site is written by AI" - immediately followed by the precise,
     defensible version of what the pipeline *does* do (`infer_tags`,
     truncation, lead selection), so it survives the exact objection the
     item itself raised rather than overclaiming. Added the same claim,
     more concisely, to `SPONSOR_KIT.md`'s "Isn't this just Patch?"
     section, since a sponsor deciding whether to buy is asking the same
     question a reporter or reader is.

     Also did the "related" fix, not just the headline one: found and
     replaced every genuinely bare "updated automatically" (no source
     named anywhere nearby) across the site - the hub's `<meta
     description>`/`og:description`/`twitter:description` (all three
     identical, now "pulled automatically from each town's village,
     library, and park district"), both email templates' footer tagline,
     and the Facebook weekly-summary's closing line. Left the handful of
     occurrences that already have a source-naming qualifier in the same
     sentence alone (`about.html.j2`'s own two other paragraphs, the
     `llms.txt` intro, the RSS feed description) - those aren't the
     ambiguity this item is about.

     5 new regression tests (the AI-disclosure statement's exact wording
     and precision, plus `build_corrections_cta_url`'s two branches used
     by item 132 below). 377 tests pass; verified every fix against the
     real generated site (`docs/about/index.html`, `docs/index.html`'s
     meta tags, `docs/combined-email-send.html`'s footer,
     `docs/mount-prospect-60056/weekly-summary.txt`) after a real
     `build_digest.py` run, and re-ran the real accessibility audit
     (axe-core, light and dark) against the two pages touched most (hub,
     about) - 0 violations.

#### P2 (new)

132. ✅ **Add a corrections path, because accuracy is the entire claim.**
     Every failure in the category above was an accuracy failure. This
     site's differentiation rests on being traceable and correct — and it
     currently offers a reader who spots a wrong date no way to say so,
     and states no position on what happens when something is wrong.

     The mechanism already exists and is unused: replies reach a real
     inbox since item 93, and item 106's welcome email is already slated
     to invite them. Extend that to the site itself — a short line in the
     footer and on the About page: *see something wrong or missing? reply
     to the newsletter or email us — corrections get made the same week.*
     Promise only the cadence the rebuild can actually keep.

     Two reasons this is worth more than it costs. It converts the
     product's biggest structural weakness — nobody checks the feeds by
     hand — into a distributed check, at zero owner time until someone
     actually writes in. And a stated corrections posture is the clearest
     signal that a real person stands behind the thing, which is item
     130's argument arriving from a different direction.

     It also feeds the moat: a resident writing in about an event no feed
     carries is exactly the content no competitor can aggregate, and the
     twenty-fifth pass already identified replies as the highest-value
     thing a local subscriber can send.

     ✅ DONE (2026-09-18). A real point of contact, not just a promise:
     added `build_contact_mailto_url()` (generalizing the sponsor CTA's
     existing mailto-or-GitHub-issue-fallback logic, item 57, since it's
     the same underlying need - a real address, never guessed) and
     `build_corrections_cta_url()` on top of it. Threaded `contact_email`
     through to `render_about_page()` and `render_hub_page()` (both had
     exactly one call site in `main()`, so this stayed a small, mechanical
     change) rather than only adding it where it was easiest.

     Added the exact line this item asked for - "corrections get made
     the same week" - to both the About page's "Questions or corrections"
     section (which already had a GitHub-issue path for new event
     submissions; this adds the general-purpose one) and the hub page's
     footer, the site's front door. Didn't thread it through
     `region.html.j2`'s five call sites this same pass - the About page
     is one click from every region page's own footer already, and the
     hub covers "the footer" this item asked for without touching five
     call sites for one line; worth doing later if it turns out readers
     don't find it there.

     2 new regression tests (About page and hub page each showing the
     cadence promise and a real mailto CTA when configured). 377 tests
     pass; verified against the real generated site (`docs/about/index.html`'s
     mailto link genuinely resolves to the configured `contact_email`,
     `docs/index.html`'s footer) after a real `build_digest.py` run.

133. ✅ **DONE (build loop's own pick — a full read-through of
     `scripts/send_newsletter.py`, since it hadn't had one this
     session).** `read_build_timestamp()` parses `docs/feed.xml`'s
     `<lastBuildDate>` with `email.utils.parsedate_to_datetime()`, which
     does **not** raise on a date string with no UTC offset - it
     silently returns a naive datetime instead. Confirmed empirically,
     not assumed: `parsedate_to_datetime("Fri, 18 Sep 2026 13:00:29")`
     (no trailing zone) returns
     `datetime(2026, 9, 18, 13, 0, 29)` with `tzinfo=None`, no exception.
     Unguarded, that naive value would flow straight into
     `assert_build_is_fresh()`'s `now - build_time`, where `now` is
     always aware - a bare, uncaught `TypeError` ("can't subtract
     offset-naive and offset-aware datetimes") instead of the clean
     `SendError` every other bad-input path in this file raises, which
     is exactly the loud-but-readable failure item 111 exists to
     guarantee.

     Not reachable through the current pipeline today -
     `build_digest.py`'s `build_feed_xml()` always writes an aware `now`,
     and `email.utils.format_datetime()` always renders an aware
     datetime with an explicit offset - but a real, findable gap in a
     module whose own stated design promises loud, readable failures on
     bad input, not raw tracebacks. Fixed at the source (inside
     `read_build_timestamp()`, right where the ambiguity is introduced)
     rather than downstream at the subtraction site: raise `SendError`
     immediately if the parsed timestamp has no `tzinfo`. 1 new
     regression test reproducing the exact naive-date string above. 378
     tests pass; the real dry-run path (`--dry-run` against a real
     `build_digest.py` output) still passes its freshness check
     unaffected, confirming this doesn't touch the normal case.

134. ✅ **DONE — the exact bug item 127 just fixed server-side, found
     duplicated client-side.** After fixing `_ics_escape()`'s missing
     bare-`\r` handling in `build_digest.py`, checked whether the same
     escaping logic existed anywhere else in the codebase - and it did:
     the "Build my weekend" itinerary tray's client-side "Export all to
     calendar" button (`templates/region.html.j2` and
     `templates/weekend_hub.html.j2`, both templates carry their own
     copy of this JS) has its own `icsEscape()`, byte-for-byte the same
     unpadded four-substitution version the Python one used to be -
     escapes `\`, `,`, `;`, `\n`, but not a bare `\r`.

     **Confirmed exploitable with a real headless-browser test before
     fixing it, not assumed from reading the code**: seeded
     `localStorage`'s `weekendPlannerTray` with a crafted item titled
     `"Fake Event\rDTSTART:20260101T000000Z\rSUMMARY:Injected"` (the
     same class of value `fetch_rss()`'s `item.findtext()` can hand
     through unescaped - `.strip()` only trims the ends, no line-
     splitting), clicked the real "Export all to calendar" button, and
     read back the downloaded `.ics` `Blob`'s actual content: the
     `SUMMARY:` line came back with the raw `\r` bytes still embedded,
     exactly like the server-side bug before its fix - a calendar app
     lenient about line endings would read the injected text as extra
     ICS properties in the same `VEVENT`.

     Fixed identically in both templates: the same CRLF/bare-CR-to-LF
     normalization added to `build_digest.py`, ported to JS
     (`.replace(/\r\n/g, "\n").replace(/\r/g, "\n")` before the existing
     four substitutions). Re-ran the identical headless-browser test
     against the fixed build on both pages (`/mount-prospect-60056/`
     and `/this-weekend/`, since the itinerary tray exists on both) -
     the exported `SUMMARY:` line now contains no raw `\r` on either.
     No JS test framework exists in this repo (`package.json` is
     Lighthouse-CI-only), so this is verified the same way item 35's
     original DOM-XSS fix to this same script was - a real, scripted
     browser check, not a persisted automated test. 378 tests pass
     (Python suite unaffected, since this is client-side JS).

135. ✅ **DONE (build loop's own pick) — the same unpadded-substring
     tagging bug class as item 121, one more real false positive found
     by testing a plausible real municipal program title, not by code
     inspection.** `"baby"` in the `toddler` tag's keyword list was
     unpadded, and a literal prefix of `"babysitting"`/`"babysitter"` -
     confirmed with a real, common library/park district offering,
     `"Babysitting Basics Certification Course"` (typically aimed at
     tweens/teens learning to care for *younger* kids, not the toddlers
     themselves), which `infer_tags()` tagged `toddler` purely from that
     substring before the fix.

     Fixed with the same word-boundary-padding idiom item 121 already
     established for `kid`/`pup`/`hall`/`art`: `"baby"` → `" baby "`
     (both sides padded, since the false positive extends the keyword
     on one side only - same shape as `kid`/`kidney` and `pup`/`puppet`).
     `"babies"` (plural, already in the list) is unaffected and keeps
     covering that common phrasing without this risk, same reasoning as
     `kids`/`kidney` before it.

     Two regression tests added
     (`test_infer_tags_baby_does_not_false_positive_on_babysitting`,
     `test_infer_tags_baby_still_matches_bare_word`) confirming the fix
     closes the false positive while `"Mommy and Baby Yoga"` and `"Baby
     Storytime"` still correctly tag `toddler`. Considered the same
     substring risk for `"trail"` (a prefix of `"trailer"`, in the
     `outdoor` tag) but left it alone: unlike `art`/`baby`/`kid`/`pup`/
     `hall`, the false-positive word extends the keyword on the
     *trailing* side, so the same leading-space padding trick doesn't
     fix it (would need a trailing-boundary check the plain-`in`
     matcher here doesn't do), and a real municipal listing titled
     around "trailer" is a much thinner hypothetical than a real
     babysitting-certification program - not worth the added complexity
     ahead of an actual false positive being found. 380 tests pass;
     verified against a real `build_digest.py` run (network calls to
     the real fetcher/weather/IndexNow hosts fail in this sandbox as
     expected - proxy-blocked, not a regression - the build still
     completes and every page renders).

136. ✅ **DONE (build loop's own pick) — a third, unfixed instance of the
     same bare-CR ICS injection items 127/134 already fixed twice, found
     by checking whether `event['url']` had the same gap as
     title/detail.** `_ics_escape()` (item 127, server-side) and its JS
     mirror `icsEscape()` (item 134, client-side) both escape TEXT-typed
     properties - `SUMMARY:`/`DESCRIPTION:`. Neither ever touched
     `URL:{event['url']}` (`build_ics_data_uri()`,
     `build_region_calendar_ics()` in `scripts/build_digest.py`) or its
     two client-side twins (`templates/region.html.j2` and
     `templates/weekend_hub.html.j2`'s `"URL:" + item.url` in the
     itinerary tray export) - a URI-typed property doesn't need TEXT's
     backslash-escaping, but a raw CR/LF in it still corrupts the `.ics`
     content-line structure exactly the same way an unescaped one in
     SUMMARY does, and `event['url']` is real, fetched RSS `<link>`/HTML
     `href`/ICS `URL:` text that never runs through a line-splitting
     pass (same reasoning as items 127/134's title/detail case).

     **This instance is the most exposed of the three**: the client-side
     tray export needs a visitor to click "Export," but
     `build_region_calendar_ics()` writes a public, continuously-
     refreshed `calendar.ics` a real calendar app *subscribes* to - a
     malicious/compromised RSS feed could inject into every subscriber's
     calendar app on the next refresh, with no click required at all.

     **Confirmed exploitable before fixing, not assumed**: crafted an
     event with `url = "https://evil.example/x\rDTSTART:...\rSUMMARY:
     Injected"` and ran it through both Python builders directly - the
     raw `\r` landed unescaped in the generated `URL:` line both times.
     For the two client-side copies, reproduced with the same real
     headless-Playwright technique item 134 used: seeded
     `weekendPlannerTray` with the same malicious URL, clicked the real
     export button on both `/mount-prospect-60056/` and `/this-weekend/`,
     and read back the downloaded `.ics` Blob - confirmed the raw `\r`
     present before the fix, on both pages.

     Fixed with a new helper on each side rather than reusing
     `_ics_escape()`/`icsEscape()`: those fold a CR/LF to visible `\n`
     text, appropriate for a title/detail that might legitimately
     contain one; a URL never legitimately does, so `_ics_sanitize_url()`
     (Python) and `icsSanitizeUrl()` (JS) strip embedded CR/LF outright
     instead. Applied at all four call sites (two Python, two JS).
     Re-ran the same reproductions against the fixed build - no raw `\r`
     in the `URL:` line anywhere. Two new regression tests added
     (`test_build_ics_data_uri_strips_bare_carriage_returns_from_url`,
     `test_build_region_calendar_ics_strips_bare_carriage_returns_from_url`).
     382 tests pass; verified against a real `build_digest.py` run.

#### Research pass 2026-09-18 (thirty-first pass)

Searching for the site's own brand name turned up a competitor nobody
here had seen, and did **not** turn up the site.

| Angle | Finding | Consequence |
|---|---|---|
| **Kidlist** | A weekly family-events email and weekend planner for the **west and northwest Chicago suburbs** — the same territory. Submission-based, human-reviewed, named editor, and an explicit rule that the calendar carries only free/drop-in events | The nearest competitor yet, and the useful kind: it validates the model and shows exactly where the differentiation is (item 137) |
| **Brand-name search** | A query naming `withintenmiles.com`, "Within Ten" and Mount Prospect returns Eventbrite, Meetup, the village, the library, Kidlist — and **not this site** | Expected at four days old, but it is the baseline worth recording and the first signal to watch (item 139) |
| **Source coverage** | Configured sources per region: Mount Prospect **8**, Palatine **5**, Arlington Heights **4**, Des Plaines **3**. Des Plaines is the only region with **no school-district feed at all** | A category gap, not a volume gap — card counts are 16–20 everywhere (item 138) |

#### P1 (new)

137. ✅ **DONE — Kidlist is the real competitor, and the comparison is
     clarifying.** `mykidlist.com` publishes a weekly family-activities
     email and a weekend planner for the west and northwest Chicago
     suburbs — not a national template pointed at a ZIP, but a real
     regional publication with a named editor, covering the same towns.
     Thirty-one passes in, it is the closest analogue found, and it is
     more instructive than Patch because it is *good*.

     What it validates, which is worth saying plainly rather than
     treating every competitor as a threat: a weekly local family email
     works, a weekend-planner framing works, and a **free/drop-in
     filter** is worth having as a first-class thing — Kidlist makes it
     an editorial rule, this site already ships it as the `/free` view.
     That is two independent arrivals at the same design.

     Where the difference actually lies, and it is not "we are better":

     - **Kidlist is submission-based and human-reviewed** (approvals on
       Wednesdays). It carries what somebody submitted and an editor
       approved. This site carries what the village, library, park
       district and school district **published**, whether or not anyone
       thought to submit it. Those are different coverage guarantees and
       both have failure modes — theirs misses what nobody submits, this
       one misses what no feed carries.
     - **Kidlist is family-only by policy.** This site is all-audience:
       village board meetings, library adult programs and park district
       senior events are in scope. Narrower and broader respectively.
     - **Kidlist is regional; this is per-town.** A Mount Prospect parent
       gets Mount Prospect, not "the northwest suburbs."

     Two concrete consequences. `SPONSOR_KIT.md` and the press pitch
     should name Kidlist honestly when asked what else exists — a local
     business owner may already know it, and pretending otherwise ends
     credibility faster than the competition does. And **Kidlist's editor
     is named and reachable**, which is independent support for item 130:
     the successful local competitor in this exact market does not
     operate anonymously.

     ✅ DONE (build loop's own pick, same cycle). Added a matching
     "Isn't this just Kidlist?" section to `SPONSOR_KIT.md`, right after
     the existing Patch section, naming the real coverage/audience/
     granularity differences (feed-based vs. submission-based,
     all-audience vs. family-only, per-town vs. regional) rather than
     claiming either is "better" - exactly the framing this item asked
     for, and structurally the same pattern the Patch section already
     established, so a reader sees Within Ten answer this question
     honestly for a second real competitor, not just the first. Added a
     parallel paragraph to `OUTREACH_TEMPLATES.md` §7 (the press pitch)
     giving the same talking points for *if* a reporter raises Kidlist,
     without baking an unprompted competitor comparison into the cold
     pitch itself - matching how that same template already handles
     Journal & Topics. Didn't touch item 130 (naming a real person on
     the About page) - that's still the owner's own privacy/credibility
     call, already in Needs Ryan; this item's mention of Kidlist's named
     editor is supporting evidence for that decision, not a new reason
     to make it here. 382 tests pass (markdown-only change, no code
     path touches these files at build time - confirmed by grepping for
     references, then still ran the full build as this loop's standing
     verification step).

#### P2 (new)

138. ✅ **DONE (build loop's own pick, partial) — Des Plaines is the only
     region with no school-district feed.**
     Counted in config: Mount Prospect 8 sources, Palatine 5 (including
     two districts), Arlington Heights 4 (including D25), **Des Plaines
     3 — village, library, park district, and nothing else.**

     Being precise about the size of this, because the obvious framing
     overstates it: it is **not** a volume problem. The live build
     produces 16 cards for Des Plaines against 19 for Mount Prospect, so
     a reader is not seeing an empty page. It is a **category** gap. A
     Des Plaines parent gets no early-dismissal or no-school days, while
     a parent one town over does — and since item 90 made informational
     items first-class with their own "Also this week" grouping, that
     category now has a real place in the product that Des Plaines
     silently never fills.

     It matters more since item 105: the combined email puts all four
     regions in front of every subscriber every week, so per-region
     asymmetries are now visible to everyone rather than only to the
     people in that town.

     The fix is ordinary and follows the existing discipline — find
     District 62's published calendar feed the same way D57's was found
     (via the district's own iCal page), add it to
     `config/regions/des-plaines-60016.yaml` with `informational: true`
     so item 90's classification applies, and let the fail-soft fetcher
     handle an unverified URL. Worth checking Arlington Heights for a
     high-school district too: Palatine carries both D15 and D211, and
     Arlington Heights carries only D25.

     ✅ DONE, partially - the honest version. WebSearch found d62.org's
     calendar module is **Finalsite**, not the ASP.NET-style platform
     D57/D25 use - a real, material difference from "find it the same
     way D57's was found." D57's `/ical/<District_Name>_export.ics` is a
     readable, guessable filename (confirmed by that district's own
     indexed page); Finalsite's own support docs describe a "Get
     Standard iCal URL" generated **per calendar** from that calendar's
     Settings panel - an opaque, calendar-specific link with no
     discoverable static pattern, and this sandbox's WebFetch is
     proxy-blocked for `d62.org` the same way it is for every other
     fetcher host here, so the actual per-calendar URL couldn't be read
     off the page directly either. Inventing a plausible-looking hashed
     URL would have been a fabrication, not a real-evidence guess like
     D57's - so added the confirmed real page (`d62.org/calendars`,
     verified indexed via WebSearch) as an `html_events` source instead,
     the same honest-fallback shape already used for two of this same
     region's other three sources. Didn't add `informational: true`
     (the item's own suggestion): checked every existing school-district
     source in this repo first and none sets it - `is_informational()`'s
     per-item phrase detection (item 90) already reclassifies a "No
     School"/"Early Dismissal" item without it, so adding an
     inconsistent one-off here would be new drift, not a fix. Also
     confirmed the Arlington Heights/D214 sub-question needs no new
     work: `config/regions/arlington-heights-60005.yaml`'s existing
     comment already documents D214 (the shared high school district)
     as researched and found to have no discoverable public ICS, only
     PDF calendars - a district-wide finding, not region-specific, so
     nothing was missing there. 382 tests pass; verified against a real
     `build_digest.py` run (the new source hits the same proxy-blocked
     transport error every other fetcher in this sandbox does - not
     counted against source health, and will self-correct from the next
     real GitHub Actions build's logs if `d62.org/calendars`'s link list
     turns out to be JS-rendered, same recovery path every other guessed
     `html_events` source in this file already has).

#### P3 (new)

139. ✅ **DONE — first real baseline taken.** A search naming the domain, the brand and the town returns
     Eventbrite, Meetup, the village, the library and Kidlist — and not
     this site. That is entirely expected four days after the domain was
     verified in Search Console, and it is not a defect. It is a
     **measurement**, and it is the one this file has never taken.

     Brand-name queries are the first thing a new domain wins — long
     before it competes for "things to do in Mount Prospect." So the
     order of signals to watch, roughly weekly, is: the site appears for
     its own brand name, then for `site:withintenmiles.com`, then for
     long-tail town+venue queries, and only much later for the head term
     Eventbrite owns. Checking the head term first is how a founder
     concludes SEO is not working when it is simply early.

     Worth writing down as a short section in the roadmap or a
     `METRICS.md` rather than re-deriving it each pass: the date checked,
     which of those four signals is live, and nothing else. Item 102
     already argued for open frequency as the retention metric; this is
     the same argument on the acquisition side, and both are cheap
     precisely because they are single numbers checked occasionally
     rather than a dashboard nobody maintains.

     **Discoverability baseline (checked 2026-09-18, via WebSearch)**:

     | Signal | Live? |
     |---|---|
     | Brand-name query (`Within Ten withintenmiles.com Mount Prospect events`) | ❌ Not yet — returns Kidlist, the Village, Eventbrite, the Library, mpdowntown.com, Meetup, AllEvents |
     | `site:withintenmiles.com` | ❌ Not yet — zero results, no unrelated noise either (nothing mis-indexed under the domain) |
     | Long-tail town+venue query (`"Within Ten" Mount Prospect weekend events village library park district`) | ❌ Not yet — returns the Library's own pages, the Park District, Meetup |
     | Head term (`things to do in Mount Prospect this weekend`) | Not checked this pass — expected last regardless, per the ordering above; not worth spending a query on until the first three move |

     All three checked signals are still off, four days after GSC
     verification - exactly what this item predicted, not a surprise or
     a regression. Recorded here as this file's own convention (inline,
     no new `METRICS.md`, matching how item 102's open-frequency metric
     is tracked) so the next check is a diff against a real number
     instead of a re-derivation. Re-check roughly weekly, in the same
     order, and stop at the first signal that's still off - no need to
     spend a query confirming the head term is also off once brand-name
     already is.

140. ✅ **DONE (build loop's own pick) — a real production duplicate-card
     bug, found by reading the actual output of the real GitHub Actions
     build that ran after item 138's D62 source shipped, not by code
     inspection.** `data/source_health.json` showed the new source
     fetching a real `6` items on its first live run - genuinely working,
     contrary to this file's own worry that Finalsite's calendar list
     might be JS-rendered. But the built `docs/des-plaines-60016/
     index.html` showed why it was 6 and not fewer: **"All Schools: No
     School (Labor Day)" appeared twice, and "ICS: No School
     (Parent-Teacher Conferences)" appeared four times** - the real,
     live site rendering the same two closures six times over instead
     of twice.

     Root cause, found by reading `fetch_html_events()`
     (`scripts/fetchers.py`): its `detail_links` branch (used when a
     source has real per-event URLs) already dedupes by `url`, but the
     **fallback keyword branch** right below it - the one every source
     without a confirmed detail-link pattern falls into, D62 included -
     never deduped at all. D62's calendar page apparently links each
     closure notice more than once (an "ICS:"/"All Schools:"-prefixed
     add-to-calendar variant alongside the plain listing), and since
     every item in this fallback branch shares one generic listing-page
     `url` (that's exactly why it's in the fallback branch and not the
     one above), nothing ever collapsed the repeats.

     Fixed by deduping the fallback branch too - but **not** by `url`
     alone, which would have overcorrected: two genuinely different
     closures (Labor Day, Parent-Teacher Conferences) share that same
     one page `url`, so deduping on `url` alone would have silently
     dropped one of them as a false duplicate. Deduped on `(title, url)`
     together instead, which collapses the real repeats while keeping
     both real closures. This is a generic fix to a shared fetcher, not
     a D62-specific patch - it protects every other source that falls
     into this same fallback branch (Village News, Library Events, and
     several park district sources across all four regions) from the
     identical failure mode the moment any of their pages happens to
     link an item more than once, which this file had never had real
     evidence of until this build.

     Two regression tests added
     (`test_fetch_html_events_dedupes_identical_title_and_url_in_fallback`,
     reproducing the exact real titles/counts from the production
     build, and `test_fetch_html_events_keeps_distinct_titles_sharing_one_page_url`,
     guarding against the `url`-alone overcorrection). 384 tests pass;
     verified against a real `build_digest.py` run.

#### Research pass 2026-09-19 (thirty-second pass)

Three scheduled firings arrived while the previous pass was still
running (00:33, 06:33, 12:33 UTC). This is one pass covering all three
rather than three thin ones — recorded so the gap in dated headings is
not read later as missed runs.

| Angle | Finding | Consequence |
|---|---|---|
| **Farmers markets** | Every major Chicago outlet — WBEZ, Sun-Times, WTTW, WGN, **and Patch** — publishes a dated suburban market guide each spring, by region and weekday, with season dates and hours. Seasons are fixed and knowable a year ahead (e.g. Sundays, 14 Jun – 11 Oct) | The pipeline has **no vocabulary for a recurrence** and the circuit guide punts to the organiser (item 141) |
| **Backlog accuracy** | 49 items read as open in this file. Cross-referencing commit messages, **22 of them have shipping commits** | The file overstates its own backlog by ~45% (item 142) |
| **Google Business Profile** | Eligibility requires in-person customer interaction; **online-only businesses cannot create one** | A tempting local-pack idea that does not apply — recorded so it is not re-derived (item 143) |

#### P1 (new)

141. ✅ **DONE — Teach the pipeline what a recurring event is — starting with
     farmers markets, which are the clearest case and a category
     competitors already own.** Checked in config: there is no
     recurrence vocabulary anywhere. `annual_events` reads exactly
     `title`, `detail`, `tags` and a single `date`, and the
     `seasonal-circuit-guide` handles recurring things in prose —
     "links to the real organisers' own pages, where each year's exact
     dates actually get posted." That is the same punt item 101 removed
     from the trick-or-treat page, still in place here.

     It matters because a farmers market is not a footnote to the
     weekend — on a Sunday morning from June to October it **is** the
     weekend, every weekend, for twenty consecutive issues. Right now a
     market that runs Sundays 14 Jun – 11 Oct, 7am–1pm appears in no
     weekend view, no email, and no calendar feed, despite being the most
     reliably knowable event the region has. Meanwhile WBEZ, the
     Sun-Times, WTTW and Patch all publish dated market guides every
     spring, so this is a category where competitors already rank and
     this site offers a link to somewhere else.

     The fix is small and reuses everything downstream. Add a minimal
     recurrence block to `annual_events` — `starts`, `ends`, `weekday`,
     `time` — and expand it into concrete dated occurrences at build
     time. Every consumer already works on dated events, so the weekend
     view, the combined email, schema.org `Event` and item 100's
     `calendar.ics` all pick it up with no further work. Bound the
     expansion (say 120 days forward) so a five-month season does not
     inflate the sitemap or the feed.

     **One design consequence, and it is the reason to think before
     shipping this:** the same market appearing in twenty consecutive
     emails is exactly how a digest starts feeling automated and stale —
     the failure mode item 124's competitors have. Apply item 90's
     lesson rather than re-learning it: a recurrence is a *standing*
     item, not a headline. It belongs in the "Also this week" grouping,
     must never be picked for a subject line, and is worth a light
     visual treatment ("every Sunday through 11 Oct") that reads as
     reference rather than news. Get that right and the recurrence is an
     asset; get it wrong and it is twenty weeks of repetition.

     ✅ DONE (build loop's own pick, same cycle). Added a minimal
     `recurrence:` block to `annual_events` (`starts`, `ends`, `weekday`,
     optional `time`) and `expand_recurring_annual_event()` in
     `scripts/build_digest.py`, which turns it into concrete dated
     occurrence dicts at build time - bounded to `MAX_RECURRENCE_DAYS`
     (120) forward from `now` or `ends`, whichever is sooner, and never
     includes an occurrence that's already passed. Every occurrence
     reuses `_build_annual_event_dict()` (factored out of the existing
     single-`date:` path so both share one code path), so it's just
     another dated event to every downstream consumer - the weekend
     view, both email templates, schema.org `Event`, and item 100's
     `calendar.ics` all picked it up with zero changes of their own.

     Took the "One design consequence" warning literally rather than the
     literal "Also this week" grouping suggested (that's item 90's
     *non-attendable* informational bucket - a farmers market is a real
     event people attend, so reusing it would have misrepresented one).
     Instead: every occurrence carries `attendable: True` and
     `recurring: True`; `build_email_subject_line()` and
     `select_editors_pick()` both now exclude `recurring` items from
     their headline pick specifically (a recurring item still counts in
     the subject line's "and N more" tally, and `editors_pick_url` can
     still target one by hand) - applying the item's own stated
     principle to *both* places on the site that pick a "headline," not
     just the one it named. Visual treatment: a muted, italic
     `recurrence-note` kicker ("Every Sunday through Oct 25") on the
     card, deliberately the opposite weight of the existing bold/accent
     `.series` kicker, in both HTML templates and both email templates.

     Shipped with a real, WebSearch-confirmed entry, not just the
     infrastructure: the **Mount Prospect Farmers Market** (Mount
     Prospect Lions Club, 2026 season June 7 - Oct 25, Sundays 8am-1pm,
     West Metra commuter lot) - confirmed against three independent
     sources (the Village's own calendar, the Lions Club's own site, and
     the National Farmers Market Directory) before adding it to
     `config/regions/mount-prospect-60056.yaml`. Verified against a real
     `build_digest.py` run, not just the tests: the built
     `this-weekend/index.html` shows exactly one real occurrence
     (Sep 20) with no duplication across its star-button/title/JSON-LD
     representations, `calendar.ics` carries six real future Sunday
     occurrences, and the card's `recurrence-note` renders correctly.
     14 new tests (recurrence expansion - weekly cadence, the 120-day
     bound, skipping already-passed occurrences, the midnight default,
     three fail-soft cases for bad input; subject-line and Editor's Pick
     exclusion, both directions - excluded from the automatic heuristic,
     still reachable via explicit override). 399 tests pass.

142. ✅ **DONE — the backlog overstated itself by nearly half, and this file is the
     coordination surface between two loops.** Counting numbered Phase 11
     items: 139 total, 89 marked done, 1 skipped, **49 reading as open**.
     Cross-referencing those 49 against commit messages that name an item
     number, **22 have shipping commits** — 24, 31, 37, 47, 90, 91, 92,
     94–106, 110, 116 among them.

     This is not a cosmetic problem. The file's main job is telling the
     build loop what is left, and it is currently wrong about that in 45%
     of cases. The cause is mechanical rather than careless: the build
     loop ships a change and writes "(item N)" in the commit, but the
     numbered heading in `ROADMAP.md` keeps its original wording, so
     nothing in the file changes. Both loops then re-read an item that is
     already done — and the research loop has to check git log to know
     the difference, which it will not always do.

     Two fixes, and the second matters more. **Reconcile once**: walk the
     22, confirm each against the actual code rather than trusting the
     commit message, and mark the heading `✅ DONE` with the PR number.
     **Then close the loop**: the build loop should mark the item done in
     the same commit that implements it, and a test can enforce the
     weaker version cheaply — assert that no item referenced as shipped
     in the last N commits still reads as open. A convention nothing
     checks is the convention that drifts.

     Both fixes done (build loop's own pick, same cycle). **Reconciled,
     but the scope turned out to be 34 items, not 22** - the research
     pass's own count (via `git log` grep for `"(item N)"` in commit
     messages) missed items whose body already carried a `✅ DONE`
     marker but whose heading never got a second look, including several
     from *this session's own* recent cycles (118-132) - the drift this
     item describes is real even in code freshly written by this same
     loop, not just old history. Confirmed each one the way the item
     asked - against the actual body text's own prior verification, not
     re-trusting a commit message - before touching the heading, and
     deliberately did **not** touch three that looked similar but
     weren't: items 25, 77, and 130 all carry a `⚠️` marker too, but it
     means "drafted, a human action is still pending" (a press pitch
     unsent, a cross-recommendation email unsent, a name decision not
     yet made), not "done" - marking those `✅` would have been the exact
     kind of false-positive this reconciliation exists to prevent, not a
     fix. Left item 47 alone for the same reason from the other
     direction: its own text says "not marking this item fully done"
     and means it (unsubscribe headers, spam-complaint monitoring still
     real work).

     For "close the loop," added `tests/test_roadmap_consistency.py`
     instead of a git-log-parsing test (fragile in a shallow clone, and
     git history isn't guaranteed available inside every CI checkout) -
     a static check of `ROADMAP.md` itself: any numbered item whose body
     contains a `✅ DONE` marker must carry that marker on its own
     heading line too, or the test fails and names the item. Verified it
     actually catches the drift, not just passes by construction:
     reverted one heading back to its old unmarked wording, watched the
     test fail and name that exact item, then restored it. 385 tests
     pass (1 new). The first fix (this reconciliation) is done manually,
     once; the second (this test) is what keeps it from being needed
     again - if a future cycle's own `✅ DONE` note doesn't make it onto
     the heading, CI says so on the very next run instead of the count
     silently drifting for another thirty-plus items.

#### P3 (new)

143. skipped — **A Google Business Profile for the site.** Superficially
     attractive after item 139 measured discoverability at zero: a GBP
     surfaces in Maps and the local pack, is free, and is the standard
     first move for a local business.

     It does not apply. Eligibility requires interacting with customers
     **in person**, at a physical location or within a defined service
     area; a business operating entirely online, with no face-to-face
     contact, cannot create a profile. This site is online-only. Creating
     one anyway would mean claiming a storefront that does not exist,
     which is both against the guidelines and exactly the kind of
     fabrication items 130/131 argue this business must stay clear of.

     Recorded rather than left out, because "get a Google Business
     Profile" is an obvious suggestion that will recur every time
     discoverability comes up. The legitimate versions of the same
     instinct are already in the backlog: item 116's stable venue names
     for entity clarity, item 99's `Organization` schema, and item 126's
     provenance line.

144. ✅ **DONE (build loop's own pick) — a real timezone bug in item 141's
     own recurrence code, found the same hour it shipped, not by code
     review months later.** `expand_recurring_annual_event()` computed
     its "today" cutoff from `now.date()` - the build server's UTC
     date - while `region_local_date()` exists elsewhere in this exact
     file specifically because "today" near midnight depends on the
     region's own timezone, not the server's. The new recurrence code
     never called it.

     **Confirmed exploitable with a real crafted input before fixing,
     not assumed:** a build running Sunday night Central time (10pm CDT)
     is already Monday 3am in UTC. Fed that exact UTC timestamp into
     `expand_recurring_annual_event()` for a Sunday-recurring market and
     the function returned **next** Sunday as the soonest occurrence -
     skipping the Sunday that was, locally, still in progress, and
     jumping a full week ahead. Since this loop's own builds run at
     arbitrary times via push-triggered CI (not just the Monday-morning
     schedule), the UTC/Central offset (5-6 hours) means a meaningful
     fraction of the day was affected, not an edge case.

     Fixed by changing `expand_recurring_annual_event()`'s signature
     from a bare `now: datetime` to a `today: date` the caller supplies
     already localized, and having `prepare_annual_events()` compute it
     via the same `region_local_date()` every other date-boundary
     decision in this file already uses (`weekend_dates()`,
     `filter_events_by_dates()`) - applying the fix that already exists
     for this exact class of error instead of reintroducing it.

     One new regression test reproduces the exact scenario found (a
     Sunday-night-Central build, expressed as its real Monday-UTC
     timestamp, asserting the still-in-progress Sunday is not skipped),
     plus updated the existing recurrence tests to pass a `date` instead
     of a `datetime` now that the function's own contract changed. 400
     tests pass; verified against a real `build_digest.py` run.

145. ✅ **DONE (build loop's own pick) — a real RSS spec violation, found
     by reading the actual generated `docs/feed.xml` after item 141
     shipped, not by re-reading the diff.** `build_feed_xml()` gave every
     `<item>` a `<guid isPermaLink="true">` built from nothing but its
     `url` - fine when every event links a distinct page, wrong the
     moment two events share one. A recurring event's every occurrence
     links the same organiser page by design (item 141), so the real
     build's `docs/feed.xml` had **six items for one farmers market, all
     six with the byte-identical guid** - confirmed by grepping the
     actual generated file, not assumed from the code. RSS readers and
     aggregators use `<guid>` for deduplication; many treat a repeated
     guid as "the same item again," so at most one of six real, distinct
     dates would likely ever reach a subscriber. `isPermaLink="true"`
     compounded it - one URL cannot truthfully be six different dates'
     "permanent link" at once.

     Not purely new: the same collision already existed for a
     multi-day annual event sharing one info-page URL across days (item
     71's `series` - Oktoberfest/Fall Festival, Palatine's own Oktoberfest)
     - smaller and less visible at two items than at six, but the same
     bug, confirmed in the same real rebuild after the fix (three
     distinct guids, one per Palatine Oktoberfest day, where "before"
     would have been three duplicates).

     Fixed by counting `url` occurrences across the build's own item set
     first: a `url` that's actually unique keeps the simple
     `isPermaLink="true"` guid; one shared by two or more items gets the
     event's `date_iso` folded into the guid and switches to
     `isPermaLink="false"` - the RFC-documented way to say "stable
     identifier, not a dereferenceable page of its own," rather than
     inventing a new convention. `<link>` is untouched either way, so
     the real organiser URL a reader clicks never changes.

     Two new regression tests (shared-URL items get distinct guids with
     `isPermaLink="false"`; non-colliding items keep the simple
     `isPermaLink="true"` guid unchanged) plus re-verified against a
     real rebuild: 16 feed items, 16 distinct guids, zero collisions.
     402 tests pass.

146. ✅ **DONE (build loop's own pick) — the third real bug found this way
     from item 141: the itinerary tray's own star buttons collide on a
     recurring event, the same "shared url, distinct occurrences" root
     cause as item 145's RSS guids, just on the client instead of the
     server.** `templates/region.html.j2` and `templates/weekend_hub.html.j2`
     build each event's tray "id" as `item.url or item.title` - unique
     for a one-off event, but every occurrence of a recurring event
     shares the same `url` by design, so every one of them got the
     identical tray id.

     **Confirmed with a real headless-browser test before fixing, not
     assumed:** loaded the real built `/mount-prospect-60056/` page (six
     Farmers Market occurrence cards, one per upcoming Sunday), clicked
     only the Sep 20 card's star, and checked every Farmers Market
     card's `aria-pressed` state afterward - **all six** showed starred,
     from clicking just one. Worse than a cosmetic bug: the tray's
     toggle logic matches by id alone (`tray[i].id === item.id`), so
     starring a *second* occurrence after the first was already saved
     wouldn't add a second planner entry - it would **remove the
     first**, since the toggle sees "id already present" and un-stars
     it. A family trying to plan for two different Sundays could star
     one, star what looks like a second, and silently end up with
     neither saved.

     Fixed by folding `date_iso` into the id (`url|date_iso`) at all
     four tray-item construction sites across both templates, so two
     occurrences sharing a `url` no longer collide - `item.url` itself
     (used separately for the actual link, and for the ICS/Google
     Calendar export) is untouched, so nothing about what a reader
     clicks or exports changed. Re-ran the identical headless-browser
     test against the fixed build: exactly 1 of 6 cards shows starred
     after clicking one, and each card's id is now genuinely distinct.
     No JS test framework exists in this repo, so verified the same way
     items 35/134's client-side fixes were - a real, scripted browser
     check, not a persisted automated test. 402 tests pass (Python
     suite unaffected, since this is template/client-side JS only).

147. ✅ **DONE (build loop's own pick) — item 142's own drift guard had a
     gap, found the same way item 142 found the original problem: by
     checking what it claimed to prevent against the actual file.**
     `tests/test_roadmap_consistency.py`'s regex only matched the literal
     word "DONE" after a checkmark. Item 115 says its own work is
     `✅ VERIFIED` in its body - a real, legitimate synonym already in
     use elsewhere in this file's history - but the regex never caught
     it, so its heading sat unmarked exactly like the 34 items item 142
     already fixed, undetected by the very test meant to catch that.

     Found by grepping every `✅ <WORD>` phrasing actually present in
     `ROADMAP.md`, not by guessing at synonyms: 54 + 23 real uses of
     `DONE`, one `VERIFIED` (item 115), and one unrelated match
     (`✅ JSON-LD`, a checklist bullet, not a numbered-item heading -
     correctly out of this test's scope either way). One real outlier,
     one real fix: added `✅ **Item 100's...` to item 115's own heading,
     and extended the test's regex to `(DONE|VERIFIED)` - an explicit
     alternation, not a generic all-caps match, which would start
     flagging unrelated acronyms like the `JSON` match above.

     Verified the broadened regex actually catches what it's meant to,
     not just passing by construction: reverted item 115's heading,
     confirmed the test failed and named item 115 specifically, restored
     it, confirmed green again. 402 tests pass; verified against a real
     `build_digest.py` run (markdown/test-only change, but the file's
     own convention is to always confirm, not assume).

#### Research pass 2026-09-19 (thirty-third pass)

The last uncovered data-source category, a checkable asymmetry in the
site's own URL structure, and a number worth stating plainly before
anyone builds an argument on it.

| Angle | Finding | Consequence |
|---|---|---|
| **High school athletics** | Shaw Local runs "Friday Night Drive", a weekly football product for the suburban Chicago area. Illinois schedules are published largely **through MaxPreps**, a commercial aggregator; some states' associations publish `.ics`/`.csv` exports directly, Illinois' was not confirmed to | The largest family-relevant category this site does not touch — with a real sourcing constraint (item 148) |
| **Site structure** | `/this-weekend` is merged across all four regions at the hub. `/free` and `/today` exist **only per region** | An entry point users and search both want, missing at the level where it would rank (item 149) |
| **Events UX** | **65%+ of event-site traffic is mobile**; users want multiple entry points by intent — browse a list *or* filter first — and one primary action per screen | The hub already does this for "this weekend". Extending it is cheap (item 149) |
| **Send history** | `data/send_history.json` now exists and holds exactly **one** entry: 2026-09-17, the manual send | Item 114's mechanism works. The claim it enables is currently "one issue" (item 150) |

#### P1 (new)

148. ✅ **DONE — High school sports is the biggest family-relevant
     category the site ignores — investigate the source before assuming
     it is available.** For a family-dense suburb, a Friday night home
     football game *is* the weekend, and local publishers build whole
     recurring products around it: Shaw Local's "Friday Night Drive"
     covers every game in the suburban area, week by week. This site
     carried none of it. District 214 (the shared high school district
     covering Mount Prospect and Arlington Heights), District 211
     (Palatine), and District 207 (Des Plaines' Maine West) are all
     already known entities here — D211's and D207's *academic* calendars
     are configured; none of the four regions' athletics were.

     Did the source investigation the item called for, in order, using
     WebSearch (the sandbox's own network can't reach any of these
     districts' domains directly, confirmed by two failed `WebFetch`
     attempts against `adc.d211.org` and `www.d214.org` — `EGRESS_BLOCKED`
     — the same constraint every fetcher source in this repo already
     works under):

     1. **Checked whether each district's own athletics page publishes a
        calendar feed**, the way D57's academic iCal page was found.
        D211's site (`adc.d211.org`) repeatedly surfaced only the
        already-configured *academic* calendar's RSS URL, never a
        distinct athletics one, across several targeted searches. A
        promising-looking `PageType=21` "ICal Detail" link turned up too,
        but with no way to confirm which calendar it actually points to
        (sports vs. some other district calendar) without fetching the
        page — and per items 109/143's own standard, an unconfirmed guess
        doesn't get wired in just because it looks plausible.
     2. **Checked whether MaxPreps is genuinely the dominant real source**,
        rather than assuming it from the item's own framing. Searched each
        region's actual team by name — "Prospect High School football
        schedule," "John Hersey athletics schedule," "Fremd athletics
        schedule" — and MaxPreps pages outranked every official district
        page in the real results for all three, with district pages
        themselves pointing searchers toward Hudl, IHSA, and NFHS Network
        rather than hosting structured schedule data. This corroborates
        the constraint the item already named, rather than taking it on
        faith.
     3. **Landed on the legitimate fallback the item itself specified**:
        an evergreen guide entry linking to each school's own athletics
        page — not MaxPreps (items 109/143's rule against republishing a
        commercial aggregator's data is about pulling in and re-listing
        its schedule as this site's own content, not linking out to a
        team's page as a citation; this entry does the latter, to the
        *school's own* page, not MaxPreps'). Found and confirmed one real,
        school-specific athletics landing page per region — verified
        present in each WebSearch call's raw result-link list, not just
        the AI summary prose, the same discipline as every other
        real-source fact in this repo:
        - Mount Prospect (Prospect HS, D214): `d214.org/o/phs/page/athletics`
        - Arlington Heights (Hersey HS, D214): `d214.org/o/jhhs/page/athletics`
        - Palatine (Fremd HS, D211): `fhs.d211.org/athletics` (D211 hosts
          each school's athletics section on its own subdomain, not under
          `adc.d211.org`)
        - Des Plaines (Maine West HS, D207): `west.maine207.org/maine-west-athletics/`

     Added one `evergreen` entry per region (`config/regions/*.yaml`) with
     an honest detail line stating plainly that this site has no licensed
     schedule feed for game dates and why, rather than implying more than
     a link actually delivers — matching this repo's `hours: null`
     trick-or-treat honesty pattern rather than overclaiming.

     Verified against a real local build:
     `python scripts/build_digest.py` succeeded with no errors; grepped
     each region's real `docs/<region>/index.html` output and confirmed
     the new "Athletics" card renders with the correct title and a
     correctly-escaped `href` for its school's real URL, in all four
     regions. `python -m pytest tests/ -q`: 406 passed, unchanged — this
     is a config-content-only change (same pattern as item 141's Farmers
     Market addition), verified by inspecting the real generated output
     rather than by adding a new test, since no existing test exercises
     real `config/regions/*.yaml` content directly.

     Not done, and explicitly out of scope here per the item's own
     decision tree: no schedule *data* feed exists for any of the four
     schools (steps 1-2 above ruled that out), so no `sources:` fetcher
     entry, no `.ics` calendar wiring, and no `attendable` game events —
     just the honest evergreen link. If Illinois HS athletics ever gets a
     real open feed (a rules or platform change at IHSA/the districts
     themselves), that would be new information worth re-investigating,
     not a reason to revisit this conclusion on a hunch.

#### P2 (new)

149. ✅ **DONE — Publish `/free` and `/today` at the hub, not only per region.**
     Checked against the live build: the hub carried exactly one merged
     cross-region view, `this-weekend/`, plus `about/`, `sponsor/` and
     the new `trick-or-treat/`. Every region had its own `free/` and
     `today/`; neither existed at the hub.

     That was a gap in two directions at once. For a reader, the current
     UX research is that people want multiple entry points by intent —
     browse a list or filter first — and "free things to do" is one of
     the strongest intents this audience has; the hub already proves the
     pattern works with `this-weekend`. For search, "free things to do
     near me this weekend" is a real query with no page on this site
     pointed at it above the region level, and item 1's whole argument
     was that URL-addressable views beat client-side-only filters
     precisely because they can rank.

     The merge logic existed and was proven — `docs/this-weekend/`
     already did exactly this across four regions. `render_weekend_hub_page()`
     was generalized into `render_merged_hub_page()` (heading, subheading,
     meta description, empty message and canonical slug now parameters
     instead of hardcoded weekend copy), and its template renamed
     `weekend_hub.html.j2` → `merged_hub.html.j2` to match — one template
     now drives all three hub views. Inside the existing per-region
     `views` loop (already computing each region's own `/today` and
     `/free` item lists), a non-empty region's `today`/`free` items are
     now also collected into `hub_today_sections`/`hub_free_sections`,
     the exact same non-empty gate `hub_weekend_sections` already used —
     so there's no separate filtering logic to drift out of sync with the
     per-region views, per the item's own "same code path with a
     different predicate" framing. Each card already carries
     `region_name`/`region_url` since `merged_hub.html.j2`'s card markup
     was untouched — the region label was already there for
     `this-weekend`.

     `/today/index.html` and `/free/index.html` now build at the hub
     root, added to `collect_sitemap_urls()` and `build_llms_txt()`
     (mirroring the existing `## This weekend` GEO section with matching
     `## Today`/`## Free things to do` sections) alongside the existing
     `this-weekend/` entries. The hub landing page keeps the "first
     screen disciplined" requirement literally: rather than two more
     bento tiles (which the item itself called out as exceeding the
     phone above-the-fold budget), `/today` and `/free` are linked from a
     single lightweight pill-link row under the bento grid, each showing
     a live count (`stats.today_count`/`stats.free_count`, computed the
     same way `stats.weekend_count` already was).

     Verified against the real local build (network-fetch-blocked
     sandbox, so against whatever the four regions' config/cached content
     produce): `python scripts/build_digest.py` wrote
     `docs/today/index.html` (3 region sections) and `docs/free/index.html`
     (4 region sections); inspected both directly — correct
     `<title>`/`<h1>`/canonical per page, region `<h2>` headings present,
     events rendered under the right region. Confirmed `docs/sitemap.xml`
     gained both `<loc>` entries and `docs/llms.txt` gained both new
     sections with real per-region links. Confirmed the hub's own
     `docs/index.html` renders `<div class="hub-secondary-links">` with
     working `today/`/`free/` links and real counts (3 and 13 in this
     build). `python -m pytest tests/ -q`: 406 passed (up from 402) —
     added `test_render_merged_hub_page_supports_a_different_slug_and_copy`,
     `test_render_merged_hub_page_shows_its_own_empty_message`,
     `test_build_sitemap_xml_includes_today_and_free_hub_urls`,
     `test_render_hub_page_links_to_the_today_and_free_hub_views`, plus
     assertions extended in the existing llms.txt regions/weekend-links
     test; the four `render_weekend_hub_page` call sites in the existing
     test suite were updated to a small helper wrapping
     `render_merged_hub_page` with the production `/this-weekend` kwargs,
     so they keep testing the exact same behavior under the new,
     generalized signature.

#### P3 (new)

150. ✅ **DONE — State the send count honestly: it is one.**
     `data/send_history.json` exists and works — item 114 shipped and the
     workflow is committing it back. It contains a single entry, the
     manual send of 2026-09-17, and the next scheduled issue is
     2026-09-23.

     Recording this because item 114 justified the file partly as
     sponsor-facing evidence — "we have published N consecutive weekly
     issues" — and that sentence is currently true only with N = 1 and
     the word "consecutive" doing no work. There is nothing wrong with
     that at six days old, but it is exactly the kind of number that
     drifts into a pitch deck rounded up.

     Checked `SPONSOR_KIT.md` directly against `data/send_history.json`
     rather than against memory, as this item asked: it does **not**
     currently make the "N consecutive issues" claim item 114 warned
     about, or state any issue count at all. Nothing to walk back. It
     already independently used the honest framing item 118 argued for —
     "A subscriber count isn't the number to lead with this early — it's
     honestly the weakest one this business has" — so the risk this item
     flagged hadn't actually materialized.

     What it was missing was the other half of that same honest framing:
     it never said *why* there's no track record yet, leaving a void
     where a sponsor could either assume the worst or wonder if a number
     was being hidden. Added one clause, sourced from the file's one real
     entry: "The newsletter itself is new — the first issue went out
     September 17, 2026." A real, verifiable, currently-true fact, not a
     projection — it turns the honest gap into the "ground floor
     opportunity" framing item 118 already established rather than
     leaving it unexplained.

     Verified: `data/send_history.json`'s single entry's `timestamp`
     field (`2026-09-17T03:02:00+00:00`) matches the date now stated in
     `SPONSOR_KIT.md`. Grepped the whole repo for "consecutive" outside
     `ROADMAP.md` itself and confirmed zero other sponsor-facing surface
     (outreach templates, the site's own `/sponsor/` page copy in
     `templates/sponsor.html.j2`) makes an issue-count claim needing the
     same correction. No test references `SPONSOR_KIT.md`'s prose
     directly (confirmed by grep), so no test update was needed for this
     content-only change; `python -m pytest tests/ -q` still passes
     unchanged.

     Still true and still worth watching rather than acting on (nothing
     to do here yet, as of this write-up on 2026-09-19): the 2026-09-23
     run will be the **first ever `schedule`-mode send**, and its
     Buttondown fields are still the unverified guess flagged in
     `send_newsletter.py`'s own docstring. If it fails it will fail
     loudly, which is the design working — but it means the second issue
     could slip a week, turning "one issue" into "two issues, thirteen
     days apart." A future cycle at or after 2026-09-23 should check
     whether that send actually went out before touching this claim
     again.

#### P1 (new)

151. ✅ **DONE — De-risk the 2026-09-23 first `schedule`-mode Buttondown
     send before it runs, not after.** Item 150 flagged this as "watch,
     don't act" since the send is still four days out. But the backlog
     was otherwise empty this cycle (items 148/149/150 all shipped,
     nothing new from the research loop yet), so rather than idle, this
     cycle used the time to re-examine the one already-flagged risk still
     sitting ahead of a real deadline — proactive, not reactive, since
     the whole point of noticing a risk early is being able to act on it
     before it fires.

     `send_newsletter.py`'s own docstring already named the exposure:
     `publish_date`'s exact shape "has never been tried against the live
     API." The sandbox can't call `api.buttondown.com` directly (egress
     blocked, same as every fetcher source) or even fetch
     `docs.buttondown.com` with `WebFetch` (confirmed:
     `EGRESS_BLOCKED`) - but WebSearch can still reach real page content
     through search results, the same channel item 32's D57 calendar and
     item 25's Northwest Neighbor newsletter were found through. Searched
     Buttondown's own published docs for the exact request shape and
     found a real, concrete mismatch: their documented example for
     `scheduling-emails-via-the-api` is
     `{"status": "scheduled", "publish_date": "2024-12-31T12:00:00Z"}` -
     a "Z"-suffixed UTC string. The code was instead sending whatever
     `next_thursday_morning()`'s own `.isoformat()` produced - confirmed
     in a real Python REPL call: `"2026-09-24T07:00:00-05:00"`, an
     America/Chicago offset, not UTC.

     The failure mode this created is worse than a clean error: this
     module's whole docstring premise is "a wrong guess is loud and
     obvious," but a lenient API parser that reads an unrecognized offset
     as if it were UTC wouldn't error at all - it would silently schedule
     the send six-ish hours early, defeating the entire point of item 110
     (hitting the researched Thursday-07:00-Central slot) without
     tripping any alarm.

     Fixed by converting to UTC and formatting to match Buttondown's
     documented shape exactly:
     `next_thursday_morning(now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`
     - same absolute moment either way (confirmed:
     `2026-09-24T07:00:00-05:00` Chicago = `2026-09-24T12:00:00Z`), just
     no longer betting on how permissively Buttondown parses an offset
     it doesn't document.

     Verified: a new test,
     `test_schedule_mode_publish_date_matches_buttondowns_documented_z_format`,
     asserts the exact `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z` shape *and*
     that it's still the correct absolute moment (not just correctly
     formatted) by comparing against `next_thursday_morning(now)`
     converted to UTC independently. `python -m pytest tests/ -q`: 407
     passed (was 406) - the existing schedule-mode test still passes
     unchanged since Python 3.11's `datetime.fromisoformat()` accepts a
     `Z` suffix natively. `python scripts/build_digest.py` still
     succeeds (this script doesn't touch the build pipeline).

     Not resolved by this, and correctly so: this is now a
     docs-verified guess, not a live-API-verified one - no request has
     actually been sent. The docstring was updated to say exactly that,
     honestly, rather than overclaiming confidence a documentation cross-
     check can't fully deliver. The 2026-09-23 run is still the real
     test; a future cycle at or after that date should check
     `data/send_history.json` for the second entry and confirm the
     timestamp lands at the intended Thursday-07:00-Central slot, not
     shifted.

#### Research pass 2026-09-20 (thirty-fourth pass)

Item 139 measured discoverability at zero and listed the signals to
watch. It did not say what to *do* about it, and thirty-three passes have
gone by without anyone asking the most obvious question: this site links
out to six local `.org` domains every single week, and has never once
asked any of them to link back.

| Angle | Finding | Consequence |
|---|---|---|
| **Local link building** | A **.gov or .org in your own geography** is the strongest local link there is; a Chamber link outranks a random authoritative blog for local signals; **5–10 quality local links beat 50 directory listings** | The highest-value backlinks available are the sites this one already promotes (item 152) |
| **Chambers of Commerce** | Membership normally includes a directory listing with a link, and sponsorships carry a sponsor-page backlink | A strong local signal, a member directory full of prospects — and the first recurring cost (item 153) |
| **Nextdoor** | Verified **local** businesses get **two free Business Posts/month**; national and e-commerce excluded; repeated similar content gets flagged | Fits the time budget, with the same eligibility doubt that killed item 143 (item 154) |

#### P1 (new)

152. **Ask the civic sources to link back — the strongest local backlinks
     available, and the ask is reciprocal rather than a favour.** The
     research is unusually consistent here: the most valuable link a
     local site can hold is from a `.gov` or `.org` tied to its own
     geography, and a handful of those outperform dozens of generic
     directory listings. This site's natural candidates are the exact
     domains it already serves: `mountprospect.org`, `mppl.org`,
     `mppd.org`, `dppl.org`, `ahml.info`, `palatinelibrary.org`, and each
     village's own site.

     What makes this different from ordinary link-begging is that the
     value already flows both ways and can be demonstrated. Item 131
     verified **19 of 19** event cards link out to the publisher that
     posted the event; every issue of the newsletter and every region
     page sends readers to the library's own programme page and the park
     district's own registration. The ask is therefore not "please link
     to me" but "we send your events to local families every week and
     link every listing back to you — would you add us to your community
     links page?" Many library and village sites keep exactly such a
     page.

     Needs a short template in `OUTREACH_TEMPLATES.md` — a new §10 —
     leading with what the site does *for them*, naming the specific
     feed being used, and offering to correct or remove anything they
     would rather not see aggregated. That last line matters: it treats
     them as the owner of their own data, costs nothing, and is the
     difference between a partner and a scraper. The build loop can draft
     it; Ryan sends.

     Sequence it **alongside** items 77 and 107 rather than behind them.
     It is the same shape of task — a handful of emails, no cost, no
     recurring time — and unlike the press pitch it is not one-shot: six
     organisations, four towns, and a "no" from one costs nothing. It is
     also the most durable of the three, because a community-links entry
     keeps working every month without being re-sent.

     ⚠️ **Template drafted, sending still needs Ryan — same shape as
     items 25 and 77.** `OUTREACH_TEMPLATES.md` §11 (§10 was already
     taken by item 25's newsletter cross-recommendation template, drafted
     the same session) — one adaptable template with
     `[Organization Name]`/`[Contact Name]`/`[link]` placeholders rather
     than six hardcoded emails, since the actual target list is longer
     than the six domains named above once every region's own park
     district and village/city site is counted (see each region's
     `sources:` in `config/regions/*.yaml` for the full, real list — not
     re-guessed here). Leads with what the site already does for them
     (the 19/19 verified backlink from item 131), asks the actual
     question directly, and offers to correct or remove anything they'd
     rather not see aggregated, per the item's own requirement. Added to
     the "Needs Ryan" table above — sending one at a time, not a batch
     blast, is a human judgment call this loop shouldn't make on its own.

#### P2 (new)

153. **Chamber of Commerce membership — a real backlink, a directory of
     prospects, and the first recurring cost.** Chamber membership
     normally carries a directory listing with a live link, and the
     research names a Chamber link as a stronger local ranking signal
     than a link from a random high-authority site. Four towns means four
     chambers.

     The second benefit is arguably larger than the first and is
     currently missing from every monetisation item in this file: **a
     Chamber's member directory is a list of exactly the businesses items
     94, 118 and 119 are trying to reach**, pre-filtered for the ones
     that already pay to be visible locally. A member emailing members is
     a materially warmer approach than a cold email to a dentist.

     Flagged honestly rather than slipped in, the same way item 78 flagged
     Meta ads: **`BUSINESS_PLAN.md` assumes zero spend**, and Chamber dues
     for a small business are typically a few hundred dollars a year per
     chamber. That is a deliberate exception and the owner's call, not
     the loop's. Two things make it a better first spend than item 78's
     ad test: it produces a permanent asset rather than a one-off burst,
     and it is the only item here that advances findability *and* sponsor
     access at once. It is also the natural pairing with item 119's
     founding-partner rate — join one chamber, in the strongest region,
     and see whether a conversation starts before joining four.

#### P3 (new)

154. **Nextdoor gives two free Business Posts a month — if the site
     qualifies at all.** Nextdoor has appeared here twice as a *pricing*
     anchor (item 95) and as Patch's content source (item 124), never as
     a channel this business could use. Verified businesses get two free
     posts per month into the neighbourhood feed, which is where this
     audience demonstrably is, and the twice-monthly ceiling happens to
     match the time budget precisely.

     The open question is eligibility, and it is the same one that ruled
     out a Google Business Profile in item 143: Nextdoor restricts
     newsfeed posting to **local businesses**, excluding national brands
     and e-commerce. A free, locally-operated website with a real service
     area is plausibly local in the sense they mean, and plausibly not a
     "business" in the sense their verification expects. **Check before
     building anything around it** — and if verification requires
     claiming a physical storefront, stop, for exactly the reason item
     143 gave.

     If it does qualify, the rules argue for restraint anyway: repeated
     similar content gets flagged, so a weekly "here's this week's
     digest" post is the fastest route to being removed. Two posts a
     month, each leading with something genuinely useful — the
     trick-or-treat hours page, the free-events view — is both compliant
     and the better pitch. Posting from a personal account instead of a
     Business Page is explicitly discouraged and should not be a
     workaround anyone reaches for.

     **Checked, as asked — the real blocker turned out different from
     the one this item anticipated.** WebSearch of Nextdoor's own
     verification help pages found the eligibility bar is not the
     storefront/in-person-contact test that ruled out item 143's Google
     Business Profile: Nextdoor explicitly accepts a **home address** for
     a home-based or mobile business (and lets it be hidden from public
     display), so "online-only, real service area" was never the
     obstacle it looked like at first glance.

     The actual requirement is different and, for this business as it
     stands today, a real blocker: verification needs one of a specific
     list of **official business documents** — a government-issued
     business license, an EIN confirmation letter, IRS tax notices, a
     business bank account statement, a business credit report, or a
     Fictitious Business Name Statement (Illinois' term for a DBA). This
     repo has no evidence "Within Ten" has any of them — `SPONSOR_KIT.md`
     itself names Venmo/Zelle/check as the payment methods, which is how
     an individual takes payment, not a registered business with its own
     bank account. So the honest read is: not ineligible the way item
     143 was (nothing here rules it out on principle), but not currently
     qualified either — the gap is paperwork, not the business model.

     That paperwork is real but small, not a reason to give up on it:
     Illinois' Fictitious Business Name Statement (DBA) is filed with the
     county clerk, not the state — **Cook County's fee is $50** (covers
     Mount Prospect, Arlington Heights, and Des Plaines directly; Palatine
     straddles Cook and Lake counties, so confirm which clerk's office
     applies before filing) — but it also requires publishing the
     assumed name in a local newspaper for **three consecutive weeks**,
     starting within 15 days of filing. That is a real cost, a real
     multi-week timeline, and the first step toward accepting sponsor
     payments through anything other than Ryan's personal accounts too —
     which makes this bigger than a Nextdoor decision alone, and squarely
     the owner's call, the same shape as item 153's Chamber dues. Added
     to the "Needs Ryan" table above as a decision, not a task the loop
     can complete: file (or don't) is not something this loop should
     decide or spend on unilaterally.

#### Research pass 2026-09-20 (thirty-fifth pass)

Item 47 settled authentication before the first send. Nothing since has
asked what happens to deliverability when the list **stops** being one
person — which is the entire point of items 77, 94 and 107.

| Angle | Finding | Consequence |
|---|---|---|
| **Volume spikes** | Sudden increases in sending volume are a leading cause of spam placement; providers read them as a spam pattern, and recovery can take weeks | The press pitch targets 100–500 signups **in a day**, against a sending history of one email (item 155) |
| **What builds trust** | **Replies, opens, stars and spam-to-inbox moves** are the signals Gmail and Outlook actually use | A reply is worth more than a click, and the email asks for a click (item 157) |
| **DMARC reporting** | Verified by resolver query: the only `rua` destination on `_dmarc.withintenmiles.com` is `…@inbound.postmarkapp.com` | Deliverability reports for this domain go to **Buttondown**, not to the owner (item 156) |

#### P1 (new)

155. **Growing the list gradually is a deliverability argument, not just
     a strategy preference — and it re-ranks the outreach items.**
     `withintenmiles.com` is days old and has sent exactly one email, to
     one person (item 150). Item 77's press mention is designed to
     produce 100–500 subscribers in a single day, and the next Thursday
     issue would then go to all of them at once. Sudden volume spikes are
     a leading cause of spam placement, and a domain that trips that
     pattern can spend weeks recovering.

     **Calibrating this honestly, because the obvious research
     overstates it here.** Most warm-up guidance is written for cold
     outreach from your own IP, and IP reputation is the bigger half of
     it. Buttondown owns the sending IPs and their reputation, which this
     business inherits — so the exposure is the **domain** reputation
     that DKIM and DMARC align to, not an unwarmed IP. Google's bulk
     sender thresholds also sit at 5,000/day, far above anything this
     list will do. The risk is real and worth planning around; it is not
     the catastrophe a cold-email article would imply, and nobody should
     delay the press pitch out of fear of it.

     What it does change is **ordering**, and it happens to reinforce an
     ordering this file already recommends for different reasons. Items
     94 (trade a mention with local businesses) and 107 (ask three
     Facebook admins) grow the list in tens over weeks; item 77 grows it
     in hundreds in a day. Running the gradual ones first means the
     press-driven spike lands on a domain with several real sends behind
     it rather than one. That is a second, independent argument for a
     sequence already argued from repeatability — and when two unrelated
     lines of reasoning pick the same order, it is worth following.

     Concretely, and all of it free: keep the weekly cadence unbroken
     from now (item 150's "one issue" is the actual problem), and after
     any large influx resist the urge to immediately mail everyone
     something extra. The welcome email (item 106) does real work here
     too — it is a single, wanted, high-open message to each new
     subscriber as they arrive, which is exactly the gradual, engaged
     sending pattern providers reward.

#### P2 (new)

156. **The owner receives no deliverability reporting at all.** Resolver
     query against `_dmarc.withintenmiles.com` returns a single
     aggregate-report destination:
     `rua=mailto:940f…@inbound.postmarkapp.com`. That is Buttondown's
     collector, created when the managed sending domain was set up. It is
     not wrong — but it means every DMARC aggregate report about **this
     domain** goes to the vendor, and none to Ryan.

     The consequence only bites when something goes wrong, which is
     precisely when it matters: if alignment breaks, if a provider starts
     quarantining, or if someone spoofs the domain, the evidence exists
     and is invisible here. Given item 155's spike risk, the first weeks
     after a press mention are exactly when a second pair of eyes is
     worth having.

     `rua` accepts a comma-separated list, so a second destination can be
     added alongside Buttondown's rather than replacing it. Two honest
     caveats: raw DMARC XML is unreadable, so this is only useful pointed
     at a free digest service that emails a plain-English summary; and
     because the destination is on a different domain from the DMARC
     record, it needs the **external destination verification** TXT
     record that the standard requires — the same mechanism Buttondown
     already satisfies for its own address. So it is a two-record change,
     not a one-line one, and worth saying so rather than discovering it
     mid-edit. P2 because nothing is currently broken; it is instrumentation
     for the period when something might be.

     **Researched the actual "second destination" rather than leaving
     this as a generic to-do — and found the two-record framing above is
     more than this site actually needs.** `withintenmiles.com` is
     already on Cloudflare DNS (confirmed earlier this session, during
     the Google Search Console DNS work — the two authoritative
     nameservers are Cloudflare's). Cloudflare has its own free **DMARC
     Management** feature, on every plan including the free tier:
     enabling it from the dashboard (Email → DMARC Management) adds
     Cloudflare's own `rua` address to the existing record automatically
     — no hand-written TXT record, and no separate external-destination-
     verification step, since Cloudflare is the one editing its own DNS
     zone. Confirmed via search that it's additive by design (existing
     destinations, including Buttondown's, are preserved alongside
     Cloudflare's own) — and reports render as a readable dashboard
     inside Cloudflare, not raw XML, satisfying the "needs to be
     readable" caveat above for free, with no third-party account to
     create.

     Worth one honest caveat rather than presenting this as risk-free:
     search also surfaced a real Cloudflare Community thread describing
     the feature altering an existing DMARC record unexpectedly for at
     least one user. Cloudflare's own docs say existing entries are
     preserved, but that community report is real too — worth Ryan
     checking `_dmarc.withintenmiles.com` after enabling to confirm
     Buttondown's own `rua` destination is still present, not assuming
     it from the feature's description alone.

     **Postmark DMARC Digests** (`dmarc.postmarkapp.com`) is the fallback
     if Cloudflare's feature turns out not to fit: free, no account
     required (confirmed — you don't need to be a Postmark customer),
     under 2 minutes to set up, weekly plain-English email summaries,
     no dashboard to check. Worth naming specifically because Postmark
     is already the vendor behind Buttondown's own existing `rua`
     collector, per this item's own resolver finding — a second Postmark
     product, not a new vendor relationship.

     Added to the "Needs Ryan" table above with the Cloudflare path as
     the primary recommendation and Postmark as the named fallback — a
     DNS-adjacent dashboard action only Ryan can take, same as items
     47/93 before it.

157. ✅ **DONE — Ask for a reply, not just a click — the email's one call
     to action optimises for the weaker signal.** The combined email's
     single CTA is "See everything in Mount Prospect", a link. Clicks
     are good. But the signals providers actually use to build sender
     trust are **replies, opens, stars and spam-to-inbox moves**, and a
     reply is among the strongest of them — it is the clearest possible
     evidence that a human wanted the message.

     The site now has everything needed to earn one and uses none of it:
     replies reach a real inbox (item 93), item 132 proposed a corrections
     path, and item 106's welcome email is slated to invite exactly this.
     Extending it to every issue is one line in the email footer, and it
     should ask for something specific rather than "let us know what you
     think" — *"Know about something we missed? Hit reply, we read every
     one"* gives a reader a concrete reason and an easy action.

     Keep the hierarchy intact while doing it: current design research is
     consistent that one dominant CTA per screen outperforms, so the
     reply prompt belongs in the footer as a quiet secondary line, not as
     a competing button. Done that way it serves three separate things
     at once — deliverability (item 155), the corrections posture that
     distinguishes this from generated local content (items 131/132), and
     the resident-supplied events that are the one category no competitor
     can aggregate.

     Added the exact line to both `templates/email_digest.html.j2` (the
     per-region send) and `templates/combined_email_digest.html.j2` (the
     all-regions send) as its own footer row, above the existing "Within
     Ten — local events..." tagline row, matching the same muted 12px
     footer styling rather than introducing a new visual weight — no new
     button, no new color, nothing competing with the real CTA above it.
     No mailto: link needed — Buttondown/Cloudflare Email Routing
     already makes a plain reply work (item 93), so this is copy only.

     Verified against the real generated output, not just the template
     source: `python scripts/build_digest.py` then grepped the actual
     `docs/mount-prospect-60056/email-send.html` and
     `docs/combined-email-send.html` for the line - present, correctly
     rendered, in both. Added
     `test_render_email_digest_asks_for_a_reply_in_the_footer` and
     `test_render_combined_email_digest_asks_for_a_reply_in_the_footer`.
     `python -m pytest tests/ -q`: 409 passed (was 407).

#### Research pass 2026-09-20 (thirty-sixth pass)

A deeper batch, because the backlog is genuinely thin for the first time
and the reason is worth stating.

Re-audited: **156 numbered items, 136 done, 2 skipped, 18 open — and
only 3 of those 18 are stale**, down from 22 when item 142 measured it
four passes ago. The reconciliation worked. But look at what is actually
left: 19, 22, 25, 35, 38, 48, 77, 78, 84, 130, 152–156. Item 84 is a
rejection kept for the record. Items 77, 78, 130, 152, 153 and 154 are
**Ryan's** — a press email, a spend decision, a privacy decision, six
outreach emails, a membership, an eligibility check. **The build loop is
close to out of work, and the remaining bottleneck is almost entirely
human.** That shapes what this pass should produce, and items 158–161 are
deliberately build-loop-shaped.

| Angle | Finding | Consequence |
|---|---|---|
| **Head-term re-check** | Eventbrite still dominates, but **Tripadvisor and Yelp now rank too — with evergreen attraction lists, not events**. `experiencemountprospect.org` also ranks | The query mixes two intents; this site answers only the dated one (item 158) |
| **Evergreen vs. dated** | Guides accumulate backlinks and rankings over years; **a new URL per event instance dilutes authority**; recurring events should keep one permanent URL updated in place | The guides are the compounding asset, and the rule needs writing down before items 112/141 (items 158/160) |
| **Experience Mount Prospect** | Configured as a source but returns **403 Forbidden** — and it ranks for the head term this site is chasing | A blocked feed and a competitor are the same organisation (item 161) |

#### P1 (new)

158. **Build an evergreen "things to do in {town}" page per region — the
     head term is two queries and the site answers one of them.**
     Re-checking "things to do in Mount Prospect IL this weekend" turned
     up something the earlier checks missed: alongside Eventbrite,
     **Tripadvisor and Yelp now rank**, and neither lists a dated event.
     They rank with standing attractions — museums, venues, places that
     are there every week.

     So the query has two populations behind it: people asking "what is
     on this Saturday" and people asking "what is there to do here at
     all." This site is excellent at the first and silent on the second,
     and the second is the half that **compounds**. The research is
     unambiguous: "things to do" guides accumulate backlinks, search
     history and rankings over years, while dated listings capture
     traffic for days. A weekly digest can never out-rank a page that has
     been collecting authority since 2015 — but an evergreen page can,
     and it is the natural home for item 152's incoming civic links.

     The civic-source-only discipline makes this *harder* and *better*
     than Tripadvisor's version. Harder because Yelp can list every
     restaurant and this site will not. Better because the honest answer
     for a family — the park district's pools and preserves, the
     library's makerspace, the historical society's museum, Randhurst,
     the downtown blocks — is exactly what the existing sources already
     describe, and it is genuinely more useful than a ranked list of
     attractions written by somebody who has never been.

     Structurally it should follow the guides, which are the proven
     pattern here: one stable slug per region (`/things-to-do/`), the
     town named in title, headings and body, and **no year in the URL**
     ever. Seed it from the four existing guides' evergreen entries
     rather than writing new prose — the material is already in config.

     🟢 **Shipped, 2026-09-20.** `/things-to-do/` now builds for every
     region: `build_things_to_do_items()` unions each region's evergreen
     entries with every item across all its guides, deduped by url
     (falling back to title) so a source repeated across guides — the
     park district's own site, say — shows once, not four times. No new
     prose, per the item's own instruction: every entry is material
     already curated for evergreen/guides. One stable slug, no year in
     the URL, same FAQ/JSON-LD treatment as a guide page. Wired into
     nav on every region page, `sitemap.xml`, and a new "Things to do
     (evergreen)" section in `llms.txt` alongside the existing dated
     sections. 6 new tests; 415 passed.

#### P2 (new)

159. **Give the build loop standing work for when the queue empties:
     verification, not features.** With 18 items open and most of them
     Ryan's, the build loop will shortly have nothing queued — and the
     failure mode for an idle build loop is inventing features, which
     `DESIGN_PRINCIPLES.md` (item 103) exists to prevent and which item
     124's competitors demonstrate the cost of.

     The useful alternative is already implied across this file and has
     never been stated as standing work. In priority order: **re-verify
     the source feeds** (Experience Mount Prospect 403s, Downtown Mount
     Prospect returns 200 with zero items — both recorded in config
     comments and both quietly degrading the product); **close the
     remaining stale-open markers** item 142 found; **re-run the
     accessibility and performance audits** against the current build;
     and **check every external link still resolves**, since civic sites
     reorganise constantly and a dead link is the one error that makes
     this product look unmaintained.

     None of that adds surface area, all of it protects the claim items
     131 and 152 rest on — that every listing is real and traceable to
     its source. Worth writing into the working agreements as the default
     when no P1 is open, so "nothing queued" never means "invent
     something".

     🟢 **Shipped, 2026-09-20.** Written into "Working agreements for
     autonomous iteration" as a standing default, in the same priority
     order this item lays out, plus a first real pass run the same day
     — see that section for the full write-up and findings. Headline
     result: no regression found anywhere checked, and a genuinely new
     technique discovered along the way — Lighthouse CI runs locally in
     this sandbox after all (`CHROME_PATH` just needs pointing at the
     pre-installed Chromium; the plain `npx lhci autorun` CI uses has no
     reason to set that env var since GitHub's runners already have a
     browser on `PATH`), so a future pass can get real, current
     accessibility/best-practices numbers instead of waiting for CI.

160. **Write down the permanent-URL rule before items 112 and 141 break
     it.** Checked: no year-stamped directory exists anywhere under
     `docs/` today, and the trick-or-treat page item 101 shipped lives at
     `/trick-or-treat/` rather than `/trick-or-treat-2026/`. That is
     correct and it happened by good instinct rather than by rule.

     Two queued items will test it. Item 112 wants a seasonal calendar
     with Restaurant Week, holiday lights and summer camps; item 141
     wants recurring events expanded into dated occurrences. The obvious
     implementation of either produces `/restaurant-week-2027/` or a URL
     per market date, and the research is explicit that this is the wrong
     trade: **every new URL for the same recurring thing dilutes the
     site's authority**, where updating one page in place compounds
     backlinks, search history and rank.

     The rule is one line and belongs in `DESIGN_PRINCIPLES.md`:
     *seasonal and recurring pages keep one permanent URL forever; the
     year lives in the content, never in the path.* A test asserting no
     generated path matches `\d{4}` costs almost nothing and makes the
     rule enforceable rather than aspirational.

     🟢 **Shipped, 2026-09-20.** Added a "Permanent URLs" section to
     `DESIGN_PRINCIPLES.md` stating the rule and tying it to the same
     "restraint over accumulation" argument the rest of that file
     already makes, plus
     `test_collect_sitemap_urls_never_contains_a_year` — it asserts no
     URL `collect_sitemap_urls()` emits contains an isolated 4-digit
     run (matched with digit-boundary lookaround so a 5-digit ZIP in
     the path, e.g. `mount-prospect-60056`, doesn't false-positive).
     416 tests pass. Items 112 and 141, whenever they're picked up,
     now have a real test to fail against if they reach for a
     year-stamped URL.

161. **Experience Mount Prospect is a blocked feed and a ranking
     competitor — and item 152 can address both at once.**
     `config/regions/mount-prospect-60056.yaml` records that
     `experiencemountprospect.org` returns **403 Forbidden**: the domain
     responds, the request is refused. It also appears in the live
     results for the exact head term this site is chasing. It is the
     village's own tourism arm, so it is neither a rival to be beaten nor
     a source to be scraped around.

     That makes it the single best first target for item 152's link-back
     email, because one conversation can plausibly resolve three things:
     a `.org` backlink from a locally-authoritative domain, permission or
     a working URL for the feed that currently 403s, and a relationship
     with the organisation whose events this site most wants. The ask
     writes itself and is entirely honest — *we send readers to your
     events every week and link every listing back to you; your calendar
     blocks our fetcher, and we would rather ask than work around it.*

     "We would rather ask than work around it" is worth saying out loud
     to them. A 403 is a polite no from a server, and respecting it while
     asking a human is the difference between the aggregator this
     business wants to be and the one items 109, 131 and 143 keep ruling
     out. Same treatment for Downtown Mount Prospect, whose feed returns
     200 with zero matching items — a broken integration rather than a
     refusal, and equally fixable by asking.

     🟢 **Drafted, 2026-09-20.** Both emails written and ready to send in
     `OUTREACH_TEMPLATES.md` §12a/12b, added to the Needs Ryan table.
     Each makes the honest three-part ask this item describes — fix the
     feed, add a link, open a relationship — rather than splitting them
     into separate emails. Fixed first, so the ask is credible: the
     fetcher's `USER_AGENT` was still `60056Weekly/1.0`, a pre-pivot
     name pointing at the GitHub repo rather than the live site — now
     `WithinTen/1.0 (+https://withintenmiles.com/)`, so a source asked
     to allowlist it is allowlisting something that identifies itself
     as the actual product the email describes. Sending itself needs
     Ryan, per the standing rule that a real email to a real
     organization isn't the build loop's to send.

#### Research pass 2026-09-20 (thirty-seventh pass)

The periodic AI-citation re-check, and it is decisive rather than
another adjustment. Item 22 has now been recalibrated three times —
`llms.txt` does not work, AI Overviews reach ~7% of local intent rather
than half (both item 98), and now the citation data itself.

| Angle | Finding | Consequence |
|---|---|---|
| **Citation concentration** | Synthesised across ~680M citations: the **top 15 domains hold ~68% of AI citation share, Reddit alone ~40%**. ChatGPT's largest single source is **Wikipedia at 47.9%**, and it cites brands **0.59%** of the time | A four-town local site is not going to win AI citation share. Stop treating it as a goal (item 162) |
| **Recency** | Pages updated within three months average **~6 citations against 3.6** for stale pages; AI models weight recency strongly | The one lever where this site structurally beats every static competitor — and it is free and already running (items 162/163) |
| **Freshness signals** | Checked the live build: `dateModified` **is** emitted in JSON-LD and `lastBuildDate` in the RSS feed. **Nothing on the page tells a human reader when it was updated** | The claim is machine-readable and invisible to the person it would persuade (item 163) |

#### P1 (new)

162. **Close item 22 as a goal and keep only the parts that earn their
     place on other grounds.** "Get cited by AI search, as a deliberate
     strategy" has been this file's standing ambition since the early
     passes. The citation data makes the honest verdict clear: AI
     citation is far more concentrated than organic search, the top 15
     domains take roughly two-thirds of it, **Reddit alone takes about
     40%**, and ChatGPT's single biggest source is Wikipedia. A site
     covering four suburbs is not going to appear in that distribution,
     and three consecutive recalibrations of the same item is enough.

     Closing it is not the same as undoing the work, and the distinction
     matters because most of what shipped under item 22 is genuinely
     good — it was just justified by the wrong argument:

     - `robots.txt` naming GPTBot, ClaudeBot, OAI-SearchBot and the rest
       **stands**: allowing crawlers that exist costs nothing.
     - schema.org `Event` **stands**, on ordinary rich-result grounds —
       item 120 confirmed its placement is already correct under the
       2026 "primary content purpose" rule.
     - Entity clarity (`Organization` schema, the About page, item 116's
       stable venue names) **stands**, because it helps ordinary local
       search, which is the channel that can actually be won.
     - `llms.txt` stays generated and uncounted, per item 98.

     What goes is the *framing* — and with it the temptation to spend
     another pass optimising for a channel whose own numbers say a local
     publisher cannot reach it. Resolve item 22's own heading as closed,
     referring here for why, rather than leaving it open to attract more
     work. (Described rather than quoted: item 142's consistency test
     reads a done-marker in any item's body as that item marking
     *itself* done, and it is right to — the two are indistinguishable
     by regex, and weakening the guard just to quote a marker would
     cost more than the rewording.)

     The one durable finding to carry forward is recency, and it is
     genuinely good news: **pages updated within three months earn
     roughly 6 citations against 3.6 for stale ones**. This site rebuilds
     several times a week, automatically, forever. That is a structural
     advantage over every static "best things to do" list it competes
     with, it costs nothing, and it is currently unclaimed. Item 158's
     evergreen pages should lean on it explicitly.

     🟢 **Shipped, 2026-09-20.** Item 22's own heading now reads
     `✅ CLOSED AS A GOAL`, with a closing note appended in place
     explaining the citation-concentration data and confirming which
     shipped pieces stand on other grounds. No code changed — this is
     the roadmap-bookkeeping half of the item; the recency lever it
     asks to carry forward is item 163's job.

#### P2 (new)

163. **Show a human when the page was last updated.** Checked against the
     live build: `dateModified` is present in JSON-LD
     (`2026-09-20T14:54:40Z` on the Mount Prospect page) and the RSS feed
     carries `lastBuildDate`. Neither is visible to a reader. The
     strings "Updated" and "updated" appear nowhere in the rendered
     page.

     That is the wrong way round for this product specifically. The whole
     differentiation established in items 124 and 131 is that this is
     *current* — pulled automatically from live civic feeds, unlike a
     guide written once in 2023 and quietly rotting. A visitor comparing
     this page against Tripadvisor's evergreen list has no way to tell,
     and the one fact that would settle it is sitting in a `<script>` tag.

     One line, near the listings: *Updated automatically — last checked
     Sunday 20 September.* Local date, not a timestamp; readable, not
     precise. It reinforces the provenance line item 126 asked for, it is
     the human-facing half of the same claim the schema already makes,
     and it is exactly what item 158's evergreen pages need to avoid
     looking like every other static list.

     **One honest caution before shipping it.** `dateModified` currently
     tracks the *build*, not the *content* — it churns every rebuild even
     when nothing changed, and search engines are known to discount
     timestamp churn without substantive change. So the visible line
     should say what is actually true ("last checked"), and the schema's
     `dateModified` is arguably better bound to the last build in which
     that region's items *changed*. The honest version is both more
     accurate and more defensible than a date that moves for no reason.

     🟢 **Shipped, 2026-09-20 — the visible line only, per the item's
     own caution.** A new `.freshness-note` line — *"Updated
     automatically — last checked [region-local weekday, month, day]."*
     — now renders near the top of every region page view (main,
     weekend/today/free, guides, directory, things-to-do), right after
     the answer block and well above the footer's existing
     `Generated ...` line nobody scrolls to. Computed in
     `render_region_page()` from the region's own local date via the
     existing `region_local_date()` helper, not a raw UTC timestamp.
     Deliberately says "last checked," not "last updated" — true
     either way, since a build did run, without implying content
     changed when it may not have. The schema-side half of this item
     (binding `dateModified` to the last build that actually changed a
     region's items, rather than every rebuild) is real but bigger —
     it needs tracking previous-build state this pipeline doesn't keep
     today — and is deliberately left open rather than bundled in here;
     `dateModified` keeps tracking build time for now, which is what it
     already did before this item. Verified against a real build (the
     line renders with the correct date on all 7 checked page types)
     and confirmed clean against the same Lighthouse pass item 159/its
     follow-up already extended to those pages. One new test
     (`test_render_region_page_shows_a_human_readable_freshness_note`).
     417 tests pass (was 416).

#### P3 (new)

164. **Recording the Reddit tension without reopening it.** Reddit takes
     roughly 40% of all AI citations and is Perplexity's single largest
     source at 46.7%. Item 84 examined local subreddits as a discovery
     channel and **rejected** them: the 90/10 norm requires 9–19
     non-promotional contributions between promotional posts, 61% of the
     relevant subreddits ban self-promotion outright, and the cost falls
     on the one resource `BUSINESS_PLAN.md` says the owner does not have.

     That rejection still holds, and this finding does not overturn it —
     it changes the size of the prize, not the price. Worth writing down
     anyway for two reasons. First, so a later pass discovering the 40%
     figure does not treat it as new information and reopen a settled
     decision. Second, because the reasoning has an exception worth
     naming: the cost of Reddit is *sustained participation*, so if the
     owner ever becomes a genuine participant in a local subreddit for
     his own reasons, the calculation changes completely — it is only
     expensive as a marketing task.

     No action. Filed so the next pass to find this number can skip
     straight to the conclusion.

#### Research pass 2026-09-21 (thirty-eighth pass)

Item 159 observed that the remaining bottleneck is human. This pass
counted it: **six open items are owner actions** — 77 (press pitch), 78
(Meta ads), 130 (name on the About page), 152 (link-back emails), 153
(Chamber membership), 154 (Nextdoor eligibility). None has moved in a
week, and four of the six were added by this loop in the last four
passes.

That is worth naming plainly as a problem with **this loop**, not with
the owner. `BUSINESS_PLAN.md`'s founding constraint is "full-time job +
two small children → near-zero ongoing weekly time." A research process
that adds human tasks faster than one person can complete them is not
producing leverage; it is producing a queue, and a six-item queue in
front of someone with an hour a month is functionally the same as no
queue at all.

| Angle | Finding | Consequence |
|---|---|---|
| **The owner queue** | Six open owner actions, four added in four passes, none completed in a week | The loop is generating faster than the constraint allows (item 165) |
| **Expansion candidates** | Wheeling **38.3k, 39% of households with children under 18**; Elk Grove Village 32.8k but **shrinking**; Rolling Meadows 24.2k; Prospect Heights 16.1k and oldest | A concrete answer to "which town next", and real build-loop work (item 166) |
| **Demographic detail** | Wheeling is **28.1% Hispanic**; `BUSINESS_PLAN.md` cites ~$102K median household income for 60056 where village-level census figures show **$84,353** | One content question and one number worth reconciling (item 167) |

#### P1 (new)

165. **Cut the owner queue to one thing, and say which.** Six items now
     wait on Ryan. Ranked by this file's own reasoning they are not close
     to equal, and presenting them as a list invites the outcome that has
     actually happened — nothing gets picked.

     The ranking, from arguments already made here rather than new ones:

     1. **Item 130 — put a real name on the About page.** It takes
        minutes, costs nothing, and **items 77, 152 and 153 all get
        weaker without it**: a reporter will not write about an anonymous
        site, a library will not link to one as readily, and a business
        owner does not buy from one. It is the only item that is a
        prerequisite for others.
     2. **Item 152 — the link-back emails.** Six emails, no cost,
        repeatable, and the most durable result (a community-links entry
        keeps working). Item 161 already names the best first target.
     3. **Item 77 — the press pitch.** Highest single yield, but
        one-shot, and item 155 argues it should follow gradual list
        growth rather than lead it.
     4. Items 153, 154, 78 — **park them.** Two involve money and one is
        an eligibility question about a channel that may not accept this
        site at all. None should compete for attention with the three
        above.

     The concrete change is to `ROADMAP.md`'s Needs Ryan block: show
     **one** "next action" with its reason, and move the rest to a
     collapsed "after that" list. A queue of six reads as a backlog; a
     single named next step reads as a decision already made. And it is
     the loop's job to make that decision, having done the research —
     handing over six ranked options is handing back the work.

     Standing rule worth adding to the working agreements: **the research
     loop may leave at most three open owner actions.** Beyond that, it
     re-ranks and parks rather than appending. Build-loop items are
     unbounded because the build loop has unbounded hours; owner items
     are bounded because the owner does not.

     🟢 **Shipped, 2026-09-21.** The "Needs Ryan" section now leads with
     one named **Next action** (item 130, exactly as ranked here), an
     **After that** list of two (152+161 folded together, then 77),
     and an explicit **Parked** list (153, 154, 78) with a one-line why
     each — real, not deleted, just visibly deprioritized. The smaller
     no-decision items (69, 106, 25, 156) got their own
     no-ranking-needed group rather than competing with the three real
     decisions above, and the time-boxed Sept-23 check stayed separate
     since it isn't a decision at all. The standing rule is now in
     "Working agreements for autonomous iteration," worded as "at most
     three open owner *decisions*" to match how this restructuring
     actually counts them (the small housekeeping items and the
     time-boxed check don't count against the cap, matching this
     item's own reasoning that they don't compete for attention).

#### P2 (new)

166. **Wheeling is the next region, and the numbers are not close.**
     `BUSINESS_PLAN.md` says each new region costs "almost nothing" —
     one YAML file — and item 159 found the build loop nearly out of
     work. Expansion is the third option alongside features and
     verification, and it is the one that widens the surface that can
     rank and the audience that can subscribe.

     On the data, for a site whose audience is families:

     - **Wheeling — 38,329, and 39% of households have children under
       18.** Largest of the candidates and the strongest family signal.
     - **Elk Grove Village — 32,812, but declining ~0.6%/yr.** Fine on
       income ($94,175 median household) and a reasonable second.
     - **Rolling Meadows — 24,200.** Middling on both counts.
     - **Prospect Heights — 16,058, and the oldest of the four** (18.7%
       over 65 against 21.1% under 18). Weakest fit for this product.

     One strategic note to weigh rather than ignore: Wheeling, Prospect
     Heights and Rolling Meadows are all inside **Journal & Topics'**
     coverage area (twenty-ninth pass). Expanding into them increases
     overlap with the publication item 125 already flagged as a
     competitor-and-press-target. That is an argument for the honest
     framing item 125 recommends, not against expanding — but it should
     be a decision rather than a surprise.

     The work is exactly the established pattern: find the village,
     library, park district and school district feed URLs, write one YAML
     config, let the fail-soft fetcher handle what is unverified. Item
     138's lesson applies — include a school district from the start
     rather than discovering the gap later.

     🟢 **Shipped, 2026-09-21.** `config/regions/wheeling-60090.yaml`
     added — Village of Wheeling, Indian Trails Public Library District,
     Wheeling Park District, Wheeling CCSD 21, and a Township High
     School District 214 (Wheeling High School) athletics link, plus
     `evergreen`/`guides` content (fall-family-guide,
     birthday-parties-and-kids-classes, new-to-town) built from real,
     WebSearch-sourced civic facts (utility billing, library-card
     registration, Park District residency verification), same
     civic-source-only discipline as the other four regions. No
     confirmed live source counts yet — this sandbox's network can't
     fetch these sites directly, so (like every region's first pass)
     that awaits the next real GitHub Actions build. Item 138's lesson
     applied from the start: the school district is in this region's
     first commit, not a later gap-fill. Verified end-to-end against a
     real local build: the region generates every page type including
     item 158's `/things-to-do/` page (12 items, seeded automatically
     from its own evergreen/guides content with zero extra code), and
     `build_nearby_regions()`/`build_region_map()` both generalized to
     5 regions with no code change - confirmed the "within ten miles"
     premise actually holds for a real visitor here too: Wheeling's
     three nearest neighbors compute to 3.9/4.0/5.9 miles. Coordinates
     are a Wikipedia-cited town-center point, not a geocoded Village
     Hall address (no geocoding access from this sandbox) - said so in
     the config's own comment rather than implying false precision.
     Found and fixed a real test gap along the way:
     `test_every_region_tagline_names_at_least_two_real_venues` has a
     per-region expected-venues dict that doesn't auto-discover new
     regions, so it correctly failed with a `KeyError` until Wheeling's
     entry (Heritage Park, Chicago Executive Airport) was added - a
     genuine test working exactly as designed, not a bug in the test.
     417 tests pass (was 417 before too - one region added, one
     dict entry added to keep the same test passing for the same
     reason). Item 167's Spanish-language question and income-figure
     reconciliation are separate, deliberately not bundled in here.

     🟢 **First real build checked, 2026-09-21 (same day, next hourly
     firing).** Real GitHub Actions run `35549497769` gave this
     region's actual first live test, and the header comment above is
     now rewritten with the confirmed results rather than the original
     "none of this is confirmed yet" caveat: the **Village of Wheeling
     source worked on the first real try** (4 items, the guessed
     `Calendar.aspx` html_events page) - the second time in this repo a
     search-found *page* rather than a search-found *feed URL* has
     worked first try (School District 57's history in the Mount
     Prospect config is the first). Both **Wheeling Park District and
     Wheeling CCSD 21 came back a real 403 Forbidden** - the Park
     District's pattern-matched Tribe Events ICS URL didn't hold, and
     the school district's calendars page is blocked outright. Indian
     Trails Public Library hit a genuine 15-second connect timeout,
     a softer and more ambiguous signal than either outcome above -
     worth a second look once there's a live-fetch-capable environment
     to find that library's own libnet.info feed URL, rather than
     assuming the timeout means the page is unreachable. Each source's
     own block in the config now carries a one-line confirmed/broken/
     unconfirmed note, matching every other region's per-source
     annotation convention. No second guess attempted this pass for
     the two 403s - a 403 (unlike a 404) doesn't distinguish "wrong
     plugin" from "blocked like Mount Prospect's Village site," and
     guessing again without a stronger signal would carry the same risk
     as the first guess.

#### P3 (new)

167. **Two numbers worth getting right before they end up in a pitch.**

     **Wheeling is 28.1% Hispanic.** If item 166 proceeds, that raises a
     content question this site has never faced: it aggregates
     English-language civic feeds and publishes in English only. Many
     village and library sites publish Spanish-language programming
     information, and a digest that silently drops it would under-serve
     more than a quarter of the town. Not a blocker and not a reason to
     skip Wheeling — but worth deciding deliberately rather than by
     default, and worth checking whether the sources themselves offer
     Spanish feeds before assuming they do not.

     **`BUSINESS_PLAN.md` cites ~$102K median household income for
     60056; village-level census figures show $84,353.** Both may be
     right — ZIP-code and municipal boundaries differ, and the sources
     are different years — but the plan's number came from ZIP profile
     sites and the gap is large enough to matter if it is ever repeated
     to a sponsor. `SPONSOR_KIT.md` describing the audience as
     higher-income than it is would be the kind of small overstatement
     that costs credibility precisely when it is being checked. Worth
     reconciling once, citing the source and the year, and using the
     conservative figure where they disagree.

     🟢 **Income figures reconciled, 2026-09-21.** The $84,353 figure
     turned out to be the stale one, not the accurate one — it's Mount
     Prospect's 2020 Census / older ACS vintage, and the current ACS
     2024 5-year estimate is **$101,720** (Data USA and Census Reporter
     agree), almost exactly what `BUSINESS_PLAN.md` already said. "Use
     the conservative figure where they disagree" turned out to be the
     wrong instinct here: the older number isn't more conservative, it's
     just older, and blindly preferring it would have replaced an
     accurate figure with a stale one. Checked all three other regions
     the same way (Data USA, 2024) while in there, since `SPONSOR_KIT.md`
     makes the same kind of claim for each: Arlington Heights is
     **$116,723**, not the ~$100K it said (meaningfully understated);
     Des Plaines is **$97,875**, not ~$87K (also understated); Palatine
     is **$97,819** median, not the ~$125K it said - that number turned
     out to be Palatine's *average* household income ($124,160),
     conflated with the *median* the rest of the sentence was using, a
     real and more consequential error than the one this item originally
     flagged. National median updated to the Census Bureau's own 2024
     figure ($83,730) for the comparison baseline. Both
     `BUSINESS_PLAN.md` and `SPONSOR_KIT.md` updated with the corrected
     numbers and cited source/year; `BUSINESS_PLAN.md` keeps the
     original figure in place with a reconciliation note appended rather
     than silently rewriting the historical record. Wheeling's own
     figure is a known, explicitly-flagged gap - not sourced or added to
     `SPONSOR_KIT.md`'s table this pass, since guessing it would repeat
     exactly the mistake this reconciliation just fixed.

     🟡 **Spanish-language question researched, not decided, 2026-09-21.**
     Checked whether Wheeling's own sources already offer Spanish
     content, per the item's own instruction, before treating this as
     an all-or-nothing feature question: **Indian Trails Public Library
     District has a real, live "Servicios en Español" page**
     (`indiantrailslibrary.org/services/adults/servicios-en-espanol/`),
     bilingual staff, and Spanish-language materials/programs (Spanish
     conversation practice, ESL resources, a bilingual collection). The
     Village of Wheeling's own site shows no equivalent Spanish-language
     section by search. This changes the shape of the eventual decision
     from "would there even be Spanish content to include" to "there's
     at least one confirmed real source, if a bilingual treatment is
     ever worth building" - but building anything from it (a Spanish-
     language digest, a translated page, a note on which sources have
     Spanish resources) is a real scope and design decision this pass
     deliberately leaves open rather than acting on unprompted, exactly
     as the item itself asked.

#### Research pass 2026-09-21 (thirty-ninth pass)

No external research this time. This pass read what Wednesday's issue
will actually say, and found three things — one of which contradicts the
claim the last two passes built on.

| Angle | Finding | Consequence |
|---|---|---|
| **Weekend rollover** | `weekend_dates()` returns **Sep 18–20** for a Sunday build and **Sep 25–27** for a Monday one. The committed build is stamped `2026-09-21T01:54Z` (Sunday 20:54 Chicago) and the live site still says "this weekend: Sep 18–20" — on a Monday | The site advertises a weekend that has already ended, every week (item 168) |
| **House ads** | The combined email contains **five** "SPONSOR THIS SPOT" blocks — one per region plus one more | Five sales pitches in a free weekly digest with no sponsors and one subscriber (item 169) |
| **Internal consistency** | Headline reads "This weekend, **four** towns over"; the subject names **three** ("Des Plaines, Mount Prospect, and Palatine") | Arlington Heights has nothing dated. Both are defensible alone; together they read as a bug (item 170) |

#### P1 (new)

168. **The site shows last weekend's events on Monday mornings — the one
     failure the freshness claim exists to rule out.** Verified by
     calling `weekend_dates()` directly: a build dated Sunday 20 Sep
     returns the window **18–20 Sep**; a build dated Monday 21 Sep
     returns **25–27 Sep**. The currently committed build is stamped
     `2026-09-21T01:54Z`, which is Sunday evening in America/Chicago, so
     it correctly computed Sunday's window — and it is now Monday there,
     and the live site still headlines "Sep 18–20" as *this weekend*.

     The gap is structural, not a one-off. The weekend window rolls over
     at local midnight on Monday, but nothing is scheduled to rebuild at
     that moment. `build-digest.yml` fires on pushes to `main` and on
     `cron: "0 12 * * 1"` — and item 110 measured this repo's scheduled
     runs landing **5h27m to 6h54m late**, which puts the Monday rebuild
     somewhere around midday Chicago time. So in the worst case the site
     advertises a finished weekend **from Sunday midnight until early
     Monday afternoon** — roughly fourteen hours, every week, on the
     morning when a parent plausibly checks what is coming up.

     It has been masked so far by an accident: the build loop pushes
     frequently, and every push rebuilds. **That dependency is about to
     weaken** — item 159 found the build loop nearly out of work, so as
     it goes quiet the stale window gets longer, not shorter. A freshness
     guarantee that holds only while a separate agent happens to be busy
     is not a guarantee.

     The fix is one cron line: rebuild early Monday local time, before
     anyone looks. Given the measured 5–7 hour lateness, a cron aimed at
     roughly **08:00 UTC Monday** (`17 8 * * 1`, offset minute per item
     110) would land mid-morning Chicago at worst and shortly after
     midnight at best — both strictly better than now. Keep the existing
     Monday-noon entry or replace it, but do not rely on push-triggered
     builds for a time-sensitive rollover.

     Worth pairing with item 163's visible "last checked" line, which
     would have made this obvious to a reader — and to us — weeks ago.

     🟢 **Shipped, 2026-09-21.** Replaced `build-digest.yml`'s
     `0 12 * * 1` (12:00 UTC) schedule entry with `17 8 * * 1` (08:17
     UTC), exactly the item's own suggestion including the offset
     minute to dodge the documented ":00" delay spike. Confirmed by
     reading `weekend_dates()` directly (already true before this fix,
     worth stating since it's what makes a *weekly* rebuild the right
     fix rather than a daily one): the Fri/Sat/Sun window it returns
     only changes at the Sunday-to-Monday local-midnight boundary, so
     this single earlier Monday slot is sufficient by construction.

#### P2 (new)

169. **Five "SPONSOR THIS SPOT" blocks in one email is too many.**
     Counted in the built artifact: the combined issue carries **five**
     house ads — one per region block plus another. Item 88 was right
     that an empty slot should say it is for sale rather than render
     nothing, and item 105 was right to give every region its own block.
     The interaction of the two was not considered, and it produces a
     free weekly digest in which roughly one visible element in four is
     asking for money, for a product that currently has **one subscriber
     and no sponsors**.

     This matters beyond taste. Item 124's whole differentiation is
     against products that feel automated and commercial; item 137's
     nearest real competitor is human-curated and restrained; and
     `DESIGN_PRINCIPLES.md` (item 103) exists precisely to stop
     accumulation like this, where each addition was individually
     justified.

     The fix keeps both intents: **one house ad per issue, not per
     region** — placed once near the foot of the email, worded as
     available inventory rather than a per-town pitch. A real, paying
     sponsor should still appear inside its own region's block, because
     that placement is what the tier sells. The rule generalises and is
     worth writing down: *house ads are inventory notices and appear at
     most once per artifact; paid placements are content and appear where
     they were sold.*

     🟢 **Shipped, 2026-09-21.** `render_combined_email_digest()` now
     picks at most one unsold-slot sponsor across all sections (first
     found, deterministic) and passes it separately from the per-region
     `sponsor` field; `combined_email_digest.html.j2` renders it once,
     after the region loop, worded exactly as before ("SPONSOR THIS
     SPOT"). A real paying sponsor's per-region block is untouched -
     still renders inside its own region, since that placement is what
     the tier sells. Verified against a real build: 5 unsold regions
     now produce exactly 1 house-ad block, not 5. Two new tests
     (multiple-unsold-regions and paid-sponsor-plus-house-ad-together).
     The generalized rule is now written down in the item body above,
     not just applied once.

170. **The headline says four towns, the subject names three.** The
     combined email's headline reads "This weekend, four towns over"
     while the generated subject is "This weekend across Des Plaines,
     Mount Prospect, and Palatine". Arlington Heights has nothing dated
     this week, so the subject-line builder correctly omits it while the
     body correctly still includes the town with an honest empty state.

     Each behaviour is right on its own. Together they are the kind of
     small inconsistency a careful reader notices and a sponsor asks
     about — and "four towns" is a claim about coverage, which is
     exactly the sort of number item 167 just flagged as worth getting
     right before it reaches anyone.

     Cheapest correct fix: make the headline count what the issue
     actually carries, or drop the number entirely — "This weekend,
     across the northwest suburbs" says the true thing without asserting
     an arithmetic the subject line contradicts. A test asserting the
     headline's town count matches the number of region blocks rendered
     would stop it recurring as regions are added (item 166 adds a
     fifth).

     🟢 **Shipped, 2026-09-21 — took the "drop the number" option.**
     The headline is now the literal suggested text, "This weekend,
     across the northwest suburbs" - true regardless of how many
     regions have something dated this week, so it can't drift from
     the subject line again. Found and fixed the same class of bug in
     two more places while in there, since Wheeling (item 166) had
     already made both wrong: `hub.html.j2`'s subheading hardcoded
     "four towns" (now `{{ region_summaries|length }}`), and
     `build_llms_txt()`'s trick-or-treat line hardcoded "all four
     towns" (now `len(region_summaries)`). Verified against a real
     build: both now read "5 towns". Three new tests, one per fixed
     location, each asserting the real count renders and the stale
     "four towns" string is gone.

#### Research pass 2026-09-21 (fortieth pass)

Yesterday's three findings all shipped — the Monday cron moved to
`17 8 * * 1`, the window reads Sep 25–27, the house ads went from five to
one, and the headline no longer asserts a town count. Item 141's
recurrence work landed too (the farmers market renders "Every Sunday
through Oct 25"), and Wheeling is live as a fifth region.

So this pass read the output again, and found something worse than
anything cosmetic.

| Angle | Finding | Consequence |
|---|---|---|
| **Wednesday's issue** | **Four of five regions have nothing dated.** The whole email is one farmers market | The first-ever scheduled send is a weekend digest containing one event (item 172) |
| **Past events** | Palatine's entire dated inventory is **Sep 18–20, all past**. Arlington Heights serves **"Tween LitCrate Sign Up" dated Sep 1** — three weeks stale | The freshness claim is not just unproven, it is currently false (item 171) |
| **Dated inventory** | Region pages show 18–24 cards, but Arlington Heights has **5 dated items** and Palatine **4** | The weekly digest is structurally fragile, not unlucky this week (item 172) |
| **Duplicates** | "Palatine Oktoberfest (Friday)" and "Tween LitCrate Sign Up" each appear **twice** | A smaller bug, but visible on the same pages (item 173) |

#### P1 (new)

171. **The site is serving past events as current content.** Verified
     against the live build: every dated item on the Palatine page is
     last weekend's Oktoberfest (18, 18, 19, 20 September — today is the
     21st), and Arlington Heights carries "Tween LitCrate Sign Up" dated
     **1 September** and "Baby Time" dated 2 September, three weeks gone.

     This is the most serious thing found in forty passes, because it is
     not a gap — it is the product actively doing the opposite of what it
     claims. Items 162 and 163 built a whole strategy on freshness being
     this site's one structural advantage. Item 131 stakes the
     differentiation against generated local content on every listing
     being real and traceable. A parent who clicks "Tween LitCrate Sign
     Up" and finds a closed signup from three weeks ago learns something
     about this site that no amount of provenance copy undoes.

     The fix is a filter that should have existed from the first build:
     **drop dated items whose date is in the past**, evaluated in
     `America/Chicago` rather than UTC so nothing vanishes an evening
     early or lingers a morning late. Two details worth getting right
     rather than discovering later: a multi-day event should survive
     until its *end* date, not its start (item 141's recurrence work
     already models spans); and genuinely undated evergreen entries must
     be untouched, since they are what the guides are made of.

     Worth a test with a fixture dated yesterday — the failure is
     invisible in any test that uses relative dates, which is presumably
     why forty passes of green tests never caught it.

     🟢 **Shipped 2026-09-21.** Added `filter_past_events(blocks, today)`
     in `scripts/build_digest.py`, called once in `main()` right after
     `fetch_region_sections()` and the curated `annual_events` block are
     merged into `blocks` — every downstream consumer (the main region
     page, calendar.ics, the RSS feed, Editor's Pick, and every
     date-scoped view) reads from that same already-filtered list, so
     there's one place this can drift out of sync, not several. `today`
     is `region_local_date()`'s result (America/Chicago, not UTC), computed
     before the fetch instead of after so the filter has it in hand.
     Undated evergreen/guide entries never pass through this function at
     all (they're separate lists). A multi-day festival modeled as one
     dict per day needed no special handling — each day already carries
     its own `date_iso`, so only the days that have actually happened
     drop and the festival's later days remain; a weekly-recurring entry
     already never generated a past occurrence (item 141), so this is a
     no-op there, confirmed rather than assumed by reading
     `expand_recurring_annual_event` before writing this fix. Verified
     against a real local build: Palatine's Sep 18–20 Oktoberfest cards
     disappeared from the region page and Editor's Pick fell back to the
     library's evergreen listing, exactly as expected. Two new tests
     added, including the fixture-dated-yesterday one the finding asked
     for, computed relative to a fixed reference date rather than the
     real clock (so the test doesn't itself rot the day the fixture
     dates become "old" by the wrong measure) — 423 tests pass. This is
     what makes item 172's thin-digest finding real rather than
     theoretical: the same build that used to show a padded weekend now
     shows what's actually left.

172. **Wednesday's issue will contain one event across five towns —
     decide now whether to send it.** With past events still included the
     email looks sparse; with item 171's filter applied it gets
     *sparser*, because most of what is dated is behind us. The current
     build of the combined issue is: Arlington Heights nothing, Des
     Plaines nothing, Mount Prospect one farmers market, Palatine
     nothing, Wheeling nothing.

     And the thinness is structural, not a bad week. Counted on the live
     build: Arlington Heights has **5 dated items in total**, Palatine
     **4**. For towns of roughly 75,000 and 69,000 people that is
     implausibly low, which points at the sources rather than the towns —
     the 403 and zero-item feeds item 161 flagged are exactly the kind of
     thing that would produce it, and item 159 already put re-verifying
     them at the top of the build loop's standing work. That work just
     became urgent rather than housekeeping.

     Two decisions, and the loop should make the first one rather than
     leaving it: **an issue with fewer than roughly three dated events
     across all regions should not send.** Add a floor to
     `send_newsletter.py` in the same spirit as its staleness guard —
     refuse, loudly, and let the failure email say why. A weekly digest
     that arrives nearly empty teaches subscribers to ignore it, and item
     155 argues the early sends are exactly the ones that set the habit.
     The second decision is Ryan's and only if he wants it: skip a week
     deliberately rather than send a thin issue.

     🟢 **Shipped 2026-09-21** (the loop's half of this - the floor).
     `build_digest.py` now writes `data/weekend_signal.json` (same
     committed-JSON pattern as `data/source_health.json`) recording each
     region's dated weekend-event count plus the total, right after
     item 171's filter runs so the number is honest. `send_newsletter.py`
     reads it and refuses to `send`/`schedule` (not `draft` - a thin
     draft is still worth a human look) below `MIN_WEEKEND_EVENTS = 3`,
     with a `--force-thin` flag for a deliberate override rather than
     editing code under time pressure. Verified against the real build
     this pass produced: the combined issue's actual count is **1**
     (Mount Prospect's farmers market only), and
     `python scripts/send_newsletter.py --dry-run` now refuses with
     `"Only 1 dated event(s) for 'combined' this week (floor: 3)"` -
     confirmed live, not assumed, and confirmed `--force-thin` correctly
     bypasses it. This is the guard for Wednesday's imminent first real
     `schedule`-mode send (2026-09-23): without it, that send would have
     gone out as the one-event issue this item describes. 7 new tests
     (430 total pass). The second decision - whether Ryan wants to skip
     this week outright rather than let the guard hold it back - is
     still his, not the loop's, and is now the most useful thing to
     bring to him: see "Needs Ryan" below.

     This doesn't fix the thinness itself, only stops it from mailing.
     Item 159's standing re-verification work (403s and zero-item feeds
     in `data/source_health.json`) is what actually raises the real
     count, and stays the higher-value target once this guard is in
     place.

#### P2 (new)

173. **Duplicate entries on the region pages.** "Palatine Oktoberfest
     (Friday)" appears twice with the same date, and Arlington Heights'
     "Tween LitCrate Sign Up" likewise. Both are visible in the rendered
     page, not just in the star-button payload.

     The likely cause is two configured sources carrying the same event —
     a village news feed and a downtown-merchants feed both announcing
     Oktoberfest, for instance — which is the normal case in civic
     aggregation rather than an edge case, and will get more common as
     item 166 adds regions and item 148 potentially adds athletics.

     A dedupe keyed on normalised title plus date would fix it, and the
     normalisation already exists: item 86 built near-duplicate title
     matching for the subject line and the same comparison applies here.
     Prefer the entry with a detail line and a working URL when
     collapsing, so dedupe improves the surviving card rather than
     picking arbitrarily.

     P2 rather than P1 only because item 171 is worse. On a page with 4
     dated items, having 2 of them be duplicates of each other is not a
     small proportion.

     🟢 **Shipped 2026-09-21.** Added `dedupe_events(blocks)` to
     `build_digest.py`, called right after item 171's past-event filter
     in the same single insertion point - the main region page, RSS
     feed, calendar.ics, and every date-scoped view all read from the
     same deduped `blocks`. Reuses `_is_near_duplicate_title()` exactly
     as this item asked, rather than a fresh comparison: two events
     count as duplicates only when they also fall on the same calendar
     day (a same-titled weekly-recurring event on two different Sundays
     is not a duplicate), and when collapsing, the entry with a detail
     line and a working URL wins over a bare stub. Both live examples
     this item named - "Palatine Oktoberfest (Friday)" and "Tween
     LitCrate Sign Up" - had already aged out of the dated views by the
     time this shipped (item 171's filter got there first, in the same
     pass), so this couldn't be re-verified against the exact original
     duplicates; verified instead with 5 new tests built directly from
     this item's own description (cross-source collapse preferring the
     fuller entry, same title on different days left alone, distinct
     same-day titles left alone, undated items never compared, and a
     deterministic tie-break). 435 tests pass; real build unaffected
     (still 1 dated event total, as item 172 already found).

174. **Full visual redesign to "Modernist": Archivo, a single red
     accent, zero corner radius, flat 2px dividers.** Owner-directed
     (not from a research pass): shared a claude.ai Design mockup
     (hub, region, and email screens) plus its underlying design-system
     tokens (`_ds/modernist-.../styles.css`, `--color-bg: #f3f2f2`,
     `--color-text: #201e1d`, `--color-accent: #ec3013`, Archivo,
     `--radius-md: 0`) and asked to convert the real site to match.

     Confirmed scope with the owner before touching code: convert every
     page (not just the three mocked up), design a dark-mode variant to
     match (the mockup only showed light), and keep every interactive
     feature exactly as-is (the sticky filter bar, the "My Weekend"
     star/tray with localStorage export, add-to-calendar links, View
     Transitions) - all three answered as recommended.

     Applied as a values-only swap wherever the markup already ran
     through CSS custom properties - `region.html.j2` (reused by 7 page
     variants: the main page, this-weekend/today/free, guide pages,
     directory, things-to-do), `hub.html.j2`, `merged_hub.html.j2`,
     `about.html.j2`, `sponsor.html.j2`, and `trick_or_treat.html.j2`
     all kept every class name, id, and Jinja branch untouched -
     `--bg`/`--card`/`--ink`/`--accent`/`--radius-lg`/`--shadow-*`
     tokens changed value, JS/tests never had to change. Two markup
     changes were necessary rather than cosmetic: `.card-grid`/`.card`
     went from a flex-wrap grid of shadowed boxes to a single-column
     stack of flat bordered rows (Modernist's own dominant pattern in
     every mockup screen, and it also gets item 61's stranded-last-card
     fix for free - a column has no row to strand anything in), and the
     hub page gained a slim top nav bar (This weekend/Today/Free/
     Sponsor/About) matching the mockup, since no equivalent existed
     before. Two inline SVG icons (the brand mark on region.html.j2/
     hub.html.j2/merged_hub.html.j2) had hardcoded light-on-green fills
     that don't work on a light ground - repainted, not redesigned.

     Editor's Pick and Sponsor boxes, previously distinguished by two
     different accent colors (green left-border vs. amber left-border),
     needed a real decision: Modernist is deliberately mono-accent ("no
     second accent was chosen"), so inventing a second color would
     contradict the system this item asked to adopt. Editor's Pick got
     a full ink border (the site's own editorial pick); Sponsor got the
     accent (paid/promoted), matching the mockup's own sponsor-CTA
     border treatment.

     The two email templates (`email_digest.html.j2`,
     `combined_email_digest.html.j2`) and their shared
     `_email_dark_mode.css.j2` needed a different approach: email HTML
     is inline hex, not CSS variables, by design (client constraints -
     see that file's own docstring), so this was a direct hex-for-hex
     find-and-replace against the same mapping (`#f6efe1`→`#f3f2f2`,
     `#2b2318`→`#201e1d`, `#96581f`→`#ae1800` and so on), plus swapping
     the Georgia serif headline for bold Arial (Archivo isn't
     email-safe; Modernist has no serif/sans pairing to preserve
     anyway, unlike the old Fraunces/Inter pair). `_email_dark_mode.css.j2`
     forces the light palette back against Yahoo/Outlook.com's forced
     dark-mode rewriting (item 92) - that mechanism is unrelated to the
     browser dark-mode work above and was preserved as-is, just
     repainted to the new hex values.

     Four exact-hex test assertions in `test_render_email_digest_body_
     type_meets_the_16px_mobile_floor` (item 97) had the old palette's
     literal colors baked in and had to be updated in lockstep - the
     one place breaking a test was correct rather than a regression,
     since the values it pins are exactly what changed.

     Verified with a real build and headless-Chromium screenshots
     (Playwright, the pre-installed Chromium binary) of the hub, a
     region page, the merged this-weekend hub view, the sponsor page,
     and an email preview - not just "tests pass," since a redesign's
     actual defect surface is visual. All five read as a coherent,
     intentional system: flat bordered rows, the red accent used
     sparingly (kickers, active states, the sponsor border), Archivo's
     fallback stack rendering correctly even with this sandbox's own
     network blocking the real webfont. 435 tests pass.

     Dark mode was independently screenshotted too (Playwright's
     `color_scheme="dark"` emulation, hub + region), and caught a real
     process mistake in the process: the first dark-mode screenshot
     showed the *old* green-gradient hero, because `git restore docs/`
     (run to keep the diff source-only before committing) had reverted
     `docs/` to the stale pre-redesign build in between the light-mode
     and dark-mode screenshot passes - the templates were already
     correct, the rendered output being screenshotted wasn't. Rebuilt
     fresh and re-screenshotted before trusting the result: dark mode
     renders correctly - near-black ground, off-white ink, the
     brighter accent-500 red Modernist's own ramp guidance calls for on
     a dark background.

     🔴→🟢 **Real CI regression found and fixed, 2026-09-21 (same day,
     next hourly firing).** The redesign PR's own Lighthouse CI job
     failed - checked, not assumed, from the real GitHub Actions run
     (`35614346834`) rather than trusted from local pytest alone.
     Cumulative Layout Shift exceeded the 0.1 budget on 5 of 7 tested
     URLs (0.10-0.18), the real defect surface a template redesign has
     that a Python test suite structurally cannot see. Root cause:
     Archivo loads via `&display=swap` (FOUT - the fallback stack
     paints first, then swaps once the webfont arrives), and its
     metrics differ enough from the system fallback - especially now
     that headings are uniformly 800-weight with `-0.02em`
     letter-spacing, versus the old design's lighter 500-700 weights -
     that the swap reflows large headline text measurably, which
     `display=swap` never guarded against and the old Fraunces/Inter
     pairing apparently stayed just under the budget.

     Fix: `&display=swap` → `&display=optional` on all three Archivo
     `<link>` tags in every site-page template (region, hub,
     merged_hub, about, sponsor, trick_or_treat - the email templates
     don't load webfonts at all, so they were never affected).
     `optional` gives the browser a very short block window and, if
     the font isn't ready, uses the fallback for that page view with
     no later swap - the standard, documented fix for exactly this
     failure signature, trading "the custom font sometimes won't show
     on a cold, slow first load" for "no layout shift, ever," which is
     the right trade for a budget that's asserted in CI.

     Verified locally before pushing, not just reasoned about: `rm -rf
     .lighthouseci && CHROME_PATH=/opt/pw-browsers/chromium-*/chrome-
     linux/chrome npx @lhci/cli autorun --collect.settings.chromeFlags
     ="--no-sandbox"` (the `--no-sandbox` flag needed running as root
     in this sandbox, not something CI's own runner needs) - all 21
     runs across all 7 URLs passed with no assertion failures, versus
     the prior run's CLS failures on 5 of them. 435 tests still pass.

     Confirmed green on the real PR and on `main` after merge (#219,
     `89fad06`), not just assumed from the local run above - polled the
     actual GitHub Actions run via the API until it completed, rather
     than merging on faith. One unrelated, benign flake surfaced while
     watching: `build-digest.yml`'s "Commit generated site" step failed
     on `main` with a plain git push rejection, because the merge
     landed within about five seconds of that same workflow's own
     hourly `schedule` trigger firing - two independent runs raced to
     commit `docs/` at once. Not this fix's fault and not a real
     problem: the `schedule`-triggered twin's commit succeeded and
     `docs/` was already current by the time this was checked. Noted
     for pattern-recognition only, since a merge landing within
     seconds of build-digest.yml's own hourly cron is bound to recur
     occasionally - not worth hardening (a `git pull --rebase` retry
     before push) for a race this rare and this self-healing.

#### Research pass 2026-09-21 (forty-first pass)

Items 171 and 173 shipped and work — **zero past-dated items remain
across all region pages**, down from a page whose entire inventory was
last weekend. Item 172's floor shipped too, as
`MIN_WEEKEND_EVENTS = 3`.

Which produces the thing this pass is mostly about: **that floor is
about to stop Wednesday's send.**

| Angle | Finding | Consequence |
|---|---|---|
| **The send floor** | `MIN_WEEKEND_EVENTS = 3` is live; the built issue carries **one** dated event and **four** "Nothing new dated" blocks | Wednesday's send will correctly refuse. No issue goes out this week (item 175) |
| **The redesign** | Site and email both moved to grey `#f3f2f2` + red `#ec3013`/`#ae1800` + Archivo — **consistently across both**, which is the right way to do it | But it needed a CLS follow-up fix, and it is exactly what item 159 predicted an idle build loop would do (item 176) |
| **The guard document** | `DESIGN_PRINCIPLES.md` still describes **"a beige/green palette"** and says it exists "as a **defence**, not that anything needs redesigning" | The document meant to prevent drift now documents a site that no longer exists (item 176) |
| **Empty-state copy** | Four of five region blocks read "Nothing new dated for this weekend yet, but worth knowing about: [the library]" | The same sentence four times, each offering one fallback (item 177) |

#### P1 (new)

175. **No newsletter will go out this week, and the floor is not the
     problem — the feeds are.** The guard item 172 asked for is live and
     correct: with one dated event across five towns, `MIN_WEEKEND_EVENTS
     = 3` will refuse Wednesday's send and fail loudly. That is the right
     behaviour and it should stay.

     But it converts a content problem into a delivery problem, and the
     content problem is now the only thing standing between this business
     and a working weekly newsletter. Item 150 recorded one issue ever
     sent. If Wednesday refuses, the record becomes **one issue, with a
     nine-day gap and counting** — and item 155 argued the early sends
     are precisely the ones that establish whether a list survives.

     The root cause is already named and has never been actioned: item
     161 found `experiencemountprospect.org` returning **403 Forbidden**
     and Downtown Mount Prospect returning **200 with zero matching
     items**, and item 159 put re-verifying the feeds at the top of the
     build loop's standing work. Item 172 said that just became urgent.
     It is now blocking. Five suburbs of 16k–57k people in late September
     have dozens of real events between them; a pipeline that finds one
     is not measuring the towns, it is measuring itself.

     Concretely, in priority order: re-verify every configured feed and
     record what each actually returns; for any source returning zero,
     check whether the fetcher's selectors still match the page; and
     treat a source that returns zero for three consecutive builds as
     **broken rather than quiet** — `data/source_health.json` already
     tracks the history needed to tell the difference. This is the most
     valuable work available to the build loop and it outranks anything
     cosmetic.

     🟢 **Partly shipped 2026-09-21** — one real, confirmed bug fixed;
     one real, separate problem found and deliberately left open rather
     than guessed at.

     Re-verifying the feeds (as asked) surfaced something more useful
     than "still 403": the build's own "Structured-date coverage" line
     showed Des Plaines, Palatine, and Wheeling at **0/20, 0/14, 0/10** —
     zero machine-readable dates despite each fetcher returning a
     nonzero item count. That's not the 403/zero-item pattern item 161
     already named; it's items being fetched successfully and coming
     back as *undated noise*. Pulled the real `data-item` JSON out of
     each region's actual committed `docs/` output (not a guess) and
     found `fetch_html_events()`'s keyword-fallback branch — the code
     path used whenever a source has no confirmed `detail_link_pattern`,
     which is true for every Des Plaines/Palatine/Wheeling source — was
     matching generic nav/account/legal chrome purely because its link
     text contained a configured keyword substring: "My events" (a
     LibCal account link on `calendar.dppl.org` — the same false-positive
     *shape* item 9 fixed once before on a different LibCal site, now
     confirmed recurring on this one too), "Programs / Event Tickets",
     "News & Events", "City Council", "Program Guide", "Search Programs",
     "Calendar of Events", "Subscribe to E-News", "Book Discussion
     Request Form" — plus "Copyright Notices" and "Public Notices",
     confirmed on two *unrelated* civicplus-platform domains
     (`palatine.il.us` and `wheelingil.gov`), which only reach the
     denylist check at all because both towns' own YAML configs add
     `"notice"` to that source's `keywords:` override (confirmed by
     reading `config/regions/palatine-60067.yaml` and
     `wheeling-60090.yaml` directly, not assumed) for legitimate reasons
     (catching real closure/advisory notices) that happen to also catch
     "Copyright Notices" in the site footer.

     Added all 11 to `_NAV_LINK_DENYLIST` in `scripts/fetchers.py`, with
     a comment citing exactly which region's `docs/` output confirmed
     each one. Deliberately left several similar-looking titles from the
     same real evidence **out** of the denylist because they read as
     plausibly real, if undated, standing programs rather than pure
     chrome — "Book groups", "Summer Camps", "Museum Pass Programs",
     "Festival of Cultures", "Used book sale", "Storywalk", "Books &
     Media", "E-books & Digital Downloads", "Program Areas". Denylisting
     those on a guess would trade one kind of wrong (chrome as event) for
     another (a real program silently dropped), which the "verify, don't
     invent" standing rule below rules out without markup evidence this
     sandbox's blocked network can't fetch. New regression test
     (`test_fetch_html_events_denylists_libcal_and_civicplus_chrome`)
     reproduces the exact HTML shape from `calendar.dppl.org`,
     `dpparks.org`, `wheelingil.gov`, and `palatine.il.us`, passing the
     same `keywords:` override the real configs use so "Copyright
     Notices" is exercised the way it actually reaches the check in
     production, not trivially excluded by the keyword filter first —
     436 tests pass. This sandbox's network is fully blocked (every
     fetcher 403s here), so a local rebuild can't demonstrate the live
     coverage-number improvement directly; that confirmation has to come
     from the next real `build-digest.yml` run's own log line, same as
     every other fetcher fix this session.

     **Still open, and separately scoped rather than guessed at:** even
     with all confirmed chrome removed, some of what's left in those
     three regions is genuinely real and still undated — Wheeling's
     Village Board/Commission meetings, Palatine's "Festival of
     Cultures" — because `_nearby_date_hint()`'s two date-extraction
     regexes (`_DATA_DATE_ATTR`, `_ARIA_LABEL_DATE`) were each confirmed
     against exactly one platform (Mount Prospect's Vision Internet
     calendar, AHML's Drupal calendar) and return `None` silently for any
     other site's markup — which these three towns' sites are. Fixing
     that needs the real markup for each platform to confirm a new
     pattern against, which this sandbox cannot fetch; guessing a regex
     from field names alone risks a confidently wrong date, which item
     171 already established is the one error this site can't afford.
     Left as a named, scoped finding for the next pass that has live
     network access to a Des Plaines/Palatine/Wheeling page, rather than
     shipped as a guess.

     **One follow-up correction, made real by CI itself rather than
     assumed:** the PR's own `tests.yml` run failed on its first push —
     `detect_source_regressions()` (item 51) flagged
     `palatine-60067:Village of Palatine — News` for dropping from a
     steady trailing count of **2** to a real **0**. Checked the actual
     job log rather than guessing at the cause: the fetch itself
     succeeded (no transport-error tag), it's a genuine post-filter 0.
     That source's config (`url:
     "https://www.palatine.il.us/CivicAlerts.aspx"`, `keywords: [...,
     "notice", ...]`) is exactly the page and the reason "Copyright
     Notices" reached this fix's denylist check in the first place — so
     that steady "2" was, in hindsight, never real news; it was this
     source's entire history being two chrome links every single build.
     The regression detector correctly can't distinguish "a source died"
     from "a source's own past counts were themselves wrong and a fix
     just corrected them" — that's a real, previously-unexercised gap in
     what it can tell, not a new bug to fix this cycle. Reset that one
     key's history in `data/source_health.json` to a single fresh `[0]`
     entry so fresh, honest history starts accumulating from the
     corrected code, documented here rather than silently edited.

     **Final result, from the real post-merge `build-digest.yml` run
     (`23a62a9`), not assumed:** the fix did exactly what it was scoped
     to do and no more. Item counts dropped as predicted — Des Plaines
     20→19, Palatine 14→12 (its "Village of Palatine — News" source
     alone went 2→0, confirming those 2 were always "Copyright
     Notices" + "Public Notices"), Wheeling 10→9 — real chrome, gone.
     **Structured-date coverage stayed at 0% for all three regions**
     (0/19, 0/12, 0/9) — worth stating plainly rather than letting the
     item-count drop read as more than it is. Removing chrome shrinks
     the denominator; it can't raise the numerator when the numerator's
     ceiling is the separate, still-open `_nearby_date_hint()` gap this
     item already named above. Both things are true at once: the site
     now shows fewer fake listings, and the newsletter is no closer to
     clearing `MIN_WEEKEND_EVENTS = 3` in these three towns until that
     second, harder problem gets real markup evidence to fix against.

176. **The design guard did not hold, and the document that was supposed
     to hold it is now stale.** `DESIGN_PRINCIPLES.md` shipped under item
     103 to stop accumulation, names Godly and SiteInspire as the
     standard under item 113, and states in its own words that it was
     written "as a **defence**, not that anything needs redesigning." It
     still describes the palette as **"beige/green"**. The live site and
     the live email are now grey `#f3f2f2` with a red accent
     (`#ec3013` on the site, `#ae1800` in the email) and Archivo
     throughout.

     Two things should be said separately, because they are different.

     **The execution looks careful.** Both artifacts moved together —
     there is no site/email brand mismatch, which is the failure I went
     looking for and did not find. A single accent on a near-neutral
     ground with one typeface is a defensible reading of item 113's
     "restrained, editorial, typographically considered", not a drift
     toward the Awwwards direction that item ruled out. Nothing here says
     the new design is worse.

     **The process is the finding.** Item 159 predicted this precisely:
     "the failure mode for an idle build loop is inventing features,
     which `DESIGN_PRINCIPLES.md` (item 103) exists to prevent", and
     proposed verification as the standing alternative. A full palette
     and typography change, undertaken while five towns' feeds were
     returning almost nothing, is that prediction coming true — and it
     cost a Core Web Vitals regression that needed its own follow-up
     (item 174's CLS fix), on a site where item 19's earlier animation
     experiment failed CI on exactly the same metric.

     So: **update `DESIGN_PRINCIPLES.md` to describe the site that now
     exists** — a stale guard is worse than none, because it is quoted
     with confidence. And add the rule the episode reveals is missing:
     *a change to the palette, typeface or layout system needs a stated
     reason a reader would notice, recorded before the work, not after.*
     That is not a ban on redesigning; it is the same bar item 103
     already applies to adding features, applied to changing them.

     🟢 **Shipped 2026-09-21.** Rewrote `DESIGN_PRINCIPLES.md`'s "The
     two directions" to describe the real, current system — Archivo
     throughout, `#f3f2f2`/`#171615` grey ground, single `#ec3013` red
     accent, zero corner radius, flat 2px borders — with an inline note
     marking it as item 174's 2026-09-21 redesign from the earlier
     Fraunces/Inter/beige-green system, rather than presenting either
     as timeless. Replaced the old closing line ("the existing
     direction is already correct... not that anything needs
     redesigning") with an honest account of what actually happened:
     the file said that, then a redesign happened anyway, and this
     finding is what caught it. Added a new "Changing this system"
     section with the exact rule asked for — a stated, reader-noticing
     reason recorded *before* the work, explicitly ruling out "it
     looked dated" as a qualifying reason, and pointing back at item
     159's "verify, don't invent" standing work as where idle-loop time
     should go instead. No code changed; this is the guard document
     catching up to what it's meant to guard.

#### P2 (new)

177. **Four identical empty states is a design problem, not a data
     problem.** With one dated event, four of five region blocks in the
     combined email read "Nothing new dated for this weekend yet, but
     worth knowing about:" followed by a single evergreen fallback — in
     every case the town's library. The sentence is honest and the
     fallback is real; repeated four times in one short email it reads as
     a product with nothing to say.

     Item 175 fixes the supply. This is about what the email should do on
     the weeks when supply is genuinely thin, which will happen again —
     January exists.

     Three cheap improvements, in order of value: draw the fallback from
     **more than one source** so the four blocks are not four library
     links; **collapse consecutive empty regions** into one line ("Nothing
     dated yet in Arlington Heights, Des Plaines, Palatine or Wheeling —
     here is what is standing") rather than repeating the full structure;
     and where a region has a **recurring** entry in range, prefer it —
     item 141's farmers market is exactly the kind of standing answer that
     beats a bare library link.

     Worth keeping the honest empty state rather than padding it. The
     point is not to hide that a week is quiet; it is to say so once,
     briefly, rather than four times at full length.

     🟢 **Shipped 2026-09-21, two of three.** Confirmed the exact
     mechanism before touching anything: every region's `evergreen:`
     list is `[library, park district, village, HS athletics]` in that
     order, and only the library entry ever carries an explicit `free`
     tag - so `[e for e in evergreen if "free" in tags][:3]` always
     returned exactly one item (the library) no matter how high its
     slice limit was, real config confirmed for all five regions before
     assuming it. New `_pick_evergreen_highlights()` helper prefers the
     free-tagged item first, then fills remaining slots from the
     region's own remaining evergreen entries in their existing curated
     order - a standalone region block now shows up to 2 distinct
     sources (library + park district) instead of one.

     Collapsing: `render_combined_email_digest()` now separates regions
     with genuinely nothing (no attendable event, no informational
     note, and *no active sponsor* - a paying sponsor's per-region
     placement, item 169's tier, is never folded away) from the rest,
     and only collapses them into one shared block once **two or more**
     qualify at once - `_join_names(..., conjunction="or")` (the
     existing subject-line joiner, given a second conjunction option)
     produces "Nothing dated yet in Arlington Heights, Des Plaines,
     Palatine, or Wheeling — worth knowing about:" followed by one
     compact line per region with its own real link, replacing four
     repeats of the identical sentence. A single empty region still
     reads as its own ordinary card - collapsing only pays off once
     there's real repetition to remove.

     Verified against this build's own real output (this sandbox's
     network is blocked, so every non-Mount-Prospect region is
     genuinely empty right now - an honest, if extreme, test of the
     collapse path): `docs/combined-email-preview.html` shows exactly
     one "Nothing dated yet in Arlington Heights, Des Plaines,
     Palatine, or Wheeling" line, zero repeats of the old per-region
     sentence, and Mount Prospect's real farmers-market card untouched
     alongside it - screenshotted, not just grepped. 6 new tests (441
     total pass), covering the multi-source pick, the collapse
     threshold (2+ triggers it, 1 doesn't), and the sponsored-region
     exclusion.

     **Not attempted, and said plainly rather than guessed at:** the
     third improvement (prefer a recurring entry when one's in range)
     turns out to be structurally unreachable with today's data. Only
     Mount Prospect has a `recurring: true` annual event (item 141's
     Sunday farmers market, in season through Oct 25), and a weekly
     recurrence's dated occurrence always lands inside the Fri–Sun
     window it's checked against - so whenever that market is in
     season, Mount Prospect's `attendable_events` is never empty and
     the fallback branch this item is about never fires for it in the
     first place. No other region has any recurring entry at all.
     Writing the "prefer recurring" logic anyway would be dead code
     with nothing real to exercise it - worth revisiting only once a
     second region gets one, or once the farmers market's season ends
     and its own fallback behavior can be checked against reality
     instead of assumed.

#### Research pass 2026-09-22 (forty-second pass)

Item 175 said the feeds were the problem and asked for root-causing. This
pass did it, against `data/source_health.json` and `scripts/fetchers.py`
rather than by inference. **The cause is found and it is not what the
last three passes assumed.**

| Angle | Finding | Consequence |
|---|---|---|
| **Volume** | 16 of 20 sources are live, returning roughly **75 items** between them. The towns are not quiet | The thin weekend was never a supply problem (item 178) |
| **The cap** | `scripts/fetchers.py:38` — **`MAX_ITEMS_PER_SOURCE = 6`**. Every healthy source returns exactly 6, on every recorded build | A library publishing 40 events a month contributes 6. The weekend window is starved by truncation (item 178) |
| **The dead four** | Zero-returning sources are **Village of Mount Prospect News, Village of Mount Prospect Calendar, Downtown Mount Prospect, Experience Mount Prospect** — every one of them Mount Prospect, every one of them the village layer | The home region has lost its entire civic tier and is running on library + parks + schools (item 179) |

#### P1 (new)

178. **`MAX_ITEMS_PER_SOURCE = 6` is why the weekend is empty — fetch by
     horizon, not by count.** Every live source in the health file
     returns exactly 6 items, on every build recorded. That is not a
     coincidence about twenty different civic calendars; it is
     `scripts/fetchers.py` truncating each feed to its first six entries
     before anything else happens.

     The consequence falls entirely on the weekend view, and it explains
     the whole puzzle of the last three passes. A public library
     publishing forty programmes across the next month contributes six of
     them. A park district the same. So the site holds ~75 items spread
     over several weeks, which makes the region pages look reasonably
     full — and leaves the odds that three or more land on **one
     specific Friday-to-Sunday** poor. Items 171–175 read that as broken
     sources or quiet towns. It was neither.

     The design is backwards: it truncates by count and then filters by
     date, when it should gather across a date horizon and let the window
     select. Concretely — **raise the cap substantially and bound by time
     instead**: take everything a feed offers within, say, the next 60
     days, with a generous per-source ceiling (a few hundred) purely as a
     runaway guard rather than as the operative limit. `FEED_MAX_ITEMS =
     50` already exists in `build_digest.py` for the RSS output, so a
     larger number is not a new idea in this codebase, just one that
     never reached the fetchers.

     Two things to keep while changing it. The **per-source cap should
     stay non-null** so one pathological feed cannot dominate a region
     page; and the region page's own display limits should be checked
     afterwards, because they were tuned against six-item sources and may
     now need their own attention. Worth a test that asserts a fetcher
     given 50 well-formed dated items returns substantially more than six.

     🟢 **Shipped 2026-09-22.** Raised `MAX_ITEMS_PER_SOURCE` in
     `scripts/fetchers.py` from 6 to 200 — sized to the "a few hundred"
     runaway-guard this item asked for, not removed outright, so one
     pathological feed still can't dominate a region page or blow up
     build time. `fetch_ics` already filters to upcoming-only before
     this cap ever applies, so raising it there directly implements
     "gather across a date horizon and let the window select" with no
     other logic change; `fetch_rss` and `fetch_html_events` have no
     per-item date ordering to exploit the same way, so the raised cap
     is their only real fix, and build_digest.py's own existing
     downstream filters (`filter_past_events`,
     `filter_events_by_dates`/`weekend_dates`) are what actually select
     the weekend window from the larger pool now flowing through.

     Checked the region page's own display limits before assuming they
     needed the same attention this item flagged: none do.
     `templates/combined_email_digest.html.j2`'s `[:4]` and
     `templates/email_digest.html.j2`'s `[:6]` (also mirrored in
     `build_weekly_summary_txt`'s own `[:6]`) all slice
     *already-weekend-filtered* events for a short email/social post,
     not raw fetcher output — a real weekend won't have dozens of
     events per region regardless of this fix, so these were never
     tuned against the six-item cap and don't need raising. No other
     `[:N]` slice exists on the main region page.

     Added the two tests this item's own write-up asked for
     (`test_fetch_rss_does_not_truncate_a_well_stocked_feed_to_six`,
     `test_fetch_ics_does_not_truncate_a_well_stocked_feed_to_six`) - a
     50-item feed now returns 50, not 6. 443 tests pass. This sandbox's
     network is fully blocked, so a local rebuild can't demonstrate the
     real per-region item-count increase directly (every source still
     fetches 0 here); that confirmation has to come from the next real
     `build-digest.yml` run's own log, same discipline as every other
     fetcher fix this session. Item 179 (Mount Prospect's dead village
     layer) is a separate, real-URL-diagnosis task rather than a code
     change and is left for a following pass rather than folded into
     this one.

     **Final confirmation, from the real post-merge build (`f190e02`),
     not assumed:** the fix worked exactly as intended. Mount Prospect
     Public Library — Events jumped 6→200, its School District 57
     calendar 6→66, Arlington Heights Memorial Library 6→200 — and it
     wasn't truncation of the same handful of items either: pulled the
     real committed `docs/arlington-heights-60005/index.html` and
     confirmed 199 distinct data-items, 132 unique titles, the repeats
     being exactly what a real library calendar produces (13 "Beginning
     ESL" sessions, 9 "Play Time," 6 "Baby Time" - individual weekly
     occurrences, not chrome or duplication). The weekend view moved
     for real: Mount Prospect's `this-weekend/index.html` went from 2
     items to 6, `free/index.html` from 2 to 7. `TOTAL structured-date
     coverage: 249/482 events (52%)`, up from the low-30s/81 this file
     had been reporting for weeks. `detect_source_regressions()` found
     nothing to flag - every source that changed went up, none crossed
     to zero.

     One real, honestly-reported side effect, checked rather than
     assumed away: Arlington Heights' own coverage *percentage* dropped
     (5/194, down from 8/18) even though the volume win is real -
     raising the cap didn't fix dates, it just made the existing,
     already-flagged (item 175's "separately flagged" note)
     `_nearby_date_hint()` gap visible at 194 items instead of 12. That
     gap is unchanged by this item and still not attempted here for the
     same reason item 175 gave: fixing it needs real markup evidence
     this sandbox can't fetch.

     Also checked, given this item's own instruction to look at display
     limits afterward: a 356KB, 199-item region page is a real dom-size
     concern, not a hypothetical one. Ran Lighthouse locally (this
     sandbox's Chromium, `--no-sandbox`) against the actual committed
     Arlington Heights page - `dom-size` scores 0 (2,756+ elements
     region-wide once Mount Prospect's own 239-item page is checked the
     same way), but the metrics `lighthouserc.json` actually gates on
     stayed comfortably inside budget on both: LCP 953ms/1209ms, CLS 0,
     TBT 80.5ms/55.5ms against the 2500ms/0.1/200ms limits. Mount
     Prospect's page carries the identical `dom-size` flag and already
     passed real CI on this exact data (PR #230's own Tests workflow
     built with real network access), so this isn't a new regression -
     it's the expected shape of "more real content," not yet a problem
     the current gates catch, but worth a display-side cap or "show
     more" pattern in a future pass if a source's raw count keeps
     growing rather than settling. Recorded as a real, open,
     non-blocking finding rather than either ignored or over-fixed on
     a guess.

     **Second follow-up, 2026-09-22 - the 200 cap turned out too low,
     found by the diagnostic item 180 built specifically to find
     exactly this:** the PR shipping item 180's truncation check failed
     real CI on its very first live run - `detect_truncated_sources()`
     correctly caught Arlington Heights Memorial Library and Mount
     Prospect Public Library both landing on exactly 200 for 3
     consecutive real builds. Checked before reacting, not assumed: the
     earlier real-CI confirmation above already established AHML's 199
     items were genuine, distinct content (132 unique titles, real
     recurring sessions), so this isn't item 175's nav-chrome problem
     recurring - it's a source that's genuinely bigger than 200 was
     assumed to comfortably cover. Raised `MAX_ITEMS_PER_SOURCE` to
     500 in `scripts/fetchers.py`, still "a few hundred" as this item
     originally asked, not unbounded. Flagged honestly rather than
     treated as solved: `fetch_rss` and `fetch_html_events` still have
     no per-item date-horizon bound, so a source that keeps genuinely
     growing (AHML's rolling calendar is exactly this shape) can hit
     500 too - the real, not-yet-attempted fix stays what this item
     originally proposed, bounding by date horizon inside the fetcher
     itself, not repeatedly raising a count cap each time a real
     source outgrows it.

     **Settled, confirmed by a third real build:** both sources' true
     totals turned out well inside the new cap rather than still
     climbing toward it - `data/source_health.json` now shows Arlington
     Heights Memorial Library at a real 259 and Mount Prospect Public
     Library at a real 299, both comfortably below 500. The 200-item
     truncation was real but bounded, not a sign of unbounded growth;
     500 looks like real headroom rather than a number that will need
     raising again next week. `detect_truncated_sources()` and the
     other two health checks all confirm clean against this fresh data.

179. **Mount Prospect has lost its entire village layer, and it is the
     only region that has.** The four zero-returning sources are not
     scattered: they are **Village of Mount Prospect — News**, **Village
     of Mount Prospect — Calendar**, **Downtown Mount Prospect** and
     **Experience Mount Prospect**. Every other region's sources are
     live. The home region — the one `BUSINESS_PLAN.md` is written about,
     the one the domain and the brand were chosen for — is running on its
     library, park district and school district alone.

     That is worse than it looks in the counts, because the village layer
     is the *civic* half of the moat. Item 124's differentiation against
     Patch rests on aggregating "the village, the public library and the
     park district"; item 131's provenance claim names them; item 152's
     link-back play targets them. One of those three is currently absent
     for the flagship town, and Downtown Mount Prospect is the source
     that carries Oktoberfest — the single biggest event the site has
     ever listed.

     Item 161 already diagnosed two of the four (Experience Mount
     Prospect 403s; Downtown Mount Prospect returns 200 with zero
     matches) and proposed asking rather than working around. The two
     Village feeds are new here and need the same treatment: check
     whether the URL still resolves, whether the selectors still match,
     and whether the village has moved its calendar to a platform with a
     published feed. **This is the single most valuable repair available
     to the build loop** — it restores the flagship region's civic tier
     and it directly feeds item 178's fix, since a raised cap only helps
     sources that return anything at all.

     🟡 **Partly investigated 2026-09-22 — first question answered, second
     one needs real network access this loop doesn't have.** WebSearch
     (real, not guessed) confirms both `mountprospect.org/services/news`
     and `mountprospect.org/services/calendar` are still the correct,
     live, current URLs — the same two pages surface as the top hits for
     a `site:` search of exactly those paths, and the domain is actively
     publishing (an indexed "Mount Prospect Update - April 10, 2026" news
     story, live Human Services calendar events). So the 403 isn't a
     stale URL; whatever's blocking this fetcher's User-Agent is blocking
     it on a page that demonstrably still exists and still updates.

     A genuinely promising lead surfaced in the same search: the Village
     publishes real, categorized RSS feeds from a
     `.../list-all-rss-feed` page, "Village News" named as one of the
     categories - a first-class feed this codebase's existing, already-
     reliable `fetch_rss()` could use directly (the same fetcher already
     pulls the Library's RSS with zero errors), rather than continuing to
     fight a 403'd HTML scrape. That would plausibly work even if the
     block is User-Agent/bot-detection on the HTML page specifically,
     since a feed URL is often served from different infrastructure.

     Tried to get the actual feed URL directly rather than stopping at
     "a feed page exists": confirmed, by testing it directly rather than
     assuming from an earlier pass's characterization, that this
     sandbox's blocked network isn't a `requests`-library-specific
     limitation — the sandbox's own pre-installed Playwright/Chromium
     hit the identical `net::ERR_TUNNEL_CONNECTION_FAILED` against the
     same external domain. Neither tool available to this loop can reach
     that page's real DOM to read off the click-through feed URL, and
     guessing a Vision Internet RSS URL pattern would be exactly the
     kind of invented fix this file's own discipline rules out. Added a
     30-second "open this page, paste the feed URL" ask to the "Needs
     Ryan" small/no-decision bucket rather than blocking on it silently
     or guessing past it - the smallest, most mechanical item there,
     not a judgment call. The Village Calendar side (meetings/events,
     as distinct from News) is worth checking the same listing page for
     once that URL comes back, in case it's also a named category there.

#### P2 (new)

180. **A source pinned at exactly the cap is a diagnostic nobody is
     reading.** `data/source_health.json` shows sixteen sources with
     perfectly flat histories — `[6, 6, 6, 6, 6]` — and four flat at
     zero. Item 51 built this file to distinguish a transport failure
     from a genuine empty week, which it does well. It has no concept of
     the third state now known to matter: **truncation**.

     A feed returning exactly `MAX_ITEMS_PER_SOURCE` on every single
     build is almost certainly being cut off, not exhausted. That is a
     one-line check with real diagnostic value, and it is the signal that
     would have surfaced item 178 weeks ago instead of three passes of
     inference: flag any source whose last N counts all equal the cap.

     Worth pairing with the inverse, which item 175 asked for and is
     still worth having after 178 lands: treat a source returning zero
     for three consecutive builds as **broken rather than quiet**. The
     four dead Mount Prospect sources have flat-zero histories going back
     as far as the file records, and nothing has ever said so out loud.

     Both checks belong in the build, failing the job the way item 51's
     existing regression check already does — the mechanism exists, it
     simply does not know about these two cases.

     🟢 **Shipped 2026-09-22.** Added `detect_truncated_sources()` and
     `detect_newly_broken_sources()` alongside the existing
     `detect_source_regressions()` in `scripts/build_digest.py`, wired
     into the same build-failing check at the same point in `main()`.

     Truncation fires whenever a source's last three counts all land
     exactly on `MAX_ITEMS_PER_SOURCE` (200 now) — deliberately **not**
     transition-gated, since it's meant to stay loud for as long as a
     source is actually being cut off, unlike a source that died once.

     The "broken rather than quiet" check needed one real design
     decision this item's own wording didn't spell out: item 180 asked
     for both checks to fail the build exactly like the existing one,
     but a literal "any source with 3+ trailing zeros" check would
     permanently fail every build going forward for the four already-
     known, already-diagnosed dead Mount Prospect sources (items
     161/179) until their real fix lands — training everyone to ignore
     red builds, the opposite of the alert's actual purpose. Checked
     this against the real, current `data/source_health.json` before
     deciding, not assumed: those four sources' histories are already
     fully aged into all-zero (`[0,0,0,0,0]` and longer), so a naive
     check fires on every single build from here forward.

     Fixed by transition-gating it the same way the existing regression
     check already is: `detect_newly_broken_sources()` only fires on
     the build where the *third* consecutive zero lands (the 4th-from-
     last entry was still nonzero) — once, not forever. A source dead
     for weeks and already fully aged into flat-zero history won't
     re-trigger it on every later build; a source that dies *starting
     now* still gets caught at the moment it crosses into "broken," not
     silently absorbed into "quiet by design" the way item 175/180
     both described. Verified against the real, current health file:
     all three new/existing checks return empty against it (no false
     positive on the four already-known-dead sources or on
     `palatine-60067:Village of Palatine — News`'s own item-175 reset
     history), confirmed by running the functions directly against the
     committed file before shipping, not assumed from the design alone.
     6 new tests, 449 total pass.

#### Research pass 2026-09-22 (forty-third pass)

**Item 178 worked, and the send is unblocked.** Checked first, before
researching anything, because the forty-second pass ended on a live
production failure and the scheduled send fires tomorrow (Wednesday
22:37 UTC). `data/source_health.json` now totals roughly **743 items
across 20 recorded sources**, against ~75 last pass — Arlington Heights
Memorial Library went 6 → 259, Mount Prospect Public Library 6 → 299.
`data/weekend_signal.json` reports **10 dated weekend events**, clearing
`MIN_WEEKEND_EVENTS = 3`. The newsletter item 175 said would not go out
this week will go out. Item 177 shipped too, visibly: the four identical
empty states are now one consolidated sentence.

But reading the built email rather than only the counters turned up
what the totals hide.

| Angle | Finding | Consequence |
|---|---|---|
| **Sources that were never recorded** | `config/regions/*.yaml` declares **25** sources. `data/source_health.json` has **20** keys. The five missing have **never been recorded once** — not zeroes, absent | Item 180's three detectors all iterate `health.items()`. A key that does not exist cannot be iterated, so 20% of the roster is structurally invisible to every health check this repo has (item 181) |
| **Which five** | AH School District 25 (ics), Palatine CCSD 15 (ics), Palatine D211 (rss), Wheeling Park District (ics), Wheeling CCSD 21 (html) — **four of five are feed fetchers, not scrapes**, and two each sit in Palatine and Wheeling | The two regions with the most dark sources are two of the three regions contributing zero weekend events (item 181) |
| **The subject line, read literally** | The built email is headed *"This weekend across Arlington Heights and Mount Prospect"*. Des Plaines, Palatine and Wheeling contribute **0 weekend events each** | The two regions that recovered are exactly the two with a deep library feed (259, 299). The cap fix lifted the sources that were deep; it did nothing for the ones that were always shallow (item 182) |
| **Springshare LibCal** | `calendar.dppl.org` is a hosted **LibCal** instance, scraped as `html_events` and yielding **3 items**. LibCal publishes documented public RSS (`/rss.php?m=…&iid=…&cid=…`) and iCal endpoints per calendar, no auth | Des Plaines's library is being read through the narrowest available door. The deepest feed in the whole pipeline (MPPL, 299) is the one source already using a real feed instead of a scrape (item 182) |
| **Newsletter referral programs** | The standard growth engine for this category — Morning Brew, The Hustle, 6AM City all built on it. Reported effect: ~15–20% faster growth on digital-only rewards, 50–200% with physical or giveaway tiers. **But the consistent advice is to treat it as an amplifier above ~1,000 subscribers**, and to use direct acquisition below that | `BUSINESS_PLAN.md` says plainly that this newsletter "has no organic growth channel." Referral is the obvious answer and it is genuinely the wrong one at a list of one. Recording the threshold so a future pass does not file it as a P1 (item 183) |
| **The email's own links** | 16 `href`s in `docs/combined-email-send.html`: 5 region pages, 1 sponsor page, 10 outbound event links. **Not one of them is a subscribe link** | The one growth mechanism that costs nothing and works at *any* list size is a subscriber forwarding the email. Right now that forward dead-ends: the neighbour who receives it has nowhere to click to join (item 183) |
| **Subscribable calendar feeds (design/UX)** | A `webcal://` URL tells a calendar app to *subscribe* rather than download once; Google takes `https://calendar.google.com/calendar/r?cid=webcal://…`, Apple and Outlook take the bare `webcal://`. `X-WR-CALNAME` sets the name the subscriber sees, or the feed shows up as "feed.ics" | The site already builds a per-event ICS data URI and a Google Calendar link for every card. A *per-region subscribable* feed is the same data, published once, and it is the only feature on this roadmap that keeps working for a reader who never opens the site again (item 184) |

#### P1 (new)

181. **Five configured sources have never been recorded once, and the
     health file cannot detect its own missing keys.** `config/regions/*.yaml`
     declares 25 sources; `data/source_health.json` holds 20. The gap is
     exact and it is not stale keys — every health key maps to a live
     config entry, so nothing was renamed. The five that have never
     appeared:

     - `arlington-heights-60005:Arlington Heights School District 25 — Calendar` (ics)
     - `palatine-60067:Community Consolidated School District 15 — Calendar` (ics)
     - `palatine-60067:Township High School District 211 — Calendar` (rss)
     - `wheeling-60090:Wheeling Park District — Events` (ics)
     - `wheeling-60090:Wheeling CCSD 21 — Calendar` (html_events)

     The mechanism is a deliberate design decision working exactly as
     written and producing a result nobody intended.
     `build_digest.py`'s fetch loop treats a fetcher returning `None` —
     a transport or parse failure, a 403, a timeout, a non-2xx — as
     *not health signal*, and skips `update_source_health()` entirely.
     Its comment (item 55) argues the case well for the situation it
     was reasoning about: "a 403 or a timeout means the scraper never
     got a chance to work, so it's skipped from history entirely
     rather than recorded as a 0 that looks identical to a genuinely
     dead scraper." That is right for a *one-off* failure. It was
     never considered against a source that fails transport on **every
     build since it was added**, which is what these five are doing —
     and in that case the source does not get a forgiving gap in its
     history, it gets no history at all, forever.

     The consequence is that item 180's work does not cover them.
     `detect_source_regressions`, `detect_truncated_sources` and
     `detect_newly_broken_sources` all open with
     `for key, history in sorted(health.items())`. You cannot detect
     the absence of a key by iterating the keys. The forty-second pass
     wrote that a chronically-dead source "should say so once, not go
     silently unreadable again" — these five never got as far as
     saying it once.

     Note which five they are: **four of the five are `ics` or `rss`
     fetchers**, not HTML scrapes. That is a real signal and worth
     acting on rather than treating the five as unrelated one-offs.
     It is not the `webcal://` scheme in general — three other
     `webcal://` sources (AH Park District 17, MP Park District 15,
     MP D57 66) record fine — so the cause is per-source and needs a
     network-capable run to pin down, which this loop cannot do.

     What to build:

     - **Reconcile config against health at the end of every build.**
       Load the region configs, build the set of expected
       `region:name` keys, diff against `health.keys()`, and report
       anything configured-but-never-recorded alongside the existing
       three detectors. This is the check that turns "the health file
       looks fine" into "the health file covers 20 of 25 sources."
     - **Record a permanent transport failure, without undoing item
       55's reasoning.** Keep the count history clean — a 403 still
       must not be written as a `0` that looks like a dead scraper —
       but track consecutive transport failures per source key
       separately, so a source failing transport on N builds running
       is loud rather than absent. Item 55's concern was about
       *conflating* the two states; the fix is to record both, not to
       record neither.
     - **Then diagnose the five.** Needs real network; this pass
       could not fetch them. Expect some to be genuine 403s (the
       CivicPlus and Finalsite family both rate-limit non-browser
       agents) and some to be moved URLs.

     Priority: this ranks above cosmetic work because it is the same
     class of bug as item 178 — a quiet mechanism producing a
     plausible-looking file that hides the actual state of the
     product — and this file spent three research passes inferring
     around item 178 for exactly that reason.

     🟢 **Shipped 2026-09-22.** Added `expected_source_keys()` and
     `detect_missing_sources()` to `scripts/build_digest.py` — the
     former builds the full `region:name` set from every enabled
     source across `config/regions/*.yaml`, the latter diffs it
     against `health.keys()`. Also added `load_transport_failures()`,
     `update_transport_failures()`, `save_transport_failures()` and
     `detect_chronic_transport_failures()`, backed by a new
     `data/source_transport_failures.json` keyed the same way as
     `source_health.json` but tracking a **consecutive-failure
     streak** per source rather than an item count: it increments on
     every transport failure and resets to 0 on any success, so a
     source that fails once and recovers never gets flagged, but one
     failing on every build accumulates a streak that
     `detect_chronic_transport_failures()` flags once it crosses
     `CONSECUTIVE_TRANSPORT_FAILURE_ALERT_THRESHOLD = 3`. This is
     exactly item 55's own reasoning, applied to the case it never
     considered: the count history stays clean (no `0` written for a
     transport failure), and the "was this a one-off or is it dying"
     question now has its own answer instead of no answer at all.
     `fetch_region_sections()` calls `update_transport_failures()`
     unconditionally for every source (success or failure), right
     alongside the existing `update_source_health()` call.

     One real design decision this item's own wording asked for but
     didn't get: it said "both checks belong in the build, failing
     the job the way item 51's existing regression check already
     does." Checked that against the real, current health file
     before wiring it in — and it would have been wrong to follow
     literally. The five sources this check exists to catch are
     *already missing right now*, so a build-failing version fails
     **every build starting with this one**, including
     `send-newsletter.yml`'s own independent `python
     scripts/build_digest.py` step, which has no
     `continue-on-error`/`if: always()` guarding it. That would
     silently block tomorrow's scheduled send (Wednesday 2026-09-23
     22:37 UTC) — the same send items 175/178 just spent this pass
     unblocking. Wired both new checks in as `logger.warning()` calls
     instead, deliberately **not** added to the existing
     `sys.exit(1)` condition that `detect_source_regressions`,
     `detect_truncated_sources` and `detect_newly_broken_sources`
     share. They stay loud in the build log without withholding
     output, matching the same "never withhold otherwise-good output"
     principle `build-digest.yml`'s own `if: always()` comment (item
     51) already states for the commit step. Also updated
     `build-digest.yml` to commit the new
     `data/source_transport_failures.json` file alongside the other
     generated data files.

     Verified against a real local build: all five sources named
     above in this item's own list logged as warnings, exactly
     matching (no more, no fewer). Added 10 tests to
     `tests/test_build_digest.py` covering the increment/reset
     behavior, the round-trip save/load, the threshold edge (flags at
     3, not below it), and `detect_missing_sources()` against both a
     never-recorded enabled source and a disabled one (which must not
     be flagged). Full suite: 459 passed.

     Diagnosing *why* the five fail transport still needs real
     network access this loop doesn't have — unchanged from this
     item's original scope, now tracked loudly instead of silently.

182. **Three of five regions contribute zero weekend events, and the
     cap fix could never have helped them.** `data/weekend_signal.json`:
     Arlington Heights 3, Mount Prospect 7, **Des Plaines 0, Palatine
     0, Wheeling 0**. The built subject line says so out loud — *"This
     weekend across Arlington Heights and Mount Prospect"* — and the
     body renders the other three as a single consolidated "nothing
     dated yet" row (item 177's fix, working). A Wheeling subscriber
     opens a weekend digest whose subject excludes their town.

     Item 178 raised `MAX_ITEMS_PER_SOURCE` from 6 to 500 and that was
     correct, but it could only ever help a source that *had* more
     than six items behind the cap. Sort the recovered counts and the
     pattern is unambiguous: the two regions that recovered are the
     two holding a genuinely deep library feed (AHML 259, MPPL 299).
     Every other library in the network is shallow — **Des Plaines
     Public Library 3, Palatine Public Library District 12, Indian
     Trails 14** — and those numbers did not move when the cap moved,
     because there was never anything behind the cap to release.
     The weekend digest is, right now, library-powered, and three
     regions have no library supplying it.

     The lead worth chasing is the platform, not the town.
     `calendar.dppl.org` is a hosted **Springshare LibCal** instance
     being read as `html_events`, and LibCal publishes documented
     public feeds — an RSS endpoint of the shape
     `…/rss.php?m=<inst>&iid=<calendar>&cid=<id>` and per-calendar
     iCal exports, both unauthenticated. That is the same trade that
     already produced this pipeline's single best source: Mount
     Prospect Public Library is the one library read through a real
     feed (`mppl.libnet.info` RSS) rather than scraped, and it is the
     deepest source in the network at 299.

     What to do, in order:

     1. Identify the calendar platform behind each of the three
        shallow libraries (LibCal/Springshare, Communico, Libnet and
        LibraryMarket cover most public-library calendars in this
        area), then find that platform's documented public feed
        endpoint rather than scraping its rendered HTML.
     2. Swap the source type from `html_events` to `rss`/`ics` where
        a feed exists, and keep the HTML scrape configured as the
        fallback the fail-soft design already expects.
     3. Re-check `weekend_signal.json` per region afterwards. The
        success criterion is not "more items" — it is **every region
        naming at least one dated weekend event**, because that is
        what the subject line is built from.

     Until then the honest framing for the guard in
     `send_newsletter.py` is worth reconsidering: `MIN_WEEKEND_EVENTS`
     is a *network-wide* floor of 3, and 10 events all sitting in two
     towns passes it while three towns get an empty issue. A
     per-region floor is a different and probably better question than
     a total, but it is a judgement call about what the product
     promises, so it is named here rather than filed as a change.

     🟢 **One of three shipped, 2026-09-22 — Indian Trails switched to
     its real feed; Des Plaines and Palatine researched but not
     guessed.** WebSearch (this loop still has no direct fetch access)
     identified the actual platform behind all three shallow
     libraries rather than assuming from the town name:

     - **Indian Trails Public Library (Wheeling) — CONFIRMED, same
       platform as MPPL.** WebSearch surfaced `indiantrails.libnet.info`
       directly ("Events - Indian Trails Public Library District -
       Communico") — the identical Communico/libnet.info platform
       already proven live for Mount Prospect Public Library, which
       went from 6 (pre-cap) to 299 items on the exact same
       `/feeds?data=<base64 filters>` endpoint this item's own text
       named as the lead worth chasing. The base64 payload is a plain
       JSON filters object with no library ID inside it (decoded and
       confirmed: `{"feedType":"rss","filters":{...}}`), so swapping
       only the subdomain is the whole change, not a guess at a new
       parameter shape. Switched `config/regions/wheeling-60090.yaml`'s
       Indian Trails source from `html_events` (6 items) to `rss`
       pointed at `indiantrails.libnet.info/feeds?data=...`, keeping
       the previous confirmed-live URL and keywords documented in the
       comment as the rollback if this doesn't hold up. Deliberately
       reversing the *previous* build's own reasoning ("switching
       sources without a reason would just add risk") because this
       pass supplies the reason that build didn't have: a same-
       platform swap already proven to work elsewhere, not a fresh
       guess. Local build confirms the new URL is reached and fails
       soft exactly like every other source in this sandbox's blocked
       network (a real `ProxyError`, not a config or parse error);
       real confirmation waits on the next GitHub Actions build, same
       as every other source here. 463 tests still pass — no test
       hardcodes this source's type or URL.
     - **Des Plaines Public Library — platform identified, exact feed
       parameters still unknown.** WebSearch confirms `calendar.dppl.org`
       is a custom-domain alias of a real Springshare LibCal account
       (`dppl.libcal.com` — a search result titled "LibCal - Des
       Plaines Public Library" resolves there), not a guess. LibCal's
       public RSS shape is confirmed too, from three other libraries'
       *working* URLs found by search (`.../rss.php?cid=<id>&iid=<id>&m=<view>`).
       What's missing is the one thing WebSearch summaries can't
       supply: `calendar.dppl.org`'s *own* `iid`/`cid` values, which
       only exist in that page's rendered HTML (typically behind a
       "Subscribe"/RSS icon) — the same class of gap item 179 hit
       researching a village RSS URL, and the same resolution applies:
       named here with the real evidence behind it rather than guessed
       into a config that could silently return 0 items or point at
       someone else's calendar.
     - **Palatine Public Library District — platform still
       unconfirmed, and the URL shape argues against LibCal/Communico.**
       The real, currently-configured URL
       (`palatinelibrary.org/events/upcoming`) and its siblings
       (`/events/list`, `/events/week`, `/events/month/2019/03`) don't
       match either platform's URL grammar — LibCal uses `/calendar`,
       Communico/libnet.info uses `/events` with query params, not a
       `/month/<year>/<month>` path segment. That path shape is a
       distinctive fingerprint of a Drupal-based events calendar
       (Views date-argument routing), not LibCal or Communico, so a
       feed here (if one exists) is more likely a Drupal core/Views
       RSS export at a different path than either platform's
       documented one — worth a real page fetch to confirm rather
       than a second guess layered on an already-uncertain platform
       ID.

     Both remaining gaps need one real page fetch each, not more
     search — recorded honestly as still open rather than closed on
     inference.

183. **A forwarded issue dead-ends: sixteen links in the email and not
     one of them subscribes.** Counted directly in
     `docs/combined-email-send.html`: five region pages, one sponsor
     page, ten outbound event links, and the reply CTA ("Know about
     something we missed? Hit reply"). Nothing a reader can click to
     join the list.

     This matters more than it sounds because of what
     `BUSINESS_PLAN.md` already concedes: "**this newsletter has no
     organic growth channel.** Every subscriber comes from press
     (one-shot), the trade-a-mention barter, SEO (slow), or paid
     acquisition." Forwarding is the one channel that is organic,
     free, and works at a list of one — and it is currently broken at
     the receiving end. The neighbour who gets the email forwarded to
     them has ten ways to reach a library event page and zero ways to
     reach a signup form.

     The fix is small and belongs in the email template, not the
     roadmap's monetization tier: a single line in the footer, above
     the existing reply CTA — *"Get this every Thursday →"* pointing
     at the site's signup — plus an explicit forward prompt. The
     region links already in the email go to region pages; whether
     those pages surface the signup form above the fold is worth
     checking as part of this, since a subscribe link that lands on a
     page where the form is buried is the same dead end one click
     later.

     **And the deliberate non-item:** researched formal referral
     programs this pass and they are the standard answer for this
     category — Morning Brew, The Hustle and 6AM City all grew on
     milestone-reward referral, with reported effects of ~15–20%
     faster growth on digital-only rewards and 50–200% where physical
     rewards or giveaways are involved. The consistent advice is also
     that a referral program is an **amplifier above roughly 1,000
     subscribers** and that below that threshold the effort belongs in
     direct acquisition, because a percentage uplift on a list of one
     is one. This is recorded as a finding precisely so a later pass
     does not file "build a referral program" as a P1 — it is a real
     tactic, correctly sequenced *after* the press pitch (item 77) and
     the barter (item 94), and the footer link above is the part of it
     that is worth building now, since a referral program later needs
     that link to exist anyway.

     🟢 **Shipped 2026-09-22.** Added a gated footer line to both email
     templates (`templates/email_digest.html.j2` and
     `templates/combined_email_digest.html.j2`), above the existing
     item 157 reply CTA: *"Forwarded this? Get your own weekend guide
     every Thursday →"* linking to Buttondown's own hosted subscribe
     page (`https://buttondown.com/<username>`) rather than an
     embedded `<form>` — email clients strip or neuter forms
     inconsistently, a plain link does not. Gated on
     `newsletter.configured` (item 34's existing
     `load_newsletter_config()`), the same on/off switch the rest of
     the newsletter feature already uses, so an unconfigured install
     shows neither line nor a link to nothing. Wired `newsletter`
     through as a new parameter on `render_email_digest()` and
     `render_combined_email_digest()` — neither function received it
     before, since nothing in either template had needed it until now.

     Verified against the real, current `config/newsletter.yaml`
     (`buttondown_username: "andersonryant"`, `configured: True`) with
     a real local build: `docs/combined-email-send.html` now contains
     `Forwarded this? ... https://buttondown.com/andersonryant`. 6 new
     tests (configured/unconfigured × both templates plus the
     combined-issue case), 463 total pass.

     Checked the region-page half of this item's own scope — whether
     the signup form sits above the fold — rather than assuming it
     does: it does not. `templates/region.html.j2`'s form (line ~925)
     sits after the FAQ section, near the very bottom of a
     1221-line template whose hero starts at line 713. A neighbour who
     clicks the new footer link's *region* pages (the ten already in
     the email) would still have to scroll past the whole page to
     find where to sign up. Flagging this honestly rather than folding
     it in here: moving or duplicating the form's position is a real
     UX change to a page already shipped and stable, wider than this
     item's scoped "add a footer line," and deserves its own pass
     rather than riding along on this one.

#### P2 (new)

184. **Publish a subscribable per-region calendar feed — the one
     feature that keeps working for a reader who never comes back.**
     Every event card already builds an ICS data URI and a Google
     Calendar link (both per-event, both one-shot). The missing form
     is the *subscription*: one `webcal://` feed per region, so a
     parent adds "Within Ten — Mount Prospect" to their phone's
     calendar once and the town's events keep appearing next to their
     own plans forever, with no email, no app, and no return visit.

     For a site whose entire value proposition is "we watch the feeds
     so you don't," handing the reader a feed is the most literal
     possible expression of the product. It also fits
     `BUSINESS_PLAN.md`'s hardest constraint better than anything else
     on this list: the build cost is one static file per region
     emitted by an existing pipeline, and the ongoing owner cost is
     zero.

     Mechanics, researched rather than assumed:

     - Publish `docs/<region>/calendar.ics` as a real static file
       (GitHub Pages serves it fine; set `X-WR-CALNAME` to the region
       name or subscribers get a calendar literally named
       "feed.ics").
     - The subscribe link is the *same URL* under the `webcal://`
       scheme — `webcal://withintenmiles.com/<region>/calendar.ics`.
       Apple Calendar and Outlook take that directly; Google needs
       `https://calendar.google.com/calendar/r?cid=webcal://…`. Offer
       both plus a copy-the-URL affordance, because a bare
       `webcal://` link does nothing useful on a desktop with no
       calendar client registered.
     - Include `UID` and `SEQUENCE` per event and keep a stable `UID`
       across rebuilds, or every weekly rebuild duplicates every
       event in every subscriber's calendar. This is the one detail
       that turns the feature from delightful into a reason to
       unsubscribe, so it is worth a test.
     - Scope it to dated, attendable events only — the pipeline
       already carries an `attendable` flag (item 90), and pushing a
       school half-day closure into someone's personal calendar is
       not the same product as pushing a farmers market.

     Sequence this after item 182. A subscribable feed for a region
     that currently produces zero weekend events would be a subscribe
     button that delivers an empty calendar, which is worse than not
     offering it.

Competitors reviewed this pass: **Springshare LibCal** (as a *feed
platform* rather than a competitor — the calendar software behind a
large share of public-library event calendars, including at least one
of this network's own shallow sources, publishing unauthenticated RSS
and iCal endpoints that this pipeline is not using), **newsletter
referral programs** (Morning Brew / The Hustle / 6AM City's shared
growth engine, and the ~1,000-subscriber threshold below which the
advice is consistently *not* to build one), and **subscribable
`webcal://` calendar feeds** as a design/UX pattern (the
platform-specific subscribe-link shapes, `X-WR-CALNAME`, and the
stable-`UID` requirement that keeps a weekly rebuild from duplicating
every event in a subscriber's calendar).


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
- Same for `data/source_health.json` (item 51) and
  `data/source_transport_failures.json` (item 181) — always `git
  restore` both after a local build in this sandbox, never stage
  either. This sandbox's network is blocked, so every source fetches 0
  here; against the real trailing history from actual GitHub Actions
  runs, that reads as every source dying at once and `build_digest.py`
  will legitimately exit 1 - correct behavior, but committing that
  run's health file would poison the real history with a sandbox-only
  false mass-regression.
- Don't add speculative complexity ahead of an actual phase — this is a
  real small business, not a demo.
- Phase 11 is the idea queue, not a spec. Items there are researched
  suggestions, not commitments — implement the ones that serve the business
  plan's constraints (near-zero owner time, sponsor-sellable, no framework
  bloat) and mark the rest `skipped —` with a one-line reason so the
  research loop stops re-suggesting them.
- No human approval needed to merge your own PRs in this repo — squash
  merge once tests pass locally.
- Do not count an unverified rich-result or AI-surface feature as shipped
  progress (item 120). Mark it speculative when added, and re-check each
  quarter — `llms.txt` (item 98), overstated AI Overview reach (item 22),
  and `FAQPage` rich results (item 120) are the three this file has had to
  walk back within a month.
- **When the queue is empty (item 159): verify, don't invent.** An idle
  build loop's failure mode is reaching for a new feature nobody asked
  for, which `DESIGN_PRINCIPLES.md`'s standing question exists to rule
  out. The default instead, in priority order: (1) cross-check
  `data/source_health.json`'s real trailing counts (written by actual
  GitHub Actions runs, never this sandbox's own blocked network — see
  the note above) against each region config's own comments, looking
  for a source that's newly gone quiet without a matching diagnosis;
  (2) spot-check a few of this file's `⚠️`/partial-status items for
  drift the way items 142/147 did wholesale; (3) re-run Lighthouse CI
  locally (`CHROME_PATH=<path to the sandbox's own Chromium>
  npx @lhci/cli collect --staticDistDir=docs ...` — `npx lhci autorun`'s
  plain form fails here with no `CHROME_PATH` set) against the same
  URLs `lighthouserc.json` already asserts, and read the real
  `accessibility`/`best-practices` scores it also collects but doesn't
  gate on; (4) treat a link a genuine visitor would follow (nav, footer,
  a listed source's own site) as worth a WebSearch spot-check — this
  sandbox's `requests`-based fetches 403 on every external domain, but
  WebSearch isn't behind the same block. None of this adds surface
  area; all of it protects the "every listing is real and traceable"
  claim items 131 and 152 rest on.

  First pass run 2026-09-20, item 159's own: no regression found.
  `data/source_health.json`'s four 0-item entries (Downtown MP,
  Experience MP, and Village of Mount Prospect's News *and* Calendar)
  all match their region config's own long-standing 403/JS-rendering
  diagnoses — nothing newly broken. Two low-but-nonzero feeds are worth
  naming as the ones to check first if either ever drops to zero:
  Randhurst Village — Events (steady at 1/build) and Village of
  Palatine — News (steady at 2/build), each under half of any other
  tracked source's count. Items 22 and 35 (this file's two
  `⚠️ first slice done` markers) spot-checked and still accurately
  describe their real, current state — no drift. Lighthouse CI re-run
  locally against all four `lighthouserc.json` URLs: performance,
  accessibility, and SEO all scored a perfect 1.0, comfortably inside
  the asserted LCP/CLS/TBT budgets (worst case 960ms/0/8ms against
  2500ms/0.1/200ms). `best-practices` scored 0.96 on every page, but
  the one flagged item (`errors-in-console`, a failed fetch of Google
  Fonts) is `net::ERR_CERT_AUTHORITY_INVALID` from this sandbox's own
  TLS-intercepting proxy against `fonts.googleapis.com` — the same
  category of sandbox-only false signal item 51 already documents for
  the fetchers, not a real defect in what CI's own unrestricted browser
  would see.

  Second pass, 2026-09-20 (same day, next hourly firing): the first
  pass's own Lighthouse re-run exposed a real gap in what it was
  re-running against — `lighthouserc.json`'s four URLs never included
  item 158's new `/things-to-do/` page, a guide detail page (the only
  template with its own `FAQPage` schema besides things-to-do), or the
  directory page (the only template with a real empty-state UI). All
  three were genuinely unchecked by CI, not just unchecked by this
  pass. Ran them locally the same way as the first pass — clean across
  the board (performance/accessibility/SEO all 1.0, same sandbox-only
  best-practices non-issue) — then added all three to
  `lighthouserc.json`'s own URL list so this coverage is now permanent
  and CI-enforced, not a one-off manual check that goes stale the next
  time a new page template ships. Confirmed the full 7-URL set still
  passes `lhci assert` locally before committing.

  Third pass, 2026-09-20 (same day, third hourly firing since): no new
  research pass, no open issues/PRs, `data/source_health.json` unchanged
  since the last real CI build — so this pass exercised the one
  checklist item the first two hadn't yet: WebSearch-spot-checking a
  genuine visitor's outbound links, not the fetch `sources:` URLs
  `source_health.json` already tracks. Sampled six of the least-stable-
  looking links from `config/regions/*.yaml`'s `evergreen`/`guides`
  entries (the four item-148 HS athletics pages, one named event page,
  one district registration page) — all six resolve and match the
  config exactly, confirmed via `site:` searches returning the exact
  URL with real, current page content. Nothing broken; also separately
  confirmed via the real GitHub Actions run for the previous PR
  (`35530681553`) that CI's own Lighthouse assertions passed for real
  against the expanded 7-URL set, not just in this sandbox's local run.

  Fourth pass, 2026-09-21 (three hourly firings after item 174's CLS
  fix shipped): no new research pass, no open issues/PRs,
  `data/source_health.json` unchanged since the last real CI build.
  Re-checked item (1) first, given item 172's direct stake in it -
  Mount Prospect's four zero/near-zero sources (Village News/Calendar,
  Experience Mount Prospect, Downtown Mount Prospect) still match the
  same 403/JS-rendering diagnoses dated 2026-08-29, confirmed unchanged
  against the redesign PR's own real build log from earlier today
  (run `35614346834`) - no drift, nothing newly broken, nothing a
  User-Agent change could fix that item 161 hasn't already tried. Then
  WebSearch-spot-checked five more outbound Des Plaines evergreen/guide
  links not covered by the third pass's sample (Fall Fest, two Maine
  207 athletics/boundary pages, Taste of Des Plaines, D62's calendar
  page) - all five resolve and match their config descriptions. One
  worth a note, not a fix: `desplainesil.gov`'s Taste of Des Plaines
  page has at least two other historical URL paths still turning up in
  search alongside the current one, meaning that domain has
  reorganized its own URL structure before - the config's current URL
  is live and correct today, but it's the one link in this pass worth
  checking again sooner than the others if it ever 404s.

  Fifth pass, 2026-09-21 (immediately after items 175/176/177 shipped
  and merged - the forty-first research pass's full backlog is now
  clear). Checked `data/source_health.json` against the real post-
  merge build (`8edc704`) rather than assuming the queue is thin -
  item 175's reset key, `palatine-60067:Village of Palatine — News`,
  now shows `[0, 0]`, two real builds confirming the fix holds rather
  than the reset having been a one-off fluke. Two sources dipped from
  a steady 4 to a real 3 in this same build - `des-plaines-60016:Des
  Plaines Public Library — Events` and `wheeling-60090:Village of
  Wheeling — Calendar` - but neither crossed to zero, so
  `detect_source_regressions()` correctly left both alone; read as
  ordinary week-to-week turnover (an event's date passing, a listing
  rotating off), not a fetcher issue, and not worth chasing further
  without a second data point. Also spot-checked items 25, 77, and
  130 - the three `⚠️` markers the thirty-first pass's reconciliation
  deliberately left alone as "a human action is still pending" rather
  than done - against the current "Needs Ryan" section (restructured
  under item 165 this same day): all three still appear there exactly
  as pending (130 as the ranked "Next action," 77 and 25 in "After
  that"/"Small, no-decision-required"), so the markers and the section
  they describe haven't drifted apart from each other.

  Sixth pass, 2026-09-21 (next hourly firing, queue still thin - no
  new research pass since the forty-first). The third and fourth
  passes' WebSearch link-checking had only ever sampled Des Plaines
  and Mount Prospect; this pass covered Palatine instead, given item
  175's fix touched it directly this cycle. Sampled six outbound
  evergreen/guide/annual-event links from `config/regions/
  palatine-60067.yaml`: Fremd HS Athletics, the Village's own Farmers'
  Market page, the Public Library's library-card page, CCSD15's
  registration page, D211's own site, and the Rotary Club's
  Oktoberfest page. All six resolve and match their config
  descriptions exactly - real content, current, at the exact URL
  configured. The Oktoberfest check turned up a genuinely useful
  confirmation rather than just a non-finding: WebSearch's own result
  independently states the 16th Annual Oktoberfest runs Friday–Sunday,
  September 20-22, 2026 - the identical Fri/Sat/Sun the three
  `annual_events` entries for it already carry, confirming the
  config's dates against a source outside this repo, not just
  internal consistency. Nothing broken; nothing to fix.

  Seventh pass, 2026-09-21 (next hourly firing, queue still thin).
  Closed out the WebSearch link-check rotation this item's priority
  list calls for: Wheeling was the other region item 175's fix
  touched directly and the only one of the five not yet sampled by
  any pass (Mount Prospect, Des Plaines ×2, and Palatine already
  covered). Sampled five outbound evergreen/guide links from
  `config/regions/wheeling-60090.yaml`: Wheeling HS Athletics, the
  Village's refuse/recycling page, Indian Trails Library's online-
  card registration, Wheeling Park District's registration page, and
  CCSD21's calendars page. All five resolve and match their config
  descriptions exactly. The CCSD21 check is the more useful of the
  five precisely because it's the same URL `data/source_health.json`
  shows returning a real transport 403 from every fetcher - WebSearch
  confirms the page itself is live and correct at that exact address,
  which rules out "wrong URL" as the cause and leaves the known
  access-blocking diagnosis as the only explanation, consistent with
  what item 161 already found.

  With all five regions now WebSearch-checked at least once across
  these seven passes (Mount Prospect: fourth; Des Plaines: third and
  fourth; Arlington Heights: not yet - the one gap left for a future
  thin-queue pass; Palatine: sixth; Wheeling: this one) and two
  independent `data/source_health.json` drift checks finding nothing,
  this item-159 rotation has covered real ground rather than repeating
  itself. If the next firing finds the queue still this thin, Arlington
  Heights' links are the one remaining unsampled item on this
  checklist; past that, repeating the same checks without new evidence
  to look at stops being verification and starts being motion for its
  own sake - worth saying plainly rather than manufacturing an eighth
  pass that finds nothing new.

  Eighth pass, 2026-09-21 (next hourly firing) - deliberately a
  different angle rather than an eighth link-check, per the seventh
  pass's own note above. Checked the real GitHub Actions run history
  for `build-digest.yml` instead: the last three merges (the fifth/
  sixth/seventh verification-pass PRs, all docs-only) triggered no
  rebuild at all, which looked at first like a gap worth investigating
  rather than assuming. It isn't one - `build-digest.yml`'s `push`
  trigger carries a `paths:` filter
  (`scripts/**`/`templates/**`/`config/**`/its own workflow file), and
  item 168 moved its `schedule` trigger to once a week
  (`17 8 * * 1`, replacing whatever more frequent cadence an earlier
  pass in this file's history had documented) rather than hourly. A
  ROADMAP-only commit correctly changes nothing the site serves, so
  correctly triggers no rebuild; the real code changes earlier this
  cycle (items 175 and 177) each did trigger one, both green (runs
  `35643453169` and `35646601410`).

  That raised a real question worth actually answering rather than
  assuming away: does a week-old `docs/` state risk mailing a stale
  Wednesday newsletter? Read `send-newsletter.yml` directly rather
  than guessing - its own "Build digest" step runs
  `python scripts/build_digest.py` fresh every time, with a comment
  explaining exactly why: "Built fresh rather than trusting whatever
  docs/ happens to hold... mailing a stale digest is worse than not
  mailing." The send path never reads the committed `docs/` at all,
  so the weekly site-rebuild cadence and the send's own freshness are
  fully decoupled by design - nothing to fix, and worth having
  actually read the workflow rather than assumed it from the schedule
  alone.

  Ninth pass, 2026-09-22 (no new research pass yet; items 178/179/180's
  full backlog already shipped and merged). Closed the one remaining
  gap the seventh pass named: Arlington Heights, the last of the five
  regions never WebSearch-checked. Sampled five outbound evergreen/
  guide/annual-event links (John Hersey HS Athletics, the Village's own
  events page, the Library's card-registration page, School District
  25's registration page, and Harmony Fest's real event page) - all
  five resolve and match their config descriptions exactly. The Harmony
  Fest check looked like a real discrepancy at first (WebSearch's own
  results, independent of this repo, returned "October 2-3, 2026" for
  the query) until checking the config directly showed it already says
  exactly that, sourced from a WebSearch the fifteenth research pass
  ran back on 2026-09-15 - a confirmation, not a drift, but worth
  catching the difference between the two before writing either one
  down. All five regions have now been WebSearch-checked at least once;
  the rotation this item's checklist called for is complete, and the
  next thin-queue pass should look for something else rather than
  re-running it a tenth time with nothing new to find.
- **The research loop leaves at most three open owner decisions at a
  time (item 165).** A six-item "Needs Ryan" queue, none of it acted on
  in a week, is itself the finding — presenting equal-looking options
  invites nothing getting picked, and `BUSINESS_PLAN.md`'s founding
  constraint ("near-zero ongoing weekly time") means the owner's
  attention is the actual bottleneck, not this loop's output rate.
  Ranking and naming **one** next action is the research loop's job,
  not the owner's — see the "Needs Ryan" section's own "Next action" /
  "After that" / "Parked" structure for the current example. Past
  three real decisions, a new one gets ranked against the existing
  three and either displaces a parked one or waits, rather than being
  appended as a fourth live option.
