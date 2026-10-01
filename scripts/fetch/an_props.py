"""Fetch Action Network's NFL player-prop lines for one regular season.

Keyless public API (verified in docs/props_data_audit.md): `web/v2/scoreboard/nfl?season=S&week=W` lists the
week's games; `web/v2/games/{id}/props` holds every player prop. Prop history starts in 2024.

One row per (game, player, market, book, line):
  season, week, an_game_id, start_time, home, away, market, an_player_id, player, player_team,
  book_id, book, line, over_odds, under_odds, yes_odds
Over/under markets fill over_odds/under_odds; anytime-TD (a one-sided "moneyline" market) fills yes_odds.
Alternate lines (`is_alt_market`) and partial-game lines (`period` other than "event") are skipped. Book 15 ("Consensus") and 30 ("Open") are kept and labelled;
they are not books, and analysis must drop them. Line records carry NO timestamp.

Held-out guard (docs/props_preregistration.md): any season but 2024 is refused unless
docs/props_confirm_preregistration.md exists.

Usage: python scripts/fetch/an_props.py --season 2024 [--weeks 1-18] [--out data/props/an_props_2024.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

AN = "https://api.actionnetwork.com"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
EXPLORATION = 2024
CONFIRM_PREREG = Path("docs/props_confirm_preregistration.md")
MARKETS = {
    "core_bet_type_9_passing_yards": "pass_yds", "core_bet_type_30_passing_attempts": "pass_att",
    "core_bet_type_10_pass_completions": "pass_cmp", "core_bet_type_11_passing_tds": "pass_td",
    "core_bet_type_65_interceptions": "pass_int", "core_bet_type_12_rushing_yards": "rush_yds",
    "core_bet_type_18_rushing_attempts": "rush_att", "core_bet_type_15_receptions": "rec",
    "core_bet_type_16_receiving_yards": "rec_yds", "core_bet_type_66_rushing_receiving_yards": "rush_rec_yds",
    "core_bet_type_71_passing_rushing_yards": "pass_rush_yds",
    "core_bet_type_62_anytime_touchdown_scorer": "anytime_td",
}
FIELDS = ["season", "week", "an_game_id", "start_time", "home", "away", "market", "an_player_id", "player",
          "player_team", "book_id", "book", "line", "over_odds", "under_odds", "yes_odds"]


def get(url: str, pause: float, tries: int = 4):
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Referer": "https://www.actionnetwork.com/", "Origin": "https://www.actionnetwork.com"}
    last = None
    for i in range(tries):
        time.sleep(pause if i == 0 else pause + 2 ** i)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 404:
                break
        except Exception as e:  # noqa: BLE001 - retried, then reported
            last = str(e)
    print(f"  [fail] {url}: {last}", file=sys.stderr)
    return None


def team_abbrs(game: dict) -> dict:
    return {t.get("id"): t.get("abbr") for t in (game.get("teams") or []) if isinstance(t, dict)}


def players_of(props: dict) -> dict:
    """AN player id -> (full name, team id). The `players` field is a list or a dict, depending on endpoint."""
    pl = props.get("players")
    items = pl.values() if isinstance(pl, dict) else (pl or [])
    return {p["id"]: (p.get("full_name") or p.get("display_name") or "", p.get("team_id"))
            for p in items if isinstance(p, dict) and p.get("id") is not None}


def rows_for_game(props: dict, game: dict, season: int, week: int, books: dict) -> list[dict]:
    teams = team_abbrs(game)
    who = players_of(props)
    out = []
    for key, market in MARKETS.items():
        entries = (props.get("player_props") or {}).get(key) or []
        grouped: dict = defaultdict(dict)
        for e in entries:
            for book, lines in (e.get("lines") or {}).items():
                for ln in lines:
                    if ln.get("is_alt_market"):
                        continue
                    # full-game props only: from 2025 week 13 Action Network also files first-half/quarter
                    # props (period != "event") under the same market type (found 2026-10-01)
                    if ln.get("period", "event") != "event":
                        continue
                    side = ln.get("side")
                    slot = {"over": "over_odds", "under": "under_odds", "noside": "yes_odds"}.get(side)
                    if slot is None:
                        continue
                    grouped[(ln.get("player_id"), str(book), ln.get("value"))][slot] = ln.get("odds")
        for (pid, book, line), odds in grouped.items():
            name, team_id = who.get(pid, ("", None))
            out.append({"season": season, "week": week, "an_game_id": game["id"],
                        "start_time": game.get("start_time"), "home": teams.get(game.get("home_team_id")),
                        "away": teams.get(game.get("away_team_id")), "market": market, "an_player_id": pid,
                        "player": name, "player_team": teams.get(team_id, ""), "book_id": book,
                        "book": books.get(book, ""), "line": line,
                        "over_odds": odds.get("over_odds", ""), "under_odds": odds.get("under_odds", ""),
                        "yes_odds": odds.get("yes_odds", "")})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--weeks", default="1-18")
    ap.add_argument("--out")
    ap.add_argument("--pause", type=float, default=1.0)
    a = ap.parse_args()
    if a.season != EXPLORATION and not CONFIRM_PREREG.exists():
        sys.exit(f"refused: {a.season} is held out until {CONFIRM_PREREG} is committed (docs/props_preregistration.md)")
    lo, hi = (int(x) for x in a.weeks.split("-"))
    out = Path(a.out or f"data/props/an_props_{a.season}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    bd = get(AN + "/web/v1/books", a.pause)
    books = {str(b.get("id")): b.get("display_name") or b.get("name") or "" for b in ((bd or {}).get("books") or [])}
    stats = Counter()
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for week in range(lo, hi + 1):
            sb = get(f"{AN}/web/v2/scoreboard/nfl?season={a.season}&week={week}&periods=event", a.pause)
            games = (sb or {}).get("games") or []
            if not games:
                stats["weeks_without_scoreboard"] += 1
            week_rows = 0
            for g in games:
                if str(g.get("start_time", ""))[:4] not in (str(a.season), str(a.season + 1)):
                    stats["games_outside_season"] += 1
                    continue
                props = get(f"{AN}/web/v2/games/{g['id']}/props", a.pause)
                if props is None:
                    stats["props_failed"] += 1
                    continue
                rows = rows_for_game(props, g, a.season, week, books)
                stats["games"] += 1
                stats["games_with_props"] += bool(rows)
                stats["rows_without_name"] += sum(1 for r in rows if not r["player"])
                for r in rows:
                    stats[f"market_{r['market']}"] += 1
                    w.writerow(r)
                week_rows += len(rows)
            stats["rows"] += week_rows
            print(f"week {week:2d}: games {len(games):2d}, rows {week_rows}", flush=True)
    print("SUMMARY", a.season, json.dumps(dict(sorted(stats.items())), indent=1))


if __name__ == "__main__":
    main()
