# One-time setup checklist

Everything else runs automatically once these are done. Total time: ~15
minutes.

## 1. Verify feed URLs (~10 min)

This was built in a sandboxed environment with restricted outbound network
access, so the URLs in `config/sources.yaml` are best-known/documented
endpoints, not verified live. From a normal browser:

- [ ] Visit https://www.mountprospect.org/services/news and find the actual
      RSS link (look for an RSS icon or "Subscribe" link; view page source
      and search for `RSSFeed.aspx` or `<link rel="alternate"
      type="application/rss+xml">`). Update `sources.yaml` → "Village of
      Mount Prospect — News" `url`.
- [ ] Visit https://mppl.org/events/ and confirm the events listing loads
      without requiring JavaScript for the first page of results (the
      `html_events` fetcher does a plain HTTP GET, no JS execution). If it
      doesn't work, check whether mppl.org (Communico/LibNet) exposes an
      RSS/ICS export instead and switch the source `type` accordingly.
- [ ] Visit https://www.mppd.org/ and find their calendar's iCalendar (.ics)
      export link (usually a "Subscribe"/"Export" button on the calendar
      page). Update `sources.yaml` → "Mount Prospect Park District —
      Events" `url`.
- [ ] Run `python scripts/build_digest.py` locally and open
      `docs/index.html` in a browser to confirm real content shows up (not
      just the evergreen fallback section).

## 2. Enable GitHub Pages (~3 min)

- [ ] In the repo settings → **Pages**, set source to **Deploy from a
      branch**, branch `main`, folder `/docs`.
- [ ] After the first successful `build-digest` workflow run, the site will
      be live at `https://randerson-23.github.io/agent-business/`.

## 3. First sponsor outreach (~ongoing, a few min/week)

- [ ] Pick 3 local businesses from `SPONSOR_KIT.md`'s target list.
- [ ] Send the cold-intro email from `OUTREACH_TEMPLATES.md`.
- [ ] When one confirms, add an entry to `config/sponsors.yaml` under
      `history` and set `active` to its `id`.

## Ongoing time cost

Once set up, the digest builds and publishes itself weekly with no manual
step. The only recurring work is sponsor sales (a handful of emails a
month) and occasionally re-checking a feed URL if a source's website
changes its structure.
