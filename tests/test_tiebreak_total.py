import datetime as dt

import polars as pl

from engine.picks import tiebreak_total as tt


def _sched():
    k = lambda d, h: dt.datetime(2026, 9, d, h, tzinfo=dt.timezone.utc)
    return pl.DataFrame({
        "season": [2026] * 4, "game_type": ["REG"] * 4, "week": [1, 1, 2, 2],
        "game_id": ["a", "b", "c", "d"], "away_team": ["DEN", "BUF", "NYG", "DAL"],
        "home_team": ["KC", "MIA", "LA", "PHI"],
        "kickoff_utc": [k(15, 0), k(14, 17), k(22, 0), k(21, 17)],
        "total_line": [42.5, 44.0, 47.0, None], "spread_line": [3.5, 1.0, -2.0, None],
        "home_score": [24, 20, None, None], "away_score": [17, 10, None, None]})


def test_last_game_guess_and_result():
    t = tt.build(_sched(), 2026)
    assert [(r["week"], r["game_id"]) for r in t] == [(1, "a"), (2, "c")]
    w1 = t[0]
    assert w1["guess"] == 42 and w1["actual"] == 41 and w1["miss"] == 1
    assert w1["home_pts"] == 23.0 and w1["away_pts"] == 19.5
    assert w1["r80"] == [27, 60]
    assert t[1]["guess"] == 47 and "actual" not in t[1]


def test_rounding():
    assert tt.guess(42.5) == 42 and tt.guess(47.0) == 47 and tt.guess(44.75) == 45
