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
