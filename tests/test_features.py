import polars as pl

from engine.features.efficiency import ratings
from engine.features.qb import qb_change
from engine.features.rest import rest_features


def test_qb_change():
    s = pl.DataFrame({"game_id": ["g1", "g2", "g3"], "season": [2020] * 3, "week": [1, 2, 3],
                      "gameday": ["2020-09-10", "2020-09-17", "2020-09-24"], "game_type": ["REG"] * 3,
                      "home_team": ["A", "B", "A"], "away_team": ["B", "A", "B"],
                      "home_qb_id": ["a1", "b1", "a2"], "away_qb_id": ["b1", "a1", "b1"]})
    f = {r["game_id"]: r for r in qb_change(s).to_dicts()}
    assert f["g1"]["qb_change_home"] == 0 and f["g1"]["qb_change_away"] == 0   # no previous game
    assert f["g2"]["qb_change_away"] == 0                                         # A: a1 -> a1
    assert f["g3"]["qb_change_home"] == 1 and f["g3"]["qb_change_away"] == 0     # A: a1 -> a2


def test_rest():
    s = pl.DataFrame({"game_id": ["g"], "home_rest": [14], "away_rest": [4]})
    r = rest_features(s).row(0, named=True)
    assert r["rest_diff"] == 7 and r["home_bye"] == 1 and r["away_short"] == 1


def _games(rows):
    return pl.DataFrame(rows, schema=["season", "week", "team", "opp", "off_epa_pp", "opp_off_epa_pp"], orient="row")


def test_ratings_use_only_prior_games_and_recency():
    g = _games([(2020, 1, "A", "B", 0.3, 0.0), (2020, 1, "B", "A", 0.0, 0.3),
                (2020, 2, "A", "C", 0.3, 0.0), (2020, 2, "C", "A", 0.0, 0.3)])
    r = {(x["week"], x["team"]): x for x in ratings(g, half_life=1.0).to_dicts()}
    assert r[(1, "A")]["off_pre"] == 0.0            # nothing known before week 1
    assert abs(r[(2, "A")]["off_pre"] - 0.15) < 1e-12   # alpha=0.5 after one 0.3 game


def test_opponent_adjustment_uses_pre_game_opponent_rating():
    # B's defense is known to be bad (allows +0.4) before week 3; A's 0.4 vs B is worth 0 after adjustment
    g = _games([(2020, 1, "B", "X", 0.0, 0.4), (2020, 1, "X", "B", 0.4, 0.0),
                (2020, 2, "B", "Y", 0.0, 0.4), (2020, 2, "Y", "B", 0.4, 0.0),
                (2020, 3, "A", "B", 0.4, 0.0), (2020, 3, "B", "A", 0.0, 0.4),
                (2020, 4, "A", "Z", 0.0, 0.0), (2020, 4, "Z", "A", 0.0, 0.0)])
    rt = ratings(g, half_life=1.0)
    b_def = rt.filter((pl.col("team") == "B") & (pl.col("week") == 3))["def_pre"][0]
    a_off_after = rt.filter((pl.col("team") == "A") & (pl.col("week") == 4))["off_pre"][0]
    assert b_def > 0.2
    assert abs(a_off_after - 0.5 * (0.4 - b_def)) < 1e-12


def test_season_shrink():
    g = _games([(2020, 1, "A", "B", 0.4, 0.0), (2020, 1, "B", "A", 0.0, 0.4),
                (2021, 1, "A", "B", 0.0, 0.0), (2021, 1, "B", "A", 0.0, 0.0)])
    r = ratings(g, half_life=1.0, shrink=0.5).filter(pl.col("season") == 2021, pl.col("team") == "A")
    assert abs(r["off_pre"][0] - 0.5 * 0.2) < 1e-12
