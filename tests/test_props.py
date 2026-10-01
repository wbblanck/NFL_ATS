"""Known-answer checks for engine.backtest.props."""
import numpy as np
import polars as pl

from engine.backtest import props as P


def _stats():
    rows = [("p1", "D.J. Moore", "WR", 1, "CHI", "g1"), ("p2", "Marvin Harrison Jr.", "WR", 1, "ARI", "g2"),
            ("p3", "Josh Allen", "QB", 1, "BUF", "g3"), ("p4", "Mike Williams", "WR", 1, "NYJ", "g4"),
            ("p5", "Garrett Wilson", "WR", 1, "NYJ", "g4"), ("p6", "Tyler Johnson", "WR", 1, "LA", "g5")]
    d = pl.DataFrame(rows, schema=["player_id", "player_display_name", "position", "week", "team", "game_id"],
                     orient="row")
    zero = {m: 0 for m in P.STAT}
    vals = [dict(zero, rec_yds=70, rec=5, anytime_td=1), dict(zero, rec_yds=40, rec=3), dict(zero, pass_yds=250),
            dict(zero, rec_yds=10), dict(zero, rec_yds=90), dict(zero, rec_yds=0)]
    return d.with_columns(*[pl.Series(m, [v[m] for v in vals]) for m in P.STAT])


def _lines(rows):
    return pl.DataFrame(rows, schema=["week", "team", "player", "market", "line", "over_odds", "under_odds",
                                      "yes_odds", "book"], orient="row")


def test_join_and_grade():
    lines = _lines([
        (1, "CHI", "DJ Moore", "rec_yds", 65.5, -115.0, -105.0, None, "DK NJ"),        # initials -> full match
        (1, "ARI", "Marvin Harrison", "rec_yds", 40.0, -110.0, -110.0, None, "DK NJ"),  # suffix dropped, push
        (1, "BUF", "J. Allen", "pass_yds", 240.5, -110.0, -110.0, None, "DK NJ"),       # unique last name
        (1, "NYJ", "M. Wilson", "rec_yds", 50.5, -110.0, -110.0, None, "DK NJ"),        # initial disagrees: none
        (1, "NYJ", "G. Wilson", "rec_yds", 50.5, -110.0, -110.0, None, "DK NJ"),        # last name + initial
        (1, "LA", "Tyler Johnson", "rec_yds", 20.5, -110.0, -110.0, None, "DK NJ"),     # LA team code
        (1, "CHI", "Nobody Here", "rec_yds", 20.5, -110.0, -110.0, None, "DK NJ"),
        (1, "CHI", "DJ Moore", "anytime_td", 0.0, None, None, 150.0, "DK NJ"),
    ])
    j = P.join(lines, _stats())
    assert j["match"].to_list() == ["full", "full", "last", "none", "last", "full", "none", "full"]
    assert j["actual"].to_list() == [70, 40, 250, None, 90, 0, None, 1]
    g = P.graded(j)
    assert g["result"].to_list() == ["over", "push", "over", "over", "under"]
    assert abs(g["p_over"][1] - 0.5) < 1e-12 and abs(g["hold"][1] - (2 / 1.9090909 - 1)) < 1e-6


def test_profit():
    out = P.profit(np.array([-110.0, 150.0, -120.0]), np.array([1.0, 0.0, np.nan]))
    assert np.allclose(out, [100 / 110, -1.0, 0.0])
