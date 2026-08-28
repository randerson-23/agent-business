# Business Plan — 60056 (Mount Prospect, IL)

> **2026-08-26 update**: the direction expanded from a single ZIP digest
> into a multi-ZIP weekend/trip-planner site (locals planning a weekend,
> visitors planning a trip across a few nearby towns), with tag-based
> filtering (kid-friendly, dog-friendly, free, indoor/outdoor, ...) and
> at-a-glance event cards. The rationale and phased plan for that live in
> [`ROADMAP.md`](ROADMAP.md); everything below is the original plan this
> grew out of and is still accurate for the 60056 region specifically.

## Constraints driving the choice

- Full-time job + two small children → **near-zero ongoing weekly time**.
- Physical is fine, but must not eat significant hours.
- Should be buildable and largely automated in a code repo (this one).

## Who lives here (ZIP 60056)

Quick research on the target ZIP before picking an idea:

- Population ≈ 57,000, median household income ≈ $102K (above national median).
- 47% hold a bachelor's degree or higher; median age 41; 56.5% married.
- Middle/upper-middle class, family-heavy suburb of Chicago (Cook County).
- Well-served by a village government (mountprospect.org), a strong public
  library (mppl.org), and a park district (mppd.org) — all publish public
  event/news feeds, but none of it is aggregated in one place.

Sources: zip-codes.com, city-data.com, unitedstateszipcodes.org (60056 profile pages).

## Ideas considered

1. **Hyperlocal digest + local-business sponsorships** (chosen) — aggregate
   village news, library programs, and park district events into a weekly
   page/email for 60056 families; sell a "this week's sponsor" slot to local
   businesses (pediatric dentist, ice cream shop, real estate agent, etc.).
   Content generation is fully automatable; the only recurring human time is
   sponsor sales/onboarding.
2. **Local service lead-gen microsite** (e.g. "best lawn care in Mount
   Prospect") — SEO content site earning affiliate/referral fees. Rejected
   for now: SEO payoff is slow (6–12 months) and requires continuous content
   writing to rank, which competes for the same scarce hours.
3. **Print-on-demand shop with Mount Prospect-themed designs** (mugs, tees,
   tote bags for "60056" pride, school mascots, park district 5K shirts).
   Rejected as the *primary* bet — no recurring local data pipeline to build
   in code, more of a one-off design task, and demand is thin without an
   existing audience to sell into.
4. **Kids' activity finder / babysitting co-op matching app** — high value
   to the exact demographic (young families) but touches child-safety and
   trust/liability concerns that need real operational attention, not a
   "set it and forget it" system. Rejected for time-budget reasons.
5. **Neighborhood newsletter run manually (like a mini-Patch)** — same
   audience as #1 but written by hand every week. Rejected because it
   doesn't scale with limited hours; #1 keeps the same value prop but
   automates the labor-intensive part.

## Chosen idea: "60056 Weekly" — an automated hyperlocal digest

A weekly, auto-generated web page (and later, email) for Mount Prospect, IL
residents, pulling from public feeds:

- Village of Mount Prospect news/announcements
- Mount Prospect Public Library events
- Mount Prospect Park District events
- A rotating **"This Week's Local Sponsor"** spot sold to one nearby small
  business per week

### Why this fits the constraints

- **Time**: content aggregation runs on a schedule (GitHub Actions cron) with
  no human in the loop. The only recurring work is periodic sponsor outreach
  (a handful of emails a month) and updating feed configs if a source moves.
- **Audience fit**: 60056 is affluent, highly educated, family-dense, and
  currently has no single aggregator of village + library + parks info — the
  three biggest sources of "what's happening" for local families.
- **Monetization is local and small**: a $25–$75/week sponsor spot is an easy
  yes for a local business owner (dentist, tutoring center, ice cream shop,
  realtor) and doesn't require ad-network scale or approval.
- **Built entirely as code**: fetch scripts, a digest generator, a static
  site, and a scheduled workflow — no physical inventory, no shipping, no
  shift work.

### Monetization

Repriced around annual memberships, not weekly ad slots (ROADMAP.md
Phase 11 #29 — a fourth-pass research finding: the closest real business
analogue, a 15-year-old hyperlocal-newsletter network, monetizes this
exact way specifically to reduce how often a sponsor needs re-selling).
A membership renews once a year instead of needing roughly fifty
re-sells, which is what actually keeps sponsor work inside the 30-60
minutes/month budget below as this scales past one sponsor.

| Tier | Price | What they get |
|---|---|---|
| Annual Partner | $1,200/year | Permanent directory listing + a seasonal-guide spotlight + a live SEO backlink + priority Editor's Pick consideration |
| Neighborhood Authority (1/region) | $5,000/year | Everything in Annual Partner, held exclusively for the region year-round — priced for the real-estate "neighborhood farming" budget category ($500-1,500/month) |
| Weekly Spot (1 slot/region) | $50/week or $175/month | Top banner + 2-sentence blurb + link, week-to-week |
| Event Promo | $20 one-time | A single event/announcement boosted to the top of "This Week" |

Break-even is trivial: hosting is free (GitHub Pages), the only cost is time.
One Annual Partner already covers years of hosting and any tooling.

### Time budget

- **Build (this repo, now)**: automation pipeline, site, sponsor kit — done
  in code, no manual weekly labor once shipped.
- **Ongoing**: ~30–60 minutes/month — reviewing the auto-generated digest
  before it publishes (optional spot-check), sending a few sponsor emails,
  invoicing. No writing, no scraping, no design work per issue.

### Roadmap

1. ✅ Repo scaffold + business plan (this document)
2. Data-fetch scripts for village/library/park-district public feeds
3. Digest generator → static HTML page (GitHub Pages via `docs/`)
4. Scheduled GitHub Actions workflow (weekly cron) to run the pipeline
5. Sponsor media kit + outreach email templates
6. First 3 real sponsor outreach emails sent manually (outside this repo)
7. Optional: email delivery (e.g. Buttondown/Mailchimp free tier) once there
   is a subscriber list worth mailing
8. Optional: expand to neighboring ZIPs (60004, 60005) once 60056 is proven

### Risks / notes

- Public feed URLs for the village/library/park district need to be
  confirmed against the live sites (this build environment's outbound network
  is restricted to a small allowlist, so exact feed URLs are configured in
  `config/regions/*.yaml` for a human — or a future session with fuller network
  access — to verify/update in ~10 minutes). The pipeline is written to fail
  soft: any one source failing to fetch does not break the digest.
- No personal data is collected in v1 (no signup form yet), so there's no
  privacy/compliance surface to maintain.
