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
    d = pl.DataFrame(rows, schema=["week", "team", "player", "market", "line", "over_odds", "under_odds",
                                   "yes_odds", "book"], orient="row")
    return d.with_columns(pl.col("team").alias("home"), pl.lit("XXX").alias("away"))


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


def test_blank_team_searches_both_teams_in_the_game():
    lines = pl.DataFrame([(1, None, "CHI", "GB", "DJ Moore", "rec_yds", 65.5, -115.0, -105.0, None, "DK NJ"),
                          (1, None, "NYJ", "BUF", "Josh Allen", "pass_yds", 240.5, -110.0, -110.0, None, "DK NJ")],
                         schema=["week", "team", "home", "away", "player", "market", "line", "over_odds",
                                 "under_odds", "yes_odds", "book"], orient="row")
    j = P.join(lines, _stats())
    assert j["match"].to_list() == ["full", "full"] and j["actual"].to_list() == [70, 250]


def test_played_without_stats_is_graded_zero():
    lines = pl.DataFrame([(1, "CHI", "CHI", "GB", "Velus Jones", "rec_yds", 5.5, -110.0, -110.0, None, "DK NJ"),
                          (1, "CHI", "CHI", "GB", "Not Active", "rec_yds", 5.5, -110.0, -110.0, None, "DK NJ")],
                         schema=["week", "team", "home", "away", "player", "market", "line", "over_odds",
                                 "under_odds", "yes_odds", "book"], orient="row")
    snaps = pl.DataFrame({"player": ["Velus Jones Jr."], "team": ["CHI"], "week": [1]})
    j = P.join(lines, _stats(), snaps)
    assert j["match"].to_list() == ["snaps_zero", "none"] and j["actual"].to_list() == [0, None]
    assert P.graded(j)["result"].to_list() == ["under"]


def _synthetic_props(seed, p_under_disagree, weeks=12):
    """Per week: 40 DK-only quotes (under wins 50%) and 10 player-games where DK and BetRivers post lines one
    yard apart (under wins p_under_disagree). All at -110."""
    from engine.backtest import props_confirm as C  # noqa: F401
    rng = np.random.default_rng(seed)
    rows = []
    for wk in range(1, weeks + 1):
        for i in range(40):
            rows.append(("solo%d_%d" % (wk, i), wk, "DK NJ", 50.5, "under" if rng.random() < 0.5 else "over"))
        for i in range(10):
            res = "under" if rng.random() < p_under_disagree else "over"
            rows.append(("dis%d_%d" % (wk, i), wk, "DK NJ", 50.5, res))
            rows.append(("dis%d_%d" % (wk, i), wk, "BetRivers NJ", 51.5, res))
    d = pl.DataFrame(rows, schema=["player_id", "week", "book", "line", "result"], orient="row")
    return d.with_columns(pl.lit(2025).alias("season"), pl.lit("rec_yds").alias("market"), pl.lit(0.5).alias("p_over"),
                          pl.lit(0.0476).alias("hold"), pl.lit(-110.0).alias("under_odds"))


def test_confirm_signal_found_noise_not():
    from engine.backtest import props_confirm as C
    g = _synthetic_props(1, 0.70)
    bets, base = C.disagreement_bets(g), C.baseline(g)
    r = C.evaluate(bets["H1_under_at_highest_line"], base)
    assert r["n"] == 120 and r["pass"] and r["books_at_bet"] == {"BetRivers NJ": 120}
    g = _synthetic_props(2, 0.50)
    bets, base = C.disagreement_bets(g), C.baseline(g)
    for k in bets:
        assert not C.evaluate(bets[k], base)["pass"]
