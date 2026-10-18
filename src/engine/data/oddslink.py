"""OddsLink (oddslink.app/v1): Pinnacle spreads as a backup market source.

Verified 2026-10-18 (docs/evidence/probe/20261018T231335Z/): key in header X-API-Key (env ODDSLINK_API_KEY,
repo secret ODDS_LINK); NFL sport key "nfl"; GET /v1/sports/nfl/odds?bookmakers=pinnacle&markets=spreads
&oddsFormat=decimal returns fixtures not yet started, 1 request per call (headers X-Requests-Used /
X-Requests-Remaining; 1,000 a month on this key; rate limit 2 per second). Fixtures carry home_team /
away_team; spread outcomes are named after the teams with point (that team's line) and price, a full-game
market has no `period` field, and each ladder flags its main line `main`. The `main` flag picked a junk
Circa line (-7.5 at 3.80) on 2026-10-18, so the most balanced active two-sided line is used instead.
Pinnacle matched OddsPapi for WAS @ SF (-7.5) the same evening.

The key is never printed or logged.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import requests

from engine.teams import UnknownTeam, to_canonical

BASE = "https://oddslink.app/v1"
KEY_ENV = "ODDSLINK_API_KEY"
SPORT = "nfl"


class MissingKey(RuntimeError):
    pass


def fetch_pinnacle_spreads(session=None) -> list[dict]:
    key = os.environ.get(KEY_ENV, "")
    if not key:
        raise MissingKey(f"env {KEY_ENV} not set")
    r = (session or requests).get(f"{BASE}/sports/{SPORT}/odds",
                                  params={"bookmakers": "pinnacle", "markets": "spreads", "oddsFormat": "decimal"},
                                  headers={"X-API-Key": key, "Accept": "application/json",
                                           "User-Agent": "nfl-ats-engine/0.1"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"OddsLink HTTP {r.status_code}")     # no URL or key in the message
    print(f"OddsLink requests used {r.headers.get('X-Requests-Used')}, remaining "
          f"{r.headers.get('X-Requests-Remaining')}", file=sys.stderr)
    body = r.json()
    return body if isinstance(body, list) else []


def home_main_spread(event: dict, book: str = "pinnacle", max_hold: float = 0.10) -> dict | None:
    """The most balanced full-game spread line for `book`: (home point, home and away decimal prices)."""
    home, away = event.get("home_team"), event.get("away_team")
    best = None
    for b in event.get("bookmakers") or []:
        if b.get("key") != book:
            continue
        for m in b.get("markets") or []:
            if m.get("key") != "spreads" or "period" in m:
                continue
            outs = m.get("outcomes") or []
            for h in (o for o in outs if o.get("name") == home and o.get("point") is not None):
                a = next((o for o in outs if o.get("name") == away and o.get("point") is not None
                          and abs(float(o["point"]) + float(h["point"])) < 1e-9), None)
                if a is None:
                    continue
                try:
                    ph, pa = 1 / float(h["price"]), 1 / float(a["price"])
                except (TypeError, ValueError, ZeroDivisionError):
                    continue
                hold = ph + pa - 1
                if hold > max_hold:
                    continue
                cand = {"home_spread": float(h["point"]), "home_price_decimal": float(h["price"]),
                        "away_price_decimal": float(a["price"]), "hold": round(hold, 4),
                        "p_home_devig": round(ph / (ph + pa), 4),
                        "changed_at": m.get("last_update") or b.get("last_update")}
                if best is None or abs(cand["p_home_devig"] - 0.5) < abs(best["p_home_devig"] - 0.5):
                    best = cand
    return best


def pinnacle_capture_rows(due_games: list[dict], now: dt.datetime, *, events: list[dict] | None = None,
                          capture_id: str = "") -> list[dict]:
    """market_captures rows (book "pinnacle", reason "oddslink") for due games OddsLink lists with a Pinnacle line."""
    events = events if events is not None else fetch_pinnacle_spreads()
    rows = []
    for e in events:
        try:
            home, away = to_canonical(e.get("home_team") or ""), to_canonical(e.get("away_team") or "")
        except UnknownTeam:
            continue
        g = next((g for g in due_games if g["home_team"] == home and g["away_team"] == away), None)
        if g is None:
            continue
        try:
            start = dt.datetime.fromisoformat(str(e.get("commence_time")).replace("Z", "+00:00"))
            if abs((start - g["kickoff_utc"]).total_seconds()) > 36 * 3600:
                continue
        except ValueError:
            pass
        m = home_main_spread(e)
        if not m:
            continue
        rows.append({"capture_id": capture_id, "captured_at": now.isoformat(), "game_id": g["game_id"],
                     "season": g["season"], "week": g["week"], "home_team": home, "away_team": away,
                     "kickoff_utc": g["kickoff_utc"].isoformat(), "lock_utc": g["lock_utc"].isoformat(),
                     "minutes_to_lock": round((g["lock_utc"] - now).total_seconds() / 60, 1),
                     "book": "pinnacle", "home_spread": m["home_spread"],
                     "home_price_decimal": m["home_price_decimal"], "book_last_update": m["changed_at"],
                     "market_last_update": m["changed_at"], "provider_event_id": e.get("id"),
                     "status": "ok", "reason": "oddslink"})
    return rows
