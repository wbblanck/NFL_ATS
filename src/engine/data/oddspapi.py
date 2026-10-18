"""OddsPapi (api.oddspapi.io/v4) client: the pieces verified in wbblanck/kmodel.

What kmodel verified from GitHub Actions (2026-09 to 2026-10, MLB):
  * Every data endpoint costs 1 request of the plan (free plan: 250 a month);
    /v4/account is unmetered and reports request_count / request_limit;
    /v4/historical-odds is free (5 s cooldown, at most 3 bookmakers per call,
    history since January 2026 only).
  * /v4/odds-by-tournaments?bookmaker=<book>&tournamentIds=<id> returns every
    fixture of the tournament (today's and later) with that book's current
    markets in one request: fixture -> bookmakerOdds -> <book> -> markets ->
    <marketId> -> outcomes -> <outcomeId> -> players -> <playerId> -> quote.
    A quote holds priceAmerican, price (decimal), changedAt, active.
  * /v4/odds?fixtureId= returned no bookmaker odds.
  * Market ids are global; /v4/markets?sportId= maps each id to marketType,
    handicap and outcome ids.

NOT verified for the NFL: the American-football sport id, the NFL tournament
id, the spread marketType name, the handicap's sign convention, and which books
(Pinnacle in particular) carry NFL spreads. scripts/fetch/oddspapi_probe.py
finds out; nothing in the pick pipeline uses OddsPapi until that is settled.

The key comes only from env ODDSPAPI_API_KEY and is never printed or logged.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time

import requests

BASE = "https://api.oddspapi.io/v4"
KEY_ENV = "ODDSPAPI_API_KEY"
UA = {"User-Agent": "nfl-ats-engine/0.1", "Accept": "application/json"}
RETRY_STATUS = (429, 500, 502, 503, 504)
UNMETERED = {"account", "historical-odds"}


class MissingKey(RuntimeError):
    pass


def _key() -> str:
    k = os.environ.get(KEY_ENV, "")
    if not k:
        raise MissingKey(f"env {KEY_ENV} not set")
    return k


def scrub(text: str, key: str | None = None) -> str:
    """Remove the key from anything that might be printed (URLs, exception text)."""
    key = key if key is not None else os.environ.get(KEY_ENV, "")
    return text.replace(key, "***") if key else text


def call(path: str, *, pause: float = 1.5, tries: int = 3, session=None, **params):
    """GET BASE/path. Returns (status, json or None). Retries 429/5xx; never raises on HTTP errors.
    historical-odds needs pause >= 5 (its cooldown)."""
    key = _key()
    get = (session or requests).get
    status = None
    for attempt in range(tries):
        time.sleep(pause if attempt == 0 else 8)
        try:
            r = get(f"{BASE}/{path}", params={**params, "apiKey": key}, headers=UA, timeout=60)
        except Exception as e:                       # network error: the message can contain the URL
            print(f"oddspapi {path}: {scrub(repr(e), key)[:300]}", file=sys.stderr)
            continue
        status = r.status_code
        if status in RETRY_STATUS and attempt < tries - 1:
            continue
        if status != 200:
            print(f"oddspapi {path} -> HTTP {status}", file=sys.stderr)
            return status, None
        try:
            return status, r.json()
        except ValueError:
            return status, None
    return status, None


def request_count(session=None) -> tuple[int | None, int | None]:
    """(used, limit) this month from the unmetered /account. Only the counts are kept:
    the account body holds the owner's email."""
    _, acct = call("account", session=session)
    for sub in (acct or {}).get("subscriptions") or []:
        if "request_count" in sub:
            return sub.get("request_count"), sub.get("request_limit")
    return None, None


def items_of(resp) -> list:
    """Responses are a list, or a dict with a `data` list, or one object."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        return resp["data"] if isinstance(resp.get("data"), list) else [resp]
    return []


def last_quote(x):
    """A quote is a dict, or (in historical-odds) a list of snapshots: take the latest."""
    if isinstance(x, list):
        x = x[-1] if x else None
    return x if isinstance(x, dict) else None


def parse_ts(s) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def find_ids(rows: list[dict], name_field: str, id_field: str, *needles: str) -> list[tuple]:
    """(id, name) of rows whose name contains every needle (case-insensitive).
    E.g. find_ids(sports, "sportName", "sportId", "american") or
    find_ids(tournaments, "tournamentName", "tournamentId", "nfl")."""
    out = []
    for r in rows or []:
        nm = str(r.get(name_field) or "")
        if all(n.lower() in nm.lower() for n in needles):
            out.append((r.get(id_field), nm))
    return out


def market_types(markets: list[dict]) -> dict[str, int]:
    """marketType -> number of market ids, to see what a sport offers."""
    out: dict[str, int] = {}
    for m in markets or []:
        t = str(m.get("marketType") or "")
        out[t] = out.get(t, 0) + 1
    return dict(sorted(out.items()))


def book_markets(fixture: dict, book: str) -> dict:
    """{marketId: {outcomeId: latest quote}} for one book in one fixture. Player props nest
    quotes under outcomes -> players -> <playerId> (verified, MLB). Whether game lines do too is
    UNVERIFIED: this takes the first entry of a players map if there is one, else the outcome
    itself. Check against the probe's saved response before relying on it."""
    bk = ((fixture.get("bookmakerOdds") or fixture.get("bookmakers") or {}).get(book)) or {}
    out = {}
    for mid, md in (bk.get("markets") or {}).items():
        outs = {}
        for oid, od in ((md or {}).get("outcomes") or {}).items():
            players = (od or {}).get("players")
            q = None
            if isinstance(players, dict) and players:
                q = last_quote(next(iter(players.values())))
            else:
                q = last_quote(od)
            if q:
                outs[str(oid)] = q
        if outs:
            out[str(mid)] = outs
    return out
