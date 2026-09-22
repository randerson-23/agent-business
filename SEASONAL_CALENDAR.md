# Seasonal Calendar

Written down because seasonal content has been found one at a time, two
weeks out, by luck rather than by system (ROADMAP.md Phase 11 #112).
Item 101's trick-or-treat page worked out, but only because someone
happened to notice Halloween was close; the same near-miss with a
shorter runway would have meant publishing after the search interest
had already peaked. This file is the fix: every seasonal window worth
covering, named once, with the lead time it needs — so a future pass
checks this list instead of re-discovering the next one under time
pressure.

**How to use this**: at the start of each month, check whether anything
below falls inside its lead-time window and, if so, treat starting it as
a live task even if nothing else on ROADMAP.md points to it that day.

| Window | When it happens | Start by | What "started" means |
|---|---|---|---|
| Trick-or-treat hours | Last week of October | Mid-September | ✅ Done (item 101) — one page, now all five towns' official hours (the page's own "towns" count is templated off `region_summaries`, so Wheeling's 2026-09-21 addition picked it up automatically — no template edit needed). Writing this row down is what caught a real gap: the page had been live and in the sitemap since it shipped, but no region or hub page ever linked to it — reachable only by a crawler, not an actual visitor. Fixed the same day (a seasonal `is_trick_or_treat_season()` footer link, Sep 1 – Nov 5) rather than left for a future pass. |
| Holiday lights & Santa visits | Late Nov – Dec | Late October | Not started. Village/park-district holiday-lighting ceremonies and Santa visits/photo events, one page per region or one combined page — same shape as trick-or-treat. |
| Chicago Northwest Restaurant Week | Late Feb – early Mar (exact dates move year to year — confirm from chicagonorthwest.com close to the window; do not publish a specific date range from search results alone, which gave two different answers for the same edition when this was researched) | Early January | Not started. **Correction, 2026-09-22: this row's own "precisely these four towns" framing (see ROADMAP.md item 112) was never actually verified against the event's real participant list, and checking it now (WebSearch, cross-confirmed twice) finds the opposite — the event's official towns are Arlington Heights, Elk Grove Village, Itasca, Rolling Meadows, Roselle, Schaumburg, Streamwood, and Wood Dale. Of this site's five regions, only Arlington Heights is actually on it; Mount Prospect, Des Plaines, Palatine, and Wheeling are not.** Not a "covers all regions at once" page after all — at most an Arlington Heights-only seasonal note, and worth re-confirming the town list itself close to the 2027 window before building anything, since restaurant participation (not town coverage) is what actually varies year to year. Main Line Today — this file's own model for the send-time research — runs its own version of a restaurant week feature and sells sponsorship partly on it, for a market where it fits its whole coverage area; that model doesn't transfer here the way this row assumed. |
| Summer day camps & park-district registration | Camps run Jun – Aug; registration for many opens as early as Feb | Late January | Not started. This is the highest-intent search window of the four (parents actively planning and paying, not browsing) and shares real infrastructure with the existing birthday-party/kids'-classes guide. |
| Farmers markets (seasonal open) | May – Oct, varies by town | Mid-April | Partially covered, unevenly — Palatine's seasonal-circuit guide links its farmers market's own stable page; Mount Prospect's points to the Village's general calendar rather than a dedicated page. Des Plaines deliberately has neither (item 104: search results on it were conflicting - a stale "ended in 2016" report next to directories still listing it active - and were left out rather than guessed at, per this file's own standard; see the Restaurant Week row). Arlington Heights has no entry either. Worth a pass each spring to re-check Des Plaines and Arlington Heights with fresh search results, not just carry the omission forward by default. |

## Why dates aren't hard-coded here

Two independent web searches for Chicago Northwest Restaurant Week's
next edition returned two different specific date ranges for what was
represented as the same event — a concrete instance of exactly the
failure mode `BUSINESS_PLAN.md` and every guide-writing pass since have
tried to avoid: a synthesized search answer stating a specific date
with more confidence than the underlying sources support. The fix
applied throughout this project (item 104's Des Plaines farmers-market
omission is the clearest precedent) is the same one applied here:
when a specific fact can't be verified from a source stable enough to
trust, don't publish it — verify closer to the date instead, the same
way item 101's trick-or-treat hours were confirmed roughly two weeks
out rather than guessed five months out.

## What this list is not

Not a commitment to build all five as pages — `DESIGN_PRINCIPLES.md`'s
standing question still applies to each one when its lead time arrives:
does this earn its place, or is it one more thing. It's a commitment to
*consider* each one on time, which is the part that was missing.
