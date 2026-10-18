"""Current market spread capture (for drift = market_at_lock - CBS_open).

Source: Parlay API, an odds-api-compatible feed this user already holds a key
for (kmodel repo secret PARLAY_API_KEY). Verified 2026-09-24 by live call
(docs/evidence/probe/20260924T194249Z/parlay_nfl_spreads.json): sport key
americanfootball_nfl, market "spreads", 14 books incl. pinnacle, each with a
per-book `last_update`. Terms of use: UNVERIFIED (see data_audit.md 0.5).

Rows are appended to data/lines/market_captures.csv, one row per game x book.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import statistics
import sys

import polars as pl
import requests

from engine import config
from engine.data import store
from engine.teams import UnknownTeam, to_canonical

FIELDS = [
    "capture_id", "captured_at", "game_id", "season", "week", "home_team", "away_team",
    "kickoff_utc", "lock_utc", "minutes_to_lock", "book", "home_spread", "home_price_decimal",
    "book_last_update", "market_last_update", "provider_event_id", "status", "reason",
]


class MissingKey(RuntimeError):
    pass


USAGE_FIELDS = ["at", "endpoint", "remaining", "used", "last_cost"]
CAPTURE_FLOOR = 150          # below this many credits, optional captures stop; lock runs always run


def usage_path():
    return config.path("lines") / "api_usage.csv"


def _record_usage(r, endpoint: str) -> None:
    """Append the provider's credit counters from the response headers (never raises)."""
    try:
        h = r.headers
        row = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "endpoint": endpoint,
               "remaining": h.get("x-requests-remaining", ""), "used": h.get("x-requests-used", ""),
               "last_cost": h.get("x-requests-last", "")}
        if row["remaining"] != "":
            print(f"{endpoint}: provider reports {row['remaining']} credits remaining", file=sys.stderr)
            store.append_rows(usage_path(), USAGE_FIELDS, [row])
    except Exception as e:                                    # usage logging must never break a capture
        print(f"usage logging failed: {e!r}", file=sys.stderr)


def credits_left() -> int | None:
    """Last recorded credits remaining, or None if never recorded."""
    try:
        rows = [r for r in store.read_rows(usage_path()) if r.get("remaining") not in ("", None)]
        return int(float(rows[-1]["remaining"])) if rows else None
    except Exception:
        return None


def fetch_spreads() -> list[dict]:
    c = config.data()["market"]
    key = os.environ.get(c["api_key_env"])
    if not key:
        raise MissingKey(f"env {c['api_key_env']} not set")
    url = f"{c['base_url']}/sports/{c['sport_key']}/odds"
    r = requests.get(url, params={"apiKey": key, "markets": "spreads", "regions": c["regions"]},
                     timeout=c["timeout_seconds"], headers={"User-Agent": "nfl-ats-engine/0.1"})
    r.raise_for_status()
    _record_usage(r, "spreads")
    return r.json()


def fetch_totals() -> list[dict]:
    """Market totals (separate request so a totals failure can never break spreads).
    Verified 2026-09-25 by probe: see docs/total_report.md."""
    c = config.data()["market"]
    key = os.environ.get(c["api_key_env"])
    if not key:
        raise MissingKey(f"env {c['api_key_env']} not set")
    url = f"{c['base_url']}/sports/{c['sport_key']}/odds"
    r = requests.get(url, params={"apiKey": key, "markets": "totals", "regions": c["regions"]},
                     timeout=c["timeout_seconds"], headers={"User-Agent": "nfl-ats-engine/0.1"})
    r.raise_for_status()
    _record_usage(r, "totals")
    return r.json()


def fetch_historical(when: str) -> tuple[str, list[dict]]:
    """Market snapshot as of `when` (ISO UTC) from the historical endpoint. The user's plan serves the last 48 h
    only (probe 2026-09-26, docs/evidence/probe/20260926T223855Z). Returns (snapshot timestamp, events)."""
    c = config.data()["market"]
    key = os.environ.get(c["api_key_env"])
    if not key:
        raise MissingKey(f"env {c['api_key_env']} not set")
    url = f"{c['base_url']}/historical/sports/{c['sport_key']}/odds"
    r = requests.get(url, params={"apiKey": key, "markets": "spreads", "regions": c["regions"], "date": when},
                     timeout=c["timeout_seconds"], headers={"User-Agent": "nfl-ats-engine/0.1"})
    r.raise_for_status()
    _record_usage(r, "historical")
    return unwrap_historical(r.json(), when)


