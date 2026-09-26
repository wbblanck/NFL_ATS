import datetime as dt
import json

import numpy as np
import polars as pl
import pytest

from engine.backtest import walk_forward
from engine.data import store
from engine.picks import final, live
from tests.conftest import FIX
from tests.test_final_picks import LOCK, _league, _with_history

EVENTS = json.loads((FIX / "parlay_nfl_spreads_trimmed.json").read_text())


def _synthetic(seed=0):
    rng = np.random.default_rng(seed)
    n = 3000
    close = rng.choice(np.arange(-10, 10.5, 0.5), n)
    return pl.DataFrame({"game_id": [f"g{i}" for i in range(n)], "season": np.repeat(np.arange(2003, 2009), n // 6),
                         "week": np.tile(np.arange(1, 18), n // 17 + 1)[:n],
                         "margin": np.round(-close + rng.normal(0, 13, n)).astype(int), "close": close,
                         "open": close + rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], n) + 0.5 * (close % 1 == 0)})


def test_reproducible_same_data_same_output():
    df = _synthetic()
    a, _ = walk_forward.predict(df, 2006, 2008)
    b, _ = walk_forward.predict(df, 2006, 2008)
    assert a.equals(b)


def test_walk_forward_trains_only_on_past():
    df = _synthetic()
    d, _ = walk_forward.predict(df, 2006, 2006)
    # perturb only the TEST season's outcomes: predictions must not change
    df2 = df.with_columns(pl.when(pl.col("season") == 2006).then(pl.col("margin") + 50).otherwise(pl.col("margin")).alias("margin"))
    d2, _ = walk_forward.predict(df2, 2006, 2006)
    assert np.allclose(d["p_home"].to_numpy(), d2["p_home"].to_numpy())


