"""Closing-line value (docs/clv_preregistration.md): a descriptive metric that never changes a pick or a grade."""
import math

import polars as pl

from engine.picks import live
from tests.test_integrity import _one_pick


def test_clv_points_sign_by_side():
    assert live.clv_points("home", 3.0, 2.0) == 1.0           # pool line gives home a point more than the reference
    assert live.clv_points("home", -7.0, -7.5) == 0.5
    assert live.clv_points("away", -6.5, -7.0) == -0.5        # pool line is a half point worse for the away side
    assert live.clv_points("away", 7.5, 8.5) == 1.0
    assert live.clv_points("home", -3.5, -3.5) == 0.0


def test_summary_counts_and_standard_error():
    s = live._clv_summary([{"clv_close": 1.0, "clv_lock": 0.5}, {"clv_close": -0.5, "clv_lock": 0.0},
                           {"clv_close": 0.0, "clv_lock": None}, {"clv_close": None, "clv_lock": None}])
    assert s["close"]["n"] == 3 and s["close"]["positive"] == 1 and s["close"]["zero"] == 1
    assert math.isclose(s["close"]["mean"], 0.5 / 3)
    assert s["lock"]["n"] == 2 and math.isclose(s["lock"]["mean"], 0.25)


def test_summary_empty_is_nan_not_an_error():
    s = live._clv_summary([])
    assert s["close"]["n"] == 0 and math.isnan(s["close"]["mean"]) and live._clv_note({"clv": s}) == ""


def test_graded_rows_carry_clv_and_grades_are_unchanged(tmp_root, week3_schedule):
    played = _one_pick(tmp_root, week3_schedule)
    g = pl.col("game_id") == "2026_03_ATL_GB"
    with_close = played.with_columns(pl.when(g).then(7.0).otherwise(pl.col("spread_line")).alias("spread_line"))
    s0, rows0 = live.compute(played)                       # fixture game has no nflverse close
    s, rows = live.compute(with_close)                     # nflverse close: GB -7.0
    assert (s["W"], s["L"], s["N"]) == (s0["W"], s0["L"], s0["N"])           # the metric never touches the record
    assert rows0[0]["clv_close"] is None and rows0[0]["clv_lock"] is not None
    r = rows[0]                                           # ATL (away) picked against the pool line GB -6.5
    assert r["pick"] == "ATL" and r["league_line"] == -6.5
    assert math.isclose(r["clv_close"], -0.5)             # away: close (-7.0) minus pool (-6.5)
    assert s["clv"]["close"]["n"] == 1 and s["clv"]["close"]["positive"] == 0
    live.grade(with_close)
    assert "Closing-line value" in (tmp_root / "data/predictions/live_record.md").read_text()
