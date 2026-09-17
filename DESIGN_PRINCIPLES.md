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

**Typography as the primary interface.** Fraunces for headings, Inter
for body, a beige/green palette, generous whitespace. No framework,
because a framework brings its own visual vocabulary (component
shadows, motion defaults, icon sets) that competes with typography for
attention instead of getting out of its way.

**Restraint over accumulation.** No motion for its own sake — the one
animation on the site (native View Transitions on navigation) is a
progressive enhancement with a `prefers-reduced-motion` off-switch, not
a feature. No decorative illustration, no stock photography, no
gradient-mesh backgrounds. The refined serif heading is what signals
editorial polish; a competing visual trend on the same page would
undercut it, not add to it.

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

None of this is a change from what the site already does — the finding
is that the existing direction is already correct and needs writing
down as a **defence**, not that anything needs redesigning.

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
