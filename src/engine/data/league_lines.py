"""The league's actual grading lines, recorded by hand from the pool screen
(CBS Office Pool "BONSAI POOL 2026"). This is the source of truth for grading;
captured CBS/market lines are only used to work out how the league sets it.

Every line must be a half-point (league rule); anything else is rejected.
"""
from __future__ import annotations

from engine import config
from engine.data import store
from engine.picks.grading import favorite, validate_league_line
from engine.teams import to_canonical

FIELDS = ["game_id", "season", "week", "home_team", "away_team", "spread", "favorite",
          "source", "recorded_at"]


def load() -> list[dict]:
    rows = store.read_rows(config.path("lines") / "league_lines.csv")
    for r in rows:
        s = validate_league_line(float(r["spread"]))
        home, away = to_canonical(r["home_team"]), to_canonical(r["away_team"])
        fav = favorite(s)
        expected = {"home": home, "away": away}[fav.value]
        if r["favorite"] != expected:
            raise ValueError(f"{r['game_id']}: favorite {r['favorite']} inconsistent with spread {s}")
    return rows


def check_against_schedule(rows: list[dict], sched) -> list[str]:
    """Problems with recorded lines: unknown game_id, home/away mismatch, duplicates."""
    import polars as pl
    probs, seen = [], set()
    ids = {r["game_id"]: r for r in sched.select("game_id", "home_team", "away_team").to_dicts()}
    for r in rows:
        g = ids.get(r["game_id"])
        if g is None:
            probs.append(f"{r['game_id']}: not a regular-season game in the schedule")
        elif (g["home_team"], g["away_team"]) != (r["home_team"], r["away_team"]):
            probs.append(f"{r['game_id']}: home/away {r['home_team']}/{r['away_team']} != schedule")
        if r["game_id"] in seen:
            probs.append(f"{r['game_id']}: duplicate row")
        seen.add(r["game_id"])
    return probs


def missing_games(rows: list[dict], sched, season: int, week: int) -> list[str]:
    import polars as pl
    have = {r["game_id"] for r in rows}
    wk = sched.filter((pl.col("season") == season) & (pl.col("week") == week))["game_id"].to_list()
    return [g for g in wk if g not in have]
