"""OddsLink (oddslink.app/v1) discovery probe for NFL spreads (oddslink-probe.yml, workflow_dispatch only).

From the docs (rendered 2026-10-18, docs/evidence/probe/20261018T231019Z/): key in header X-API-Key;
GET /v1/sports/{sport}/odds lists fixtures not yet started, counts once per call; outcomes are named after
home_team / away_team with price and point and a main flag; oddsFormat=decimal available.

Questions: the NFL sport key, Pinnacle's bookmaker key, whether Pinnacle has NFL spreads now, and what the
response headers say about the allowance. About 3 calls. The key comes only from env ODDSLINK_API_KEY
(repo secret ODDS_LINK) and is never printed. Saves under docs/evidence/probe/<stamp>/oddslink_*.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

BASE = "https://oddslink.app/v1"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "evidence" / "probe" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG = []


def log(s=""):
    print(s)
    LOG.append(s)


def get(path, key, **params):
    try:
        r = requests.get(f"{BASE}/{path}", params=params, timeout=90,
                         headers={"X-API-Key": key, "Accept": "application/json", "User-Agent": "nfl-ats-engine/0.1"})
    except Exception as e:
        log(f"GET {path} failed: {type(e).__name__}")
        return None, None
    hdr = {k: v for k, v in r.headers.items()
           if any(w in k.lower() for w in ("limit", "remaining", "used", "quota", "request", "credit", "plan"))}
    log(f"GET /{path} {params} -> HTTP {r.status_code}, {len(r.content)} bytes; headers {hdr}")
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None


def save(name, obj):
    (OUT / f"oddslink_{name}.json").write_text(json.dumps(obj, indent=1)[:3_000_000])


def main():
    key = os.environ.get("ODDSLINK_API_KEY", "")
    if not key:
        print("ODDSLINK_API_KEY is not set: the workflow passes it from the repository secret ODDS_LINK.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"# OddsLink NFL probe {OUT.name}\n")
    s, sports = get("sports", key)
    save("sports", sports)
    rows = sports if isinstance(sports, list) else (sports or {}).get("data") or []
    nfl = [x for x in rows if isinstance(x, dict) and "nfl" in json.dumps(x).lower()]
    log(f"sports rows {len(rows)}; NFL-like: {json.dumps(nfl)[:800]}")
    keys = [x.get("key") for x in nfl if x.get("key")]
    sport = next((k for k in keys if k in ("americanfootball_nfl", "nfl")), keys[0] if keys else "americanfootball_nfl")
    log(f"using sport key {sport!r}")
    for name, params in (("pinnacle", {"bookmakers": "pinnacle"}), ("all", {})):
        s, ev = get(f"sports/{sport}/odds", key, markets="spreads", oddsFormat="decimal", **params)
        save(f"odds_{name}", ev)
        evs = ev if isinstance(ev, list) else []
        if not evs:
            log(f"  {name}: no fixtures; body {json.dumps(ev)[:400]}")
            continue
        books = sorted({b.get("key") for e in evs for b in e.get("bookmakers") or []})
        log(f"  {name}: {len(evs)} fixtures; books {books}")
        for e in evs[:3]:
            pin = [b for b in e.get("bookmakers") or [] if b.get("key") == "pinnacle"]
            main = [(o.get("name"), o.get("point"), o.get("price"), o.get("main"))
                    for b in pin for m in b.get("markets") or [] if m.get("key") == "spreads" and "period" not in m
                    for o in m.get("outcomes") or [] if o.get("main")]
            log(f"    {e.get('away_team')} @ {e.get('home_team')} {e.get('commence_time')} pinnacle main {main} "
                f"last_update {[b.get('last_update') for b in pin]}")
    (OUT / "oddslink_summary.md").write_text("\n".join(LOG) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
