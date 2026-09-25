"""Live capture of CBS Sports opening spreads.

Source (verified by live fetch 2026-09-24, evidence in
docs/evidence/probe/20260924T194249Z/cbs_nfl_odds.html):
  https://www.cbssports.com/nfl/odds/  renders one <table class="OddsBlock-game">
  per game with attributes data-game-abbrev="NFL_YYYYMMDD_AWAY@HOME" and
  data-game-id, and a column th.OddsBlock-betOdds--openingLines ("Open").
  In each game one team row's Open cell holds that team's spread + price
  (e.g. "-6.5 -112"); the other row holds the opening total ("o46.5 -108").

IMPORTANT (see docs/data_audit.md 0.3): the CBS odds-page "Open" column is
NOT guaranteed to be the league's grading line. On 2026-09-24, 3 of 16
week-3 openers on that page were whole numbers, which cannot be league
lines. Such rows are rejected and flagged for manual review, never graded.

Every capture is appended (never overwritten) to data/lines/cbs_open_captures.csv.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import re
from dataclasses import dataclass, field

import polars as pl
import requests
from bs4 import BeautifulSoup

from engine import config
from engine.data import store
from engine.picks.grading import InvalidLeagueLine, favorite, validate_league_line
from engine.teams import UnknownTeam, to_canonical

CAPTURE_FIELDS = [
    "capture_id", "captured_at", "source_url", "page_sha256",
    "cbs_game_id", "cbs_abbrev", "cbs_date",
    "game_id", "season", "week", "home_team", "away_team",
    "spread", "favorite", "open_price", "open_total",
    "raw_open_home", "raw_open_away",
    "current_home_spread", "current_operator",
    "status", "reason",
]
FROZEN_FIELDS = [
    "game_id", "season", "week", "home_team", "away_team", "spread", "favorite",
    "captured_at", "source_url", "capture_id", "frozen_at", "later_changes",
]

_SPREAD_RE = re.compile(r"^(?P<val>[+-]?\d+(?:\.\d+)?|PK|pk|EVEN|Even)\s*(?P<price>[+-]\d+)?$")
_TOTAL_RE = re.compile(r"^[ouOU]\s?\d+(?:\.\d+)?")


@dataclass
class ParsedGame:
    cbs_game_id: str
    cbs_abbrev: str
    cbs_date: str | None
    away_code: str
    home_code: str
    open_away: str | None
    open_home: str | None
    current_home_spread: float | None = None
    current_operator: str | None = None
    notes: list[str] = field(default_factory=list)


def _parse_spread_text(txt: str | None) -> tuple[float, int | None] | None:
    if not txt:
        return None
    t = txt.strip()
    if _TOTAL_RE.match(t):
        return None
    m = _SPREAD_RE.match(t)
    if not m:
        return None
    v = m.group("val")
    val = 0.0 if v.lower() in ("pk", "even") else float(v)
    price = int(m.group("price")) if m.group("price") else None
    return val, price


def parse_odds_page(html: str) -> list[ParsedGame]:
    soup = BeautifulSoup(html, "lxml")
    games = []
    for t in soup.select("table.OddsBlock-game"):
        abbrev = t.get("data-game-abbrev") or ""
        m = re.match(r"NFL_(\d{8})_([A-Z]+)@([A-Z]+)$", abbrev)
        if not m:
            continue
        date, away, home = m.groups()
        team_rows = [r for r in t.select("tbody tr") if r.select_one(".OddsBlock-teamText--short")]
        if len(team_rows) != 2:
            games.append(ParsedGame(t.get("data-game-id", ""), abbrev, date, away, home, None, None,
                                    notes=[f"expected 2 team rows, found {len(team_rows)}"]))
            continue
        opens, cur_home, operator = [], None, None
        for i, r in enumerate(team_rows):
            cell = r.select_one(".OddsBlock-betOdds--openingLines")
            opens.append(cell.get_text(" ", strip=True) if cell else None)
            btn = r.select_one(".OddsBlock-betOdds--spread button[data-config]")
            if btn is not None and i == 1:
                try:
                    cfg = json.loads(btn["data-config"])
                    cur_home = float(cfg["line"])
                    operator = f'{cfg.get("operatorName")}/{cfg.get("vendor")}'
                except Exception:
                    pass
        games.append(ParsedGame(t.get("data-game-id", ""), abbrev, date, away, home,
                                open_away=opens[0], open_home=opens[1],
                                current_home_spread=cur_home, current_operator=operator))
    return games


def opening_home_spread(g: ParsedGame) -> tuple[float | None, int | None, str | None]:
    """Return (canonical home spread S, price, total_text) from the Open column."""
    home = _parse_spread_text(g.open_home)
    away = _parse_spread_text(g.open_away)
    total = next((x for x in (g.open_home, g.open_away) if x and _TOTAL_RE.match(x.strip())), None)
    if home is not None and away is not None:
        if abs(home[0] + away[0]) > 1e-9:
            return None, None, total  # inconsistent; caller flags
        return home[0], home[1], total
    if home is not None:
        return home[0], home[1], total
    if away is not None:
        return -away[0], away[1], total
    return None, None, total


def match_games(parsed: list[ParsedGame], sched: pl.DataFrame) -> list[dict]:
    """Attach nflverse game_id; unmatched rows are kept with status=unmatched."""
    rows = []
    for g in parsed:
        base = {"cbs_game_id": g.cbs_game_id, "cbs_abbrev": g.cbs_abbrev, "cbs_date": g.cbs_date,
                "raw_open_home": g.open_home, "raw_open_away": g.open_away,
                "current_home_spread": g.current_home_spread, "current_operator": g.current_operator}
        try:
            home, away = to_canonical(g.home_code), to_canonical(g.away_code)
        except UnknownTeam as e:
            rows.append({**base, "status": "unmatched", "reason": f"unknown team {e}"})
            continue
        d = dt.datetime.strptime(g.cbs_date, "%Y%m%d").date()
        cand = sched.filter((pl.col("home_team") == home) & (pl.col("away_team") == away))
        cand = cand.filter(
            (pl.col("gameday").str.to_date() - pl.lit(d)).dt.total_days().abs() <= 1)
        base.update(home_team=home, away_team=away)
        if cand.height != 1:
            rows.append({**base, "status": "unmatched",
                         "reason": f"{cand.height} schedule matches for {away}@{home} {d}"})
            continue
        r = cand.row(0, named=True)
        base.update(game_id=r["game_id"], season=r["season"], week=r["week"])
        if g.notes:
            rows.append({**base, "status": "parse_error", "reason": "; ".join(g.notes)})
            continue
        s, price, total = opening_home_spread(g)
        base.update(open_price=price, open_total=total)
        if s is None:
            rows.append({**base, "status": "missing_open", "reason": "no parsable opening spread"})
            continue
        base["spread"] = s
        fav = favorite(s)
        base["favorite"] = {None: "", "home": home, "away": away}[fav.value if fav else None]
        try:
            validate_league_line(s)
            rows.append({**base, "status": "ok", "reason": ""})
        except InvalidLeagueLine as e:
            rows.append({**base, "status": "rejected", "reason": f"manual review: {e}"})
    return rows


def fetch(url: str) -> str:
    c = config.data()["cbs"]
    r = requests.get(url, headers={"User-Agent": c["user_agent"]}, timeout=c["timeout_seconds"])
    r.raise_for_status()
    return r.text


def capture(sched: pl.DataFrame, now: dt.datetime | None = None, urls: list[str] | None = None,
            fetcher=fetch) -> list[dict]:
    """Fetch CBS odds pages, parse, match, append to the capture archive."""
    now = now or dt.datetime.now(dt.timezone.utc)
    c = config.data()["cbs"]
    if urls is None:
        urls = [c["odds_url"]]
        upcoming = sched.filter(pl.col("kickoff_utc") > now).sort("kickoff_utc")
        if upcoming.height:
            season, week = upcoming.row(0, named=True)["season"], upcoming.row(0, named=True)["week"]
            for w in range(week, week + 1 + int(c.get("weeks_ahead", 0))):
                if w <= int(sched.filter(pl.col("season") == season)["week"].max()):
                    urls.append(c["week_url"].format(season=season, week=w))
    lines_dir = config.path("lines")
    capture_id = now.strftime("%Y%m%dT%H%M%SZ")
    all_rows = []
    for url in urls:
        try:
            html = fetcher(url)
        except Exception as e:
            all_rows.append({"capture_id": capture_id, "captured_at": now.isoformat(),
                             "source_url": url, "status": "fetch_error", "reason": repr(e)[:300]})
            continue
        sha = hashlib.sha256(html.encode()).hexdigest()
        parsed = parse_odds_page(html)
        rows = match_games(parsed, sched)
        if not rows:
            rows = [{"status": "no_games", "reason": "page parsed to zero games"}]
        for r in rows:
            r.update(capture_id=capture_id, captured_at=now.isoformat(), source_url=url, page_sha256=sha)
        if c.get("save_raw_html"):
            _save_raw_if_changed(lines_dir, url, html, rows, capture_id)
        all_rows.extend(rows)
    store.append_rows(lines_dir / "cbs_open_captures.csv", CAPTURE_FIELDS, all_rows)
    _append_new_flags(lines_dir / "cbs_open_flags.csv", all_rows)
    return all_rows


def _flag_key(r) -> tuple:
    return (str(r.get("game_id") or r.get("cbs_abbrev") or r.get("source_url")), str(r.get("status")),
            str(r.get("raw_open_home") or ""), str(r.get("raw_open_away") or ""))


def _append_new_flags(path, rows):
    """Log each distinct non-ok condition once (fetch errors are always logged)."""
    seen = {_flag_key(r) for r in store.read_rows(path)}
    new = [r for r in rows if r.get("status") != "ok"
           and (r.get("status") == "fetch_error" or _flag_key(r) not in seen)]
    store.append_rows(path, CAPTURE_FIELDS, new)


def _save_raw_if_changed(lines_dir, url, html, rows, capture_id):
    """Keep raw HTML only when the parsed opening lines differ from the last saved copy."""
    key = hashlib.sha256(url.encode()).hexdigest()[:10]
    digest = hashlib.sha256(json.dumps(
        sorted((str(r.get("cbs_abbrev")), str(r.get("raw_open_home")), str(r.get("raw_open_away")))
               for r in rows)).encode()).hexdigest()
    idx = lines_dir / "raw_cbs" / "index.csv"
    last = [r for r in store.read_rows(idx) if r["url_key"] == key]
    if last and last[-1]["parsed_digest"] == digest:
        return
    out = lines_dir / "raw_cbs" / f"{capture_id}_{key}.html.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt") as f:
        f.write(html)
    store.append_rows(idx, ["capture_id", "url", "url_key", "parsed_digest", "file"],
                      [{"capture_id": capture_id, "url": url, "url_key": key,
                        "parsed_digest": digest, "file": out.name}])


def freeze() -> list[dict]:
    """Derive the frozen opener per game: the FIRST valid capture. Later captures
    that differ are counted in later_changes (never replace the frozen value).
    Rewrites cbs_open_frozen.csv as a derived view (source of truth = captures)."""
    lines_dir = config.path("lines")
    caps = [r for r in store.read_rows(lines_dir / "cbs_open_captures.csv") if r["status"] == "ok"]
    caps.sort(key=lambda r: r["captured_at"])
    first, changes = {}, {}
    for r in caps:
        g = r["game_id"]
        if g not in first:
            first[g] = r
            changes[g] = []
        elif r["spread"] != first[g]["spread"] and r["spread"] not in changes[g]:
            changes[g].append(r["spread"])
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    out = [{**{k: first[g][k] for k in ("game_id", "season", "week", "home_team", "away_team",
                                         "spread", "favorite", "captured_at", "source_url", "capture_id")},
            "frozen_at": now, "later_changes": "|".join(changes[g])} for g in sorted(first)]
    p = lines_dir / "cbs_open_frozen.csv"
    if p.exists():
        p.unlink()
    store.append_rows(p, FROZEN_FIELDS, out)
    return out
