import datetime as dt
import json

import numpy as np
import polars as pl

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
