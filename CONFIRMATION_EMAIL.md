# Confirmation email (ROADMAP.md item 402)

Paste into Buttondown → Settings → Subscribing → Confirmation. Under 80 words.
The variable `confirmation_url` is Buttondown's own (checked against
https://docs.buttondown.com/transactional-emails-confirmation on 2026-10-28),
and its docs say the body must contain it as a link.

**Subject:** Confirm your Within Ten email (one click)

**Body:**

You asked for Within Ten: what's on this weekend in Arlington Heights, Des
Plaines, Mount Prospect, Palatine and Wheeling, every Thursday.

[Click to confirm]({{ confirmation_url }})

Didn't sign up? Ignore this and you'll hear nothing more.

While you're here, this weekend's list:
https://withintenmiles.com/this-weekend/?utm_source=email&utm_campaign=confirm