def unwrap_historical(j, when: str) -> tuple[str, list[dict]]:
    """(snapshot timestamp, events) from a historical response. Parlay returns a bare list of events (observed
    2026-09-29, the first successful call); an odds-api style {'timestamp', 'data'} object is also accepted."""
    if isinstance(j, list):
        return when, j
    if isinstance(j, dict) and isinstance(j.get("data"), list):
        return j.get("timestamp") or when, j["data"]
    raise ValueError(f"unexpected historical response shape: {type(j).__name__}")


def only_before(events: list[dict], ts: dt.datetime, slack_s: int = 120) -> tuple[list[dict], int, int]:
    """Keep only bookmakers whose last_update is at or before the snapshot time (plus `slack_s`). A 'historical'
    response carrying later updates is not the requested moment, so those books are dropped, never archived.
    Returns (events, books kept, books dropped)."""
    kept = dropped = 0
    out = []
    for e in events:
        books = []
        for b in e.get("bookmakers", []):
            lu = b.get("last_update")
            try:
                ok = lu is not None and dt.datetime.fromisoformat(lu.replace("Z", "+00:00")) <= ts + dt.timedelta(seconds=slack_s)
            except ValueError:
                ok = False
            if ok:
                books.append(b); kept += 1
            else:
                dropped += 1
        out.append({**e, "bookmakers": books})
    return out, kept, dropped


def capture_historical(sched: pl.DataFrame, when: str, events: list[dict] | None = None,
                       snapshot_ts: str | None = None) -> list[dict]:
    """Archive a historical snapshot exactly like a live all-games capture, with captured_at = the snapshot
    time (the moment the prices describe). capture_id is prefixed 'hist-' and reason records the retrieval."""
    retrieved = dt.datetime.now(dt.timezone.utc)
    if events is None:
        snapshot_ts, events = fetch_historical(when)
    ts = dt.datetime.fromisoformat((snapshot_ts or when).replace("Z", "+00:00"))
    events, kept, dropped = only_before(events, ts)
    if kept == 0 and dropped:
        raise ValueError(f"not a snapshot of {ts.isoformat()}: all {dropped} book updates are later")
    note = f"; {dropped} book(s) dropped for updates after the snapshot" if dropped else ""
    return capture(sched, now=ts, events=events, all_games=True, capture_prefix="hist-",
                   reason=f"historical snapshot, retrieved {retrieved.isoformat(timespec='seconds')}{note}")


def parse_totals(events: list[dict]) -> dict[tuple[str, str], dict]:
    """(home, away) -> {"median": total, "n_books": n}. Uses the Over outcome's point per book."""
    out = {}
    for e in events:
        try:
            home, away = to_canonical(e["home_team"]), to_canonical(e["away_team"])
        except (UnknownTeam, KeyError):
            continue
        pts = []
        for b in e.get("bookmakers", []):
            for m in b.get("markets", []):
                if m.get("key") != "totals":
                    continue
                over = [o for o in m.get("outcomes", []) if str(o.get("name", "")).lower() == "over"
                        and o.get("point") is not None]
                if over:
                    over.sort(key=lambda o: abs(float(o.get("price") or 0) - 1.91))
                    pts.append(float(over[0]["point"]))
        if pts:
            out[(home, away)] = {"median": statistics.median(pts), "n_books": len(pts)}
    return out


def parse_events(events: list[dict]) -> list[dict]:
    """One row per event x book with the HOME spread (canonical sign: negative = home favored;
    odds-api 'point' is already from the named team's perspective)."""
    out = []
    for e in events:
        try:
            home, away = to_canonical(e["home_team"]), to_canonical(e["away_team"])
        except (UnknownTeam, KeyError) as ex:
            out.append({"status": "unmatched", "reason": f"team: {ex}", "provider_event_id": e.get("id")})
            continue
        for b in e.get("bookmakers", []):
            for m in b.get("markets", []):
                if m.get("key") != "spreads":
                    continue
                hp = [o for o in m.get("outcomes", [])
                      if o.get("name") == e["home_team"] and o.get("point") is not None]
                if not hp:
                    continue
                # Some books also list alternate spreads (observed 2026-09-24: betrivers,
                # draftkings, fanduel had a second BUF line). Keep the main line: the
                # home price closest to even money.
                hp.sort(key=lambda o: abs(float(o.get("price") or 0) - 1.91))
                out.append({"provider_event_id": e.get("id"), "commence_time": e.get("commence_time"),
                            "home_team": home, "away_team": away, "book": b.get("key"),
                            "home_spread": float(hp[0]["point"]), "home_price_decimal": hp[0].get("price"),
                            "book_last_update": b.get("last_update"),
                            "market_last_update": m.get("last_update"), "status": "ok", "reason": ""})
    return out


