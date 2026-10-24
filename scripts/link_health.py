"""Weekly outbound-link check (ROADMAP.md item 308).

Reads data/link_candidates.json (written by the build: every event link for
the next 14 days, de-duplicated), sends one polite HEAD request per URL
(falling back to GET where HEAD is refused), at most one request per host per
second, and records the result in data/link_health.json. A link that returns
404 or 410 on two consecutive checks is swapped on its card for the source's
calendar page by build_digest.apply_link_health. A 403, a timeout or any other
status is recorded but never acted on: a bot wall is not a dead page.
"""

from __future__ import annotations

import ipaddress
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetchers import REQUEST_HEADERS, REQUEST_TIMEOUT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = ROOT / "data" / "link_candidates.json"
HEALTH_PATH = ROOT / "data" / "link_health.json"
DEAD = (404, 410)
HEAD_REFUSED = (400, 403, 405, 501)


def load_json(path: Path) -> dict | list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_public_http_url(url: str) -> bool:
    """Only http(s) links to a public host are requested: the candidate list
    comes from untrusted feeds, and the runner must never be pointed at
    localhost, a private or link-local address (such as a cloud metadata
    endpoint) or a non-web scheme."""
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." in host
    return ip.is_global


def check_url(url: str, get=requests.request) -> int | None:
    """Status code for `url`, or None when the request itself failed."""
    try:
        resp = get("HEAD", url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code in HEAD_REFUSED:
            resp = get("GET", url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True, stream=True)
            resp.close()
        return resp.status_code
    except requests.RequestException:
        return None


def next_entry(previous: dict | None, status: int | None, now: str) -> dict:
    was_dead = bool(previous) and previous.get("status") in DEAD
    strikes = (previous.get("strikes", 1) + 1 if was_dead else 1) if status in DEAD else 0
    return {"status": status, "strikes": strikes, "checked_at": now}


def run(candidates: list[dict], previous: dict, *, get=requests.request, sleep=time.sleep, clock=time.monotonic, now: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc).isoformat(timespec="minutes")
    last_hit: dict[str, float] = {}
    health: dict[str, dict] = {}
    for url in sorted({c["url"] for c in candidates if c.get("url") and is_public_http_url(c["url"])}):
        host = urlparse(url).netloc
        wait = 1.0 - (clock() - last_hit.get(host, -1e9))
        if wait > 0:
            sleep(wait)
        last_hit[host] = clock()
        health[url] = next_entry(previous.get(url), check_url(url, get), now)
    return health


def main() -> int:
    data = load_json(CANDIDATES_PATH)
    candidates = data.get("links", []) if isinstance(data, dict) else []
    if not candidates:
        print("No link candidates; nothing to check.")
        return 0
    health = run(candidates, load_json(HEALTH_PATH))
    HEALTH_PATH.write_text(json.dumps(health, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    dead = [u for u, h in health.items() if h["strikes"] >= 2]
    print(f"Checked {len(health)} link(s); {len(dead)} dead on two checks.")
    for u in dead:
        print(f"  DEAD: {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
