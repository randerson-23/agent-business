# Design Principles

Written down because nothing currently protects them (ROADMAP.md Phase
11 #103). Eleven UI features have shipped on this site so far and each
one was individually justified at the time — that's exactly how
accumulation happens. 2026 design research is unusually direct about the
failure mode for a site like this: "the strongest websites will not try
to use twelve trends at once — identify the two or three directions that
fit the audience, execute those with craft, and resist the pull of
everything else." This file is that identification, written down once
so every future pass has something to argue against instead of
re-deriving it from scratch.

## The two directions

**Typography as the primary interface.** Archivo throughout (400/600/800
weights), a near-neutral grey ground (`#f3f2f2` / `#171615` dark), a
single red accent (`#ec3013` on the site, `#ae1800`/`#ff9783` for
accessible text-weight use), zero corner radius, and flat 2px borders
in place of soft shadows — generous whitespace still does the same job
it always did. No framework, because a framework brings its own visual
vocabulary (component shadows, motion defaults, icon sets) that competes
with typography for attention instead of getting out of its way.

*(Redesigned 2026-09-21, item 174, from an earlier Fraunces-heading /
Inter-body / beige-green system — see "Changing this system" below for
why that changed and what the bar is for changing it again.)*

**Restraint over accumulation.** No motion for its own sake — the one
animation on the site (native View Transitions on navigation) is a
progressive enhancement with a `prefers-reduced-motion` off-switch, not
a feature. No decorative illustration, no stock photography, no
gradient-mesh backgrounds. **One accent color, deliberately never a
second one** — the same restraint that used to be expressed through a
refined serif heading is now expressed through a mono-accent, zero-
radius system: a competing visual trend on the same page would undercut
it, not add to it, whichever specific system is currently in place.

## The named referent

"Restraint" is hard to argue against and equally hard to apply — an
adjective gives a future pass nothing concrete to check a proposal
against (ROADMAP.md Phase 11 #113). Two real showcases disagree with
each other and make it specific:

- **Godly** and **SiteInspire** are the standard this site is held to —
  curated at a handful of sites a week, favouring craft over novelty:
  restrained, editorial, typographically considered. That's the two
  directions above, with a name.
- **Awwwards** is explicitly **not** the target — it judges on
  experimental animation, immersive storytelling, and technical
  showcase. Both directions count as "good design"; only one is right
  for a page a parent opens on a phone on a Thursday to find out what's
  on this weekend.

Concretely, that means: no scroll-driven animation, no immersive intro,
nothing that delays the first event appearing on the page. This isn't
hypothetical caution — item 19's `animation-timeline: view()` experiment
already failed real CI on LCP and TBT once, and it arrived dressed as
exactly the kind of modern touch an Awwwards-direction proposal looks
like. The next one will too.

## What these rule out

- A component library or CSS framework (Tailwind, Bootstrap, a design
  system) — it would bring its own typographic and spacing defaults
  that fight the two directions above.
- Decorative animation, parallax, or scroll-triggered effects.
- Stock photography or illustration as page furniture.
- A third accent color, a second display typeface, or any addition
  whose primary job is to look modern rather than to make the content
  easier to read or use.
- Dense, dashboard-style information density. This is a reading
  experience, not a control panel.

This described the site's original direction as a **defence** against
accumulation, not a call to redesign — and then item 174 redesigned it
anyway, to the system described above. The redesign held the same two
directions (typography-first, one accent, no framework); what it
changed was execution, not the argument. The research pass that found
it (item 176) put it plainly: the execution was careful, but a full
palette and typeface change happening while the build loop was idle is
exactly the failure mode this file exists to catch, whether or not the
result is good.

## Changing this system

A change to the palette, typeface, or layout system needs a **stated
reason a reader would notice** — not "this looks more current" or "I
was idle and it seemed worth trying" — written down in the commit or
PR *before* the work, the same bar this file already applies to adding
a feature (see "The standing question" below). "A reader would notice"
rules out anything whose actual motivation is that the builder found
the old system slightly dated: restraint doesn't go stale on its own
schedule.

This doesn't ban redesigning. It bans redesigning as a way to fill
otherwise-idle time. If the next redesign has a real, stated reason
(item 158's `/things-to-do/` pages needed real accessible-contrast
text on the accent color, say, and the color didn't have one at the
weight needed) — write that reason down first, then do the work. If
the honest reason is "nothing else was actionable" — that's exactly
what item 159's "verify, don't invent" standing work exists to absorb
instead.

## Permanent URLs

Seasonal and recurring pages keep one permanent URL forever; the year
lives in the content, never in the path. `/trick-or-treat/`, not
`/trick-or-treat-2026/`; a recurring farmers market keeps its one guide
URL updated in place, not a fresh URL per season or per date.

This isn't a style preference — it's the same "restraint over
accumulation" argument the rest of this file makes, applied to search
authority instead of visual noise. The 2026 SEO research behind
ROADMAP.md item 158 is explicit that a "things to do" or seasonal-guide
page **compounds**: it accumulates backlinks, search history, and rank
for as long as it keeps the same address. A new URL per year or per
event instance starts that clock over from zero every time, which is
the one mistake a small, evergreen aggregator can least afford.

`tests/test_build_digest.py::test_collect_sitemap_urls_never_contains_a_year`
(ROADMAP.md item 160) makes this enforceable rather than aspirational —
it fails if any generated path matches a bare four-digit year.

## The standing question

Before adding any new UI element, answer this in the PR or commit
message: **does this earn its place, or is it one more thing?**

A feature earns its place when a reader would genuinely miss it if it
were gone — it answers a real question faster, removes a real step, or
surfaces information that would otherwise require leaving the page.
"Competitors have it" is explicitly **not** a justification: the site
already has most of the features its competitors have. What it does
not yet have is readers, and a feature nobody asked for doesn't fix
that — distribution does (see `ROADMAP.md`'s current priority order).

When in doubt, the default is no. A missing feature costs nothing; an
added one costs maintenance, page weight, and a small amount of the
visual restraint that is the actual differentiator here.
