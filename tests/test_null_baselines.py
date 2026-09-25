import math

import polars as pl

from engine.models.null import baseline_table, grade_frame, se


def frame():
    # home_spread canonical (neg = home fav); margin = home - away
    return pl.DataFrame({
        "season": [2020, 2020, 2020, 2020, 2021],
        "home_spread": [-3.5, -3.0, 2.5, 0.0, -7.0],
        "margin": [7, 3, -1, 4, 0],
    })
    # game1 home fav 3.5 wins by 7 -> home covers
    # game2 home fav 3 wins by 3 -> push
    # game3 away fav 2.5, home loses by 1 -> home covers
    # game4 pick'em, home +4 -> home covers (no favorite)
    # game5 home fav 7, tie -> away covers


def test_grade():
    r = grade_frame(frame())["result"].to_list()
    assert r == ["home", "push", "home", "home", "away"]


def test_pooled_counts():
    t = {r["strategy"]: r for r in baseline_table(frame()).to_dicts()}
    assert (t["home"]["W"], t["home"]["L"], t["home"]["P"]) == (3, 1, 1)
    assert (t["away"]["W"], t["away"]["L"], t["away"]["P"]) == (1, 3, 1)
    # favorite: g1 W (home fav covered), g2 P, g3 L (away fav, home covered), g4 no_fav, g5 L (home fav failed)
    assert (t["favorite"]["W"], t["favorite"]["L"], t["favorite"]["P"], t["favorite"]["no_fav"]) == (1, 2, 1, 1)
    assert (t["underdog"]["W"], t["underdog"]["L"]) == (2, 1)
    assert t["home"]["win_rate"] == 0.75
    assert math.isclose(t["home"]["se"], math.sqrt(0.75 * 0.25 / 4))


def test_home_plus_away_complementary():
    t = baseline_table(frame(), by=["season"])
    for season in (2020, 2021):
        rows = {r["strategy"]: r for r in t.filter(pl.col("season") == season).to_dicts()}
        assert rows["home"]["W"] == rows["away"]["L"] and rows["home"]["P"] == rows["away"]["P"]


def test_se():
    assert math.isclose(se(0.5, 100), 0.05)
