import polars as pl
import pytest

from engine.features import players_v3 as V


def _qbg(rows):
    return pl.DataFrame(rows, schema={"qb": pl.Utf8, "game_id": pl.Utf8, "game_date": pl.Utf8, "season": pl.Int32,
                                      "season_type": pl.Utf8, "week": pl.Int32, "team": pl.Utf8, "n": pl.UInt32,
                                      "s": pl.Float64}, orient="row").with_columns(
        pl.col("game_date").map_elements(V._day, return_dtype=pl.Int64).alias("day"))


def test_rating_uses_only_earlier_games_and_shrinks_to_prior():
    g = _qbg([("A", "g1", "2020-09-13", 2020, "REG", 1, "X", 40, 8.0),
              ("A", "g2", "2020-09-20", 2020, "REG", 2, "X", 40, -40.0)])
    r = V.QBRater(g, D=365, k=100, prior=-0.1)
    day2 = V._day("2020-09-20")
    rating, wn = r.rating("A", day2)             # g2 is on the same day -> excluded
    w = 0.5 ** (7 / 365)
    assert wn == pytest.approx(40 * w)
    assert rating == pytest.approx((8.0 * w + 100 * -0.1) / (40 * w + 100))
    assert r.rating("A", V._day("2020-09-13")) == (-0.1, 0.0)    # nothing before the first game
    assert r.rating("nobody", day2) == (-0.1, 0.0)


def _sched(games):
    base = {"game_type": "REG", "location": "Home", "roof": "outdoors", "div_game": 0, "stadium_id": "X00",
            "home_rest": 7, "away_rest": 7, "home_qb_id": None, "away_qb_id": None, "gametime": "13:00"}
    return pl.DataFrame([{**base, **g} for g in games])


def test_context_variables():
    s = _sched([
        {"game_id": "a", "season": 2020, "week": 1, "gameday": "2020-09-13", "home_team": "SEA", "away_team": "NYJ",
         "home_rest": 14, "away_rest": 4, "roof": "closed", "div_game": 1},
        {"game_id": "b", "season": 2020, "week": 2, "gameday": "2020-09-20", "home_team": "JAX", "away_team": "STL",
         "location": "Neutral", "stadium_id": "LON00"},
        {"game_id": "c", "season": 2020, "week": 3, "gameday": "2020-09-27", "home_team": "BUF", "away_team": "MIN",
         "location": "Neutral", "stadium_id": "DET00"},
    ])
    tg = V.team_game_frame(s)
    r = {(x["game_id"], x["team"]): x for x in tg.iter_rows(named=True)}
    assert r[("a", "SEA")]["tz_shift"] == 0 and r[("a", "NYJ")]["tz_shift"] == 3
    assert r[("a", "SEA")]["rest_diff"] == 7 and r[("a", "NYJ")]["rest_diff"] == -7
    assert r[("a", "SEA")]["off_bye"] == 1 and r[("a", "NYJ")]["short_week"] == 1
    assert r[("a", "SEA")]["dome"] == 1 and r[("a", "NYJ")]["division"] == 1
    assert r[("b", "JAX")]["tz_shift"] == 5 and r[("b", "LA")]["tz_shift"] == 5     # international, STL -> LA franchise
    assert r[("c", "BUF")]["tz_shift"] == 0 and r[("c", "MIN")]["tz_shift"] == 1    # domestic neutral site (Detroit)


def test_qb_delta_zero_for_usual_starter_positive_for_upgrade():
    s = _sched([{"game_id": f"g{w}", "season": 2020, "week": w, "gameday": f"2020-10-{7 * w:02d}",
                 "home_team": "SEA", "away_team": "SF", "home_qb_id": "B" if w in (2, 3) else "A", "away_qb_id": "Z"}
                for w in range(1, 5)])
    qbg = _qbg([(("B" if w in (2, 3) else "A"), f"g{w}", f"2020-10-{7 * w:02d}", 2020, "REG", w, "SEA", 40,
                 (-8.0 if w in (2, 3) else 8.0)) for w in range(1, 5)]
               + [("A", "old", "2019-12-01", 2019, "REG", 13, "SEA", 400, 80.0)])
    tg = V.team_game_frame(s).with_columns(pl.col("qb_recorded").alias("starter"))
    q = V.qb_features(tg.filter(pl.col("team") == "SEA"), qbg, V.QBRater(qbg, 365, 100, -0.1))
    d = {r["game_id"]: r["qb_delta"] for r in q.iter_rows(named=True)}
    assert d["g2"] < 0          # backup B replaces A, whose games are all behind the team rating
    assert d["g4"] > 0          # A returns after two B games are in the baseline


def test_injury_share_and_play_probability():
    tg = pl.DataFrame({"game_id": ["g1", "g2", "g1", "g2"], "team": ["SEA", "SEA", "SF", "SF"], "opp": ["SF", "SF", "SEA", "SEA"],
                       "t": [1, 2, 1, 2]})
    snaps = pl.DataFrame({"game_id": ["g1"], "team": ["SEA"], "gsis_id": ["p"], "offense_pct": [0.8],
                          "defense_pct": [0.0], "snaps": [50.0]})
    reps = pl.DataFrame({"game_id": ["g2"], "season": [2020], "week": [2], "team": ["SEA"], "gsis_id": ["p"],
                         "position": ["T"], "group": ["ol"], "report_status": ["Questionable"]})
    pp = {"Out": {"p_play": 0.0}, "Doubtful": {"p_play": 0.1}, "Questionable": {"p_play": 0.75}}
    f = V.injury_features(tg, reps, snaps, pp)
    r = f.filter((pl.col("game_id") == "g2") & (pl.col("team") == "SEA")).row(0, named=True)
    assert r["ol"] == pytest.approx(0.25 * 0.8)
    assert f.filter((pl.col("game_id") == "g2") & (pl.col("team") == "SF"))["ol"][0] == 0.0
