import datetime as dt

import polars as pl
import pytest

from engine.backtest import projection_v6_eval as E
from engine.features import efficiency_v6 as F


def _pbp(rows):
    base = {"season": 2020, "season_type": "REG", "pass": 1, "rush": 0, "qb_dropback": 1, "qb_kneel": 0, "qb_spike": 0,
            "two_point_attempt": 0, "epa": 0.0, "success": 0, "wp": 0.5, "half_seconds_remaining": 900,
            "fixed_drive": 1, "fixed_drive_result": "Punt", "drive_inside20": 0, "defteam": "BBB"}
    return pl.DataFrame([{**base, **r} for r in rows])


def test_filters_remove_garbage_time_kneels_spikes_and_two_point_tries():
    p = _pbp([
        {"game_id": "g", "posteam": "AAA", "epa": 1.0, "success": 1},
        {"game_id": "g", "posteam": "AAA", "epa": 9.0, "wp": 0.95},                   # garbage (wp)
        {"game_id": "g", "posteam": "AAA", "epa": 9.0, "half_seconds_remaining": 100},  # garbage (end of half)
        {"game_id": "g", "posteam": "AAA", "epa": 9.0, "qb_kneel": 1},
        {"game_id": "g", "posteam": "AAA", "epa": 9.0, "qb_spike": 1},
        {"game_id": "g", "posteam": "AAA", "epa": 9.0, "two_point_attempt": 1},
        {"game_id": "g", "posteam": "AAA", "epa": -1.0, "rush": 1, "pass": 0, "qb_dropback": 0},
    ])
    m = F.game_metrics(p).row(0, named=True)
    assert m["db"] == pytest.approx(1.0) and m["n_db"] == 1
    assert m["rush"] == pytest.approx(-1.0) and m["n_rush"] == 1
    assert m["sr"] == pytest.approx(0.5) and m["n_plays"] == 2


def test_red_zone_rate_counts_drives_not_plays_and_ignores_garbage_filter():
    p = _pbp([
        {"game_id": "g", "posteam": "AAA", "fixed_drive": 1, "drive_inside20": 1, "fixed_drive_result": "Touchdown"},
        {"game_id": "g", "posteam": "AAA", "fixed_drive": 1, "drive_inside20": 1, "fixed_drive_result": "Touchdown"},
        {"game_id": "g", "posteam": "AAA", "fixed_drive": 2, "drive_inside20": 1, "fixed_drive_result": "Field goal",
         "wp": 0.99},
        {"game_id": "g", "posteam": "AAA", "fixed_drive": 3, "drive_inside20": 0, "fixed_drive_result": "Touchdown"},
    ])
    m = F.game_metrics(p).row(0, named=True)
    assert m["n_rz"] == 2 and m["rz"] == pytest.approx(0.5)


def _sched(games):
    t0 = dt.datetime(2020, 9, 10, 17, tzinfo=dt.timezone.utc)
    return pl.DataFrame([{"game_id": g, "season": s, "game_type": "REG", "home_team": h, "away_team": a,
                          "home_score": 20, "kickoff_utc": t0 + dt.timedelta(days=7 * i)}
                         for i, (g, s, h, a) in enumerate(games)]).with_columns(pl.col("kickoff_utc").cast(pl.Datetime("us", "UTC")))


def _metrics(vals):
    return pl.DataFrame([{"game_id": g, "team": t, "db": db, "rush": 0.0, "sr": 0.45, "rz": 0.5}
                         for g, t, db in vals])


GAMES = [("2019_a", 2019, "AAA", "BBB"), ("2019_b", 2019, "CCC", "DDD"), ("2020_a", 2020, "AAA", "CCC"),
         ("2020_b", 2020, "BBB", "DDD"), ("2020_c", 2020, "AAA", "DDD"), ("2020_d", 2020, "BBB", "CCC")]
VALS = [("2019_a", "AAA", 0.3), ("2019_a", "BBB", -0.1), ("2019_b", "CCC", 0.0), ("2019_b", "DDD", 0.1),
        ("2020_a", "AAA", 0.4), ("2020_a", "CCC", -0.2), ("2020_b", "BBB", 0.1), ("2020_b", "DDD", 0.0),
        ("2020_c", "AAA", 0.2), ("2020_c", "DDD", 0.05), ("2020_d", "BBB", -0.3), ("2020_d", "CCC", 0.2)]


def test_ratings_are_point_in_time():
    sched, met = _sched(GAMES), _metrics(VALS)
    full = F.build(sched, met, 4, 0.3)
    for i, (gid, *_ ) in enumerate(GAMES):
        cut = F.build(sched.head(i + 1), met.filter(pl.col("game_id").is_in([g for g, *_ in GAMES[:i]])), 4, 0.3)
        a = cut.filter(pl.col("game_id") == gid).sort("team")
        b = full.filter(pl.col("game_id") == gid).sort("team")
        for c in F.FEATURES:
            assert a[c].to_list() == pytest.approx(b[c].to_list(), abs=1e-15)


def test_first_game_has_zero_ratings_and_better_offense_rates_higher():
    f = F.build(_sched(GAMES), _metrics(VALS), 4, 0.3)
    first = f.filter(pl.col("game_id") == "2019_a")
    assert all(v == 0.0 for c in F.FEATURES for v in first[c].to_list())
    g = f.filter(pl.col("game_id") == "2020_c").sort("team")     # AAA scored 0.3 then 0.4: best offense
    aaa = g.filter(pl.col("team") == "AAA").row(0, named=True)
    ddd = g.filter(pl.col("team") == "DDD").row(0, named=True)
    assert aaa["off_db"] > ddd["off_db"] > -1


def test_opponent_adjustment_discounts_output_against_a_bad_defense():
    # Two offenses post the same raw EPA, one against a defense already rated bad, one against an average defense.
    games = [("2019_x", 2019, "BAD", "Z1"), ("2019_y", 2019, "Z2", "Z3"),
             ("2020_a", 2020, "P", "BAD"), ("2020_b", 2020, "Q", "Z2"), ("2020_c", 2020, "P", "Q")]
    vals = [("2019_x", "BAD", 0.0), ("2019_x", "Z1", 0.5), ("2019_y", "Z2", 0.0), ("2019_y", "Z3", 0.0),
            ("2020_a", "P", 0.2), ("2020_a", "BAD", 0.0), ("2020_b", "Q", 0.2), ("2020_b", "Z2", 0.0)]
    f = F.build(_sched(games), _metrics(vals), 4, 0.0).filter(pl.col("game_id") == "2020_c")
    p = f.filter(pl.col("team") == "P").row(0, named=True)
    q = f.filter(pl.col("team") == "Q").row(0, named=True)
    assert p["off_db"] < q["off_db"]


def test_beta_zero_is_v1():
    r = {"lam_td": 2.3, "lam_fg": 1.6, **{c: 0.37 for c in F.FEATURES}}
    import numpy as np
    zero = {k: {"b": np.zeros(len(F.FEATURES) + 1)} for k in ("td", "fg")}
    assert E._adj(r, zero, "td", F.FEATURES) == r["lam_td"]
    assert E._adj(r, None, "fg", F.FEATURES) == r["lam_fg"]


def test_missing_kickoff_times_are_ordered_by_game_date():
    s = pl.DataFrame({"game_id": ["a", "b"], "gameday": ["1999-09-12", "1999-09-19"],
                      "kickoff_utc": [None, None]}).with_columns(pl.col("kickoff_utc").cast(pl.Datetime("us", "UTC")))
    k = F.with_order_time(s)["kickoff_utc"].to_list()
    assert k[0] is not None and k[0] < k[1]
