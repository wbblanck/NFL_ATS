import datetime as dt
import json

import polars as pl

from engine.data import store
from engine.picks import final
from tests.conftest import FIX

EVENTS = json.loads((FIX / "parlay_nfl_spreads_trimmed.json").read_text())   # ATL@GB, GB -4.5..-5.5
UTC = dt.timezone.utc
LOCK = dt.datetime(2026, 9, 25, 0, 0, tzinfo=UTC)   # ATL@GB kickoff 00:15Z


def _league(tmp_root, rows):
    p = tmp_root / "data" / "lines" / "league_lines.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("game_id,season,week,home_team,away_team,spread,favorite,source,recorded_at\n" + rows)


def test_decide_rules():
    assert final.decide(-6.5, -5.0, None)["pick"] == "away"          # market moved toward away
    assert final.decide(-4.5, -7.5, None)["pick"] == "home"
    d = final.decide(-2.5, -2.5, None)
    assert d["pick"] == "away" and d["pick_rule"] == "no_move_fallback_away"
    m = final.decide(None, -5.0, -6.5)
    assert m["data_status"] == "incomplete" and "LINE_FROM_CBS_ODDS_PAGE_OPEN" in m["flags"]
    n = final.decide(None, None, None)
    assert n["pick"] == "away" and n["missing_input"] == "league_line;market_at_lock"


def test_lock_run_writes_before_lock_once(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    now = LOCK - dt.timedelta(minutes=20)
    out = final.run(week3_schedule, now=now, window_minutes=25, events=EVENTS)
    assert [r["game_id"] for r in out] == ["2026_03_ATL_GB"]
    r = out[0]
    # lock-time test: prediction written before kickoff - lock_buffer
    assert dt.datetime.fromisoformat(r["created_at"]) < dt.datetime.fromisoformat(r["lock_utc"])
    assert r["market_at_lock"] > r["league_line"]          # market -5ish vs league -6.5 -> moved to ATL
    assert r["pick_team"] == "ATL" and r["data_status"] == "complete"
    # second run in the same window: immutable, nothing new
    assert final.run(week3_schedule, now=now + dt.timedelta(minutes=5), events=EVENTS) == []
    assert len(store.read_rows(final.predictions_path())) == 1
    assert (tmp_root / "data" / "predictions" / "slate_2026_w03.md").exists()


def test_games_outside_window_untouched(tmp_root, week3_schedule):
    _league(tmp_root, "")
    out = final.run(week3_schedule, now=LOCK - dt.timedelta(hours=3), window_minutes=25, events=EVENTS)
    assert out == []


def test_manual_fallback_after_lock_is_flagged(tmp_root, week3_schedule):
    _league(tmp_root, "")
    out = final.run(week3_schedule, now=LOCK + dt.timedelta(minutes=5), events=EVENTS, game_id="2026_03_ATL_GB")
    assert len(out) == 1 and "LATE_AFTER_LOCK" in out[0]["flags"]
    assert out[0]["data_status"] == "incomplete"            # no league line recorded


def _with_history(sched):
    """Append 2000 synthetic past games: margin = -close + noise, so P(cover) is sensible."""
    import numpy as np
    rng = np.random.default_rng(1)
    n = 2000
    close = rng.choice(np.arange(-10, 10.5, 0.5), n)
    hist = pl.DataFrame({
        "game_id": [f"h{i}" for i in range(n)], "away_team": ["X"] * n, "home_team": ["Y"] * n,
        "gameday": ["2020-01-01"] * n, "gametime": ["13:00"] * n, "season": [2020] * n, "week": [1] * n,
        "game_type": ["REG"] * n,
        "kickoff_utc": [dt.datetime(2020, 1, 1, tzinfo=UTC)] * n, "lock_utc": [dt.datetime(2020, 1, 1, tzinfo=UTC)] * n,
        "result": np.round(-close + rng.normal(0, 13, n)).astype(int), "spread_line": -close,
    }).with_columns(pl.col("kickoff_utc").cast(sched["kickoff_utc"].dtype), pl.col("lock_utc").cast(sched["lock_utc"].dtype))
    cur = sched.with_columns(pl.lit(None, pl.Int64).alias("result"), pl.lit(None, pl.Float64).alias("spread_line"))
    return pl.concat([cur, hist.select(cur.columns)], how="vertical_relaxed")


def test_probabilities_sum_to_one_and_pick_is_argmax(tmp_root, week3_schedule):
    _league(tmp_root, "2026_03_ATL_GB,2026,3,GB,ATL,-6.5,GB,test,x\n")
    sched = _with_history(week3_schedule)
    r = final.run(sched, now=LOCK - dt.timedelta(minutes=20), events=EVENTS)[0]
    assert abs(r["p_home_cover"] + r["p_away_cover"] - 1) < 1e-3
    assert r["model_version"] == final.MODEL_VERSION and r["pick_rule"] == "argmax_cover_prob"
    # market ~ GB -5 vs league GB -6.5 -> GB less likely to cover -> ATL
    assert r["p_away_cover"] > 0.5 and r["pick_team"] == "ATL"
    assert "kickoff <" in r["training_period"]


def test_distribution_uses_only_games_before_now(week3_schedule):
    sched = _with_history(week3_schedule)
    md, period = final.fit_dist(sched, dt.datetime(2019, 1, 1, tzinfo=UTC))   # before all history
    assert md is None
