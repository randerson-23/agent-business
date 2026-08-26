# One-time setup checklist

Everything else runs automatically once these are done. Total time: ~15
minutes.

## 1. Enable GitHub Pages (~3 min) — do this first

A 404 on `https://randerson-23.github.io/agent-business/` almost always
means this step hasn't been done yet — the build workflow commits the site
to `docs/`, but GitHub Pages itself has to be turned on once by hand.

- [ ] In the repo: **Settings → Pages**. Under "Build and deployment," set
      **Source: Deploy from a branch**, **Branch: `main`**, folder
      **`/docs`**, then Save.
- [ ] Wait a minute or two, then reload
      `https://randerson-23.github.io/agent-business/`.
- [ ] If it's still 404 after ~5 minutes, check the **Actions** tab for a
      failed `pages build and deployment` run and open its log.

## 2. Verify feed sources (~10 min, optional but recommended)

This was built in a sandboxed environment with restricted outbound network
access, so most of `config/regions/mount-prospect-60056.yaml`'s `sources`
started as best-guess URLs. Status as of the last check-in:

- **Village News** — the CivicPlus "list all RSS feed" page doesn't expose
  a plain findable link (neither the build nor a human browsing it could
  find one), so this source no longer uses RSS. It now scrapes
  `mountprospect.org/services/news` directly for news links, same approach
  as the library. Not yet confirmed against a live run — after the next
  scheduled build, check the "Village News" section on the live site. If
  it's still empty, the page's actual link structure may need a tweak in
  `fetch_html_events`'s keyword list or link pattern in `scripts/fetchers.py`.
- **Library Events** — confirmed working (pulls from `mppl.libnet.info`).
- **Park District Events** — URL and `webcal://` scheme handling fixed;
  should be live after the next scheduled build. Worth a spot-check.

To verify or fix a source yourself: open the `url` from the region's YAML
file in a browser, confirm it loads real content without needing
JavaScript, then run `python scripts/build_digest.py` locally and open
`docs/<region-id>/index.html` to see what the fetcher actually extracted.

## 3. First sponsor outreach (~ongoing, a few min/week)

- [ ] Pick 3 local businesses from `SPONSOR_KIT.md`'s target list.
- [ ] Send the cold-intro email from `OUTREACH_TEMPLATES.md`.
- [ ] When one confirms, add an entry under that region's `history` in
      `config/sponsors.yaml` and set the region's `active` to its `id`.

## Ongoing time cost

Once set up, the digest builds and publishes itself weekly with no manual
step. The only recurring work is sponsor sales (a handful of emails a
month) and occasionally re-checking a feed URL if a source's website
changes its structure.
