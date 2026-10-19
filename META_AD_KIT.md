# Halloween ad kit (ROADMAP.md items 276, 344)

Everything for the $50 Meta test in one place. About ten minutes in Ads
Manager. Written by the build loop; the owner decides (item 276) and runs it.

## Landing URL

```
https://withintenmiles.com/trick-or-treat/?utm_source=meta&utm_campaign=halloween-2026
```

The page has the hours table and, directly under it, the email signup
(item 345). No Meta pixel is installed or needed.

## Ad copy (primary text, each under 125 characters)

1. `Trick-or-treat hours for Arlington Heights, Mount Prospect, Palatine, Des Plaines and Wheeling, in one place.`
2. `Halloween is a Saturday. Find your town's trick-or-treat hours here, from each village's own page.`
3. `Trick-or-treat hours, five northwest suburbs. Plus a free Thursday email of what's on that weekend.`

Headline (any variant): `Trick-or-treat hours 2026`. Button: Learn more.

## Creatives

Regenerated on every build from the page's own data, in trick-or-treat
season only, and labelled "Hours from each village's own page":

- `https://withintenmiles.com/ads/tot-square.png` (1080 x 1080, feed)
- `https://withintenmiles.com/ads/tot-portrait.png` (1080 x 1350, feed)
- `https://withintenmiles.com/ads/tot-story.png` (1080 x 1920, Stories and Reels)

Download them from those URLs (or from `docs/ads/` in the repo) shortly
before you create the ad, so the hours in the image match the page. Mount
Prospect, Wheeling and Arlington Heights show their qualifier ("standing" or
"recommended") exactly as the page does. Do not edit the images by hand.

## Audience

Location type: **People living in this location**. ZIP codes:

- 60004 (Arlington Heights, northern part; named in item 276)
- 60005 (Arlington Heights)
- 60016 (Des Plaines)
- 60056 (Mount Prospect)
- 60067 (Palatine)
- 60090 (Wheeling)

Item 344 asks for eight ZIP codes, but the repo's region configs hold five
and item 276 names these six. Ads Manager's location search will show any
other ZIP that belongs to the same towns (for example other Palatine or
Wheeling ZIPs); add only ZIPs you can confirm. Ages 25 to 54. No interest
targeting. Not a special ad category.

## Settings

- Objective: **Traffic**, optimise for **landing page views**.
- Budget: **$5 a day**, **Oct 22 to Oct 31** (10 days, $50).
- Placements: Facebook Feed, Instagram Feed, Facebook Stories and Reels,
  Instagram Stories and Reels. **Audience Network off.** Manual placements,
  not Advantage+ placements.
- Needs a Facebook Page for Within Ten (it can stay minimal) and an ad
  account with a card.

## The one success rule

Under **$1 per confirmed subscriber**, counted from Buttondown
subscribers tagged `utm_source=meta` (not Meta's own clicks). GoatCounter
shows the visits. Above $3 per subscriber, stop and keep the lesson.