def test_live_grading(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS)
    played = sched.with_columns(
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(3).otherwise(pl.col("result")).alias("result"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(24).otherwise(None).alias("home_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(21).otherwise(None).alias("away_score"))
    s = live.grade(played)
    # GB won by 3 vs league -6.5 -> ATL covers; pick was ATL -> W
    assert (s["W"], s["L"], s["N"]) == (1, 0, 1) and s["claim_allowed"] is False
    assert (tmp_root / "data" / "predictions" / "live_record.md").exists()


def test_shadow_keynum_recorded_and_graded(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    r = final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS)[0]
    assert r["shadow_pick_keynum"] in ("GB", "ATL") and 0 < r["shadow_p_home_keynum"] < 1
    played = sched.with_columns(
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(24).otherwise(None).alias("home_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(21).otherwise(None).alias("away_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(3).otherwise(pl.col("result")).alias("result"))
    s = live.grade(played)
    assert s["shadow_keynum"]["W"] + s["shadow_keynum"]["L"] == 1


def test_projection_recorded_and_graded(tmp_root, week3_schedule):
    from engine.models import projection as P
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    rng = np.random.default_rng(5)
    teams = ["GB", "ATL", "CHI", "DET", "MIN", "NYG"]
    rows = []
    for t in range(2000):
        a, b = rng.choice(teams, 2, replace=False)
        for team, opp, home in ((a, b, 1), (b, a, 0)):
            td, fg = rng.poisson(2.4), rng.poisson(1.6)
            rows.append({"game_id": f"x{t}", "season": 2020 + t // 400, "week": 1 + (t % 400) // 25,
                         "gameday": "2020-01-01", "team": team, "opp": opp, "home": home,
                         "pts": 7 * td + 3 * fg, "td": td, "fg": fg, "pat": td, "saf": 0})
    games = pl.DataFrame(rows).with_columns((pl.col("season") * 25 + pl.col("week")).alias("t"))
    final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS, proj_games=games)
    pj = store.read_rows(final.projections_path())
    assert len(pj) == 1 and pj[0]["proj_pick"] in ("GB", "ATL") and float(pj[0]["proj_home_pts"]) > 0
    played = sched.with_columns(
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(24).otherwise(None).alias("home_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(21).otherwise(None).alias("away_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(3).otherwise(pl.col("result")).alias("result"))
    s = live.grade(played)
    assert s["projection_model"]["W"] + s["projection_model"]["L"] == 1


def _v3_model():
    from engine.features import players_v3 as V
    beta = {"intercept": {"td": 0.0, "fg": 0.0}, **{f: {"td": 0.0, "fg": 0.0} for f in V.FEATURES}}
    beta["qb_delta"] = {"td": 2.0, "fg": 0.0}
    return {"version": "proj-players-v3", "D": 365, "k": 500, "prior": -0.07, "features": V.FEATURES,
            "beta": beta, "trained_on": "test"}


def _v3_row(team, qb_delta, published):
    from engine.features import players_v3 as V
    r = {f: 0.0 for f in V.FEATURES}
    r.update(game_id="2026_03_ATL_GB", team=team, qb_delta=qb_delta, starter="00-1", qb_wdropbacks=500.0,
             snapshot="2026-09-24T12:00:00Z", qb1_out=False, n_injury_rows=0, dome_estimated=False,
             injury_status_published=published)
    return r


@pytest.mark.parametrize("published", [True, False])
def test_players_v3_recorded_flagged_and_graded(tmp_root, week3_schedule, published):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    rng = np.random.default_rng(5)
    rows = []
    for t in range(2000):
        a, b = rng.choice(["GB", "ATL", "CHI", "DET"], 2, replace=False)
        for team, opp, home in ((a, b, 1), (b, a, 0)):
            td, fg = rng.poisson(2.4), rng.poisson(1.6)
            rows.append({"game_id": f"x{t}", "season": 2020 + t // 400, "week": 1 + (t % 400) // 25,
                         "gameday": "2020-01-01", "team": team, "opp": opp, "home": home,
                         "pts": 7 * td + 3 * fg, "td": td, "fg": fg, "pat": td, "saf": 0})
    games = pl.DataFrame(rows).with_columns((pl.col("season") * 25 + pl.col("week")).alias("t"))
    feats = pl.DataFrame([_v3_row("GB", -0.2, published), _v3_row("ATL", 0.0, published)])
    seen = []

    def loader(ids):
        seen.extend(ids)
        return {"model": _v3_model(), "features": feats}

    final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS, proj_games=games, v3=loader)
    assert seen == ["2026_03_ATL_GB"]
    pj = {r["model_version"]: r for r in store.read_rows(final.projections_path())}
    assert set(pj) == {"proj-poisson-v1", "proj-players-v3"}
    # a backup-level home QB (qb_delta -0.2, beta 2.0) lowers the home projection
    assert float(pj["proj-players-v3"]["proj_home_pts"]) < float(pj["proj-poisson-v1"]["proj_home_pts"])
    info = json.loads(pj["proj-players-v3"]["inputs"])
    assert info["home"]["qb_delta"] == -0.2
    assert info["flags"] == ([] if published else ["INJ_STATUS_MISSING"])
    played = sched.with_columns(
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(24).otherwise(None).alias("home_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(21).otherwise(None).alias("away_score"),
        pl.when(pl.col("game_id") == "2026_03_ATL_GB").then(3).otherwise(pl.col("result")).alias("result"))
    s = live.grade(played)["projection_models"]
    assert s["proj-poisson-v1"]["W"] + s["proj-poisson-v1"]["L"] == 1
    v3 = s["proj-players-v3"]
    assert (v3["W"] + v3["L"], v3["excluded_inj_status_missing"]) == ((1, 0) if published else (0, 1))


def test_players_v3_loader_failure_never_blocks_picks(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)

    def broken(ids):
        raise RuntimeError("nflverse down")

    out = final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS, proj_games=None, v3=broken)
    assert len(out) == 1 and store.read_rows(final.predictions_path())