def consensus(rows: list[dict], reference_book: str | None = None) -> dict:
    pts = [r["home_spread"] for r in rows if r.get("status") == "ok"]
    ref = [r["home_spread"] for r in rows if r.get("book") == reference_book]
    return {"median": statistics.median(pts) if pts else None, "n_books": len(pts),
            "reference": ref[0] if ref else None}


def redact(text: str) -> str:
    """Remove API keys from error text before it is written to a committed file."""
    return re.sub(r"(?i)(api_?key=)[^&\s'\"]+", r"\1REDACTED", text)


def latest_ok_rows(game_ids, now: dt.datetime, max_age_hours: float, captures: list[dict] | None = None) -> dict:
    """Per game: the 'ok' rows of the newest capture taken at or before `now` and at most `max_age_hours` old.
    Used only when the pick-time capture failed for that game."""
    if captures is None:
        captures = store.read_rows(config.path("lines") / "market_captures.csv")
    want, oldest, best = set(game_ids), now - dt.timedelta(hours=max_age_hours), {}
    for r in captures:
        g = r.get("game_id")
        if g not in want or r.get("status") != "ok" or r.get("home_spread") in (None, ""):
            continue
        at = dt.datetime.fromisoformat(r["captured_at"])
        if not (oldest <= at <= now):
            continue
        if g not in best or at > best[g][0]:
            best[g] = (at, [r])
        elif at == best[g][0]:
            best[g][1].append(r)
    return {g: [{**r, "home_spread": float(r["home_spread"])} for r in rows] for g, (at, rows) in best.items()}


def capture(sched: pl.DataFrame, now: dt.datetime | None = None, window_minutes: int | None = None,
            events: list[dict] | None = None, all_games: bool = False, capture_prefix: str = "",
            reason: str = "") -> list[dict]:
    """Capture market spreads for games whose lock is within `window_minutes` from now
    (or every upcoming game if all_games). Late captures are recorded with their true
    minutes_to_lock (negative = after lock) so timing error is measured, not hidden."""
    now = now or dt.datetime.now(dt.timezone.utc)
    c = config.data()["market"]
    window = window_minutes if window_minutes is not None else c["lock_window_minutes"]
    capture_id = capture_prefix + now.strftime("%Y%m%dT%H%M%SZ")
    try:
        events = events if events is not None else fetch_spreads()
    except Exception as e:
        row = {"capture_id": capture_id, "captured_at": now.isoformat(), "status": "fetch_error",
               "reason": redact(repr(e))[:300]}
        store.append_rows(config.path("lines") / "market_captures.csv", FIELDS, [row])
        return [row]
    parsed = parse_events(events)
    rows = []
    for p in parsed:
        if p["status"] != "ok":
            rows.append({**p, "capture_id": capture_id, "captured_at": now.isoformat()})
            continue
        cand = sched.filter((pl.col("home_team") == p["home_team"]) & (pl.col("away_team") == p["away_team"])
                            & (pl.col("kickoff_utc") > now - dt.timedelta(hours=6)))
        if p.get("commence_time"):
            ct = dt.datetime.fromisoformat(p["commence_time"].replace("Z", "+00:00"))
            cand = cand.filter((pl.col("kickoff_utc") - pl.lit(ct)).dt.total_hours().abs() <= 36)
        if cand.height != 1:
            continue  # not a scheduled regular-season game in range (e.g. future week)
        g = cand.row(0, named=True)
        mtl = (g["lock_utc"] - now).total_seconds() / 60
        if not all_games and not (-60 <= mtl <= window):
            continue
        p.pop("commence_time", None)
        if reason:
            p["reason"] = reason
        rows.append({**p, "capture_id": capture_id, "captured_at": now.isoformat(),
                     "game_id": g["game_id"], "season": g["season"], "week": g["week"],
                     "kickoff_utc": g["kickoff_utc"].isoformat(), "lock_utc": g["lock_utc"].isoformat(),
                     "minutes_to_lock": round(mtl, 1)})
    store.append_rows(config.path("lines") / "market_captures.csv", FIELDS, rows)
    return rows


def market_at_lock(captures: list[dict], game_id: str, as_of: dt.datetime,
                   reference_book: str | None = None) -> dict:
    """Consensus market spread for one game using ONLY captures taken at or before
    `as_of` (no look-ahead). Uses the latest such capture_id."""
    usable = [r for r in captures if r.get("game_id") == game_id and r.get("status") == "ok"
              and dt.datetime.fromisoformat(r["captured_at"]) <= as_of]
    if not usable:
        return {"median": None, "n_books": 0, "reference": None, "captured_at": None}
    latest = max(r["captured_at"] for r in usable)
    rows = [{**r, "home_spread": float(r["home_spread"])} for r in usable if r["captured_at"] == latest]
    return {**consensus(rows, reference_book), "captured_at": latest}
