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
import json
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


# --- NFL spreads (verified by the 2026-10-18 probe; .claude/skills/oddspapi-api/SKILL.md) ---

NFL_SPORT, NFL_TOURNAMENT = 14, 31
SPREAD_MARKETS_FILE = "oddspapi_nfl_spread_markets.json"     # under config.path("lines")


def load_spread_markets(path) -> dict[str, tuple[float, str, str]]:
    """{marketId: (home handicap, home outcomeId, away outcomeId)}: full-game spreads only
    (period "result"). Outcome "1" is participant1 = the home team; handicap is the home line."""
    with open(path) as fh:
        return {k: (float(v[0]), str(v[1]), str(v[2])) for k, v in json.load(fh).items()}


def _dec(q) -> float | None:
    try:
        p = float(q.get("price"))
        return p if p > 1 else None
    except (TypeError, ValueError):
        return None


def _snapshots(outcome) -> list[dict]:
    players = (outcome or {}).get("players")
    x = next(iter(players.values())) if isinstance(players, dict) and players else outcome
    x = x if isinstance(x, list) else [x]
    return [s for s in x if isinstance(s, dict)]


def _row(handicap, hq, aq, ts_field):
    h, a = _dec(hq), _dec(aq)
    if h is None or a is None:
        return None
    ph, pa = 1 / h, 1 / a
    return {"home_spread": handicap, "home_price_decimal": h, "away_price_decimal": a,
            "hold": round(ph + pa - 1, 4), "p_home_devig": round(ph / (ph + pa), 4),
            "changed_at": hq.get(ts_field) or aq.get(ts_field)}


def _balanced(cands: list[dict], max_hold: float) -> dict | None:
    ok = [c for c in cands if c and c["hold"] <= max_hold]
    return min(ok, key=lambda c: abs(c["p_home_devig"] - 0.5)) if ok else None


def main_spread_at(book_hist: dict, smap: dict, t: dt.datetime, max_hold: float = 0.10) -> dict | None:
    """From one book's /historical-odds markets: the most balanced full-game home spread whose
    latest snapshots at or before `t` are active on both sides (history has no mainLine flag).
    Adds n_lines (two-sided active lines at t) and first_seen (earliest snapshot of any line)."""
    cands, first = [], None
    for mid, md in (book_hist.get("markets") or {}).items():
        if mid not in smap:
            continue
        hcap, ho, ao = smap[mid]
        outs = (md or {}).get("outcomes") or {}
        side = {}
        for oid in (ho, ao):
            snaps = [s for s in _snapshots(outs.get(oid)) if parse_ts(s.get("createdAt"))]
            for s in snaps:
                ts = parse_ts(s["createdAt"])
                first = ts if first is None or ts < first else first
            before = [s for s in snaps if parse_ts(s["createdAt"]) <= t]
            side[oid] = max(before, key=lambda s: parse_ts(s["createdAt"])) if before else None
        hq, aq = side[ho], side[ao]
        if hq and aq and hq.get("active") and aq.get("active"):
            cands.append(_row(hcap, hq, aq, "createdAt"))
    best = _balanced(cands, max_hold)
    if best:
        best["n_lines"] = sum(1 for c in cands if c)
    return {**best, "first_seen": first.isoformat() if first else None} if best else None


def main_spread_live(fixture: dict, book: str, smap: dict, max_hold: float = 0.10) -> dict | None:
    """From odds-by-tournaments: the full-game spread the book flags mainLine (else the most
    balanced active one), with limit and n_lines."""
    cands = []
    for mid, outs in book_markets(fixture, book).items():
        if mid not in smap:
            continue
        hcap, ho, ao = smap[mid]
        hq, aq = outs.get(ho), outs.get(ao)
        if not (hq and aq and hq.get("active") and aq.get("active")):
            continue
        r = _row(hcap, hq, aq, "changedAt")
        if r:
            r["main_flag"] = bool(hq.get("mainLine") or aq.get("mainLine"))
            r["limit"] = hq.get("limit")
            cands.append(r)
    flagged = [c for c in cands if c["main_flag"] and c["hold"] <= max_hold]
    best = flagged[0] if len(flagged) == 1 else _balanced(cands, max_hold)
    return {**best, "n_lines": len(cands)} if best else None


def pinnacle_capture_rows(due_games: list[dict], now: dt.datetime, smap: dict, *, call_fn=None,
                          capture_id: str = "") -> list[dict]:
    """Pinnacle's live full-game spread for each due game, as market_captures rows (book "pinnacle",
    reason "oddspapi"). 2 requests: /fixtures around the due kickoffs (team names) and
    odds-by-tournaments for Pinnacle. Games OddsPapi does not list, or lists without an active
    Pinnacle line, get no row. Owner decision 2026-10-18: Pinnacle source while Parlay API is down."""
    from engine.teams import UnknownTeam, to_canonical
    call_fn = call_fn or call
    if not due_games:
        return []
    ks = [g["kickoff_utc"] for g in due_games]
    lo, hi = min(ks) - dt.timedelta(hours=2), max(ks) + dt.timedelta(hours=2)
    s, fx = call_fn("fixtures", tournamentId=NFL_TOURNAMENT,
                    **{"from": lo.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": hi.strftime("%Y-%m-%dT%H:%M:%SZ")})
    names = {}
    for f in items_of(fx):
        try:
            names[f.get("fixtureId")] = (to_canonical(f.get("participant1Name") or ""),
                                         to_canonical(f.get("participant2Name") or ""))
        except UnknownTeam:
            continue
    if not names:
        return []
    s, live = call_fn("odds-by-tournaments", bookmaker="pinnacle", tournamentIds=NFL_TOURNAMENT)
    rows = []
    for f in items_of(live):
        teams = names.get(f.get("fixtureId"))
        if not teams:
            continue
        home, away = teams                                   # participant1 = home (verified 2026-10-18)
        g = next((g for g in due_games if g["home_team"] == home and g["away_team"] == away), None)
        if g is None:
            continue
        start = parse_ts(f.get("startTime"))
        if start is not None and abs((start - g["kickoff_utc"]).total_seconds()) > 36 * 3600:
            continue
        m = main_spread_live(f, "pinnacle", smap)
        if not m:
            continue
        rows.append({"capture_id": capture_id, "captured_at": now.isoformat(), "game_id": g["game_id"],
                     "season": g["season"], "week": g["week"], "home_team": home, "away_team": away,
                     "kickoff_utc": g["kickoff_utc"].isoformat(), "lock_utc": g["lock_utc"].isoformat(),
                     "minutes_to_lock": round((g["lock_utc"] - now).total_seconds() / 60, 1),
                     "book": "pinnacle", "home_spread": m["home_spread"],
                     "home_price_decimal": m["home_price_decimal"], "book_last_update": m["changed_at"],
                     "market_last_update": m["changed_at"], "provider_event_id": f.get("fixtureId"),
                     "status": "ok", "reason": "oddspapi"})
    return rows
