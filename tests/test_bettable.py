import numpy as np
import polars as pl

from engine.backtest import bettable as B
from engine.picks import bettable as LB


def test_grade_and_summary_use_the_closing_line_and_refund_pushes():
    margin = np.array([10, 3, -7, 4])
    close = np.array([-3.5, -3.0, 2.5, -4.0])          # home spread
    pick_home = np.array([True, True, False, False])
    g = B.grade(pick_home, margin, close)
    # home -3.5 wins by 10: pick home covers; home -3 wins by 3: push; home +2.5 loses by 7: away covers;
    # home -4 wins by 4: push, so the away pick neither wins nor loses
    assert list(g) == [1, 0, 1, 0]
    s = B.summarize(g)
    assert (s["W"], s["L"], s["push"], s["n"]) == (2, 0, 2, 2)
    assert abs(s["units"] - 2 * 100 / 110) < 1e-9 and s["roi"] > 0.9


def test_break_even_and_holm():
    assert abs(B.BREAK_EVEN - 0.52381) < 1e-4
    ok = B.holm({"a": 0.001, "b": 0.02, "c": 0.4, "d": 0.5})
    assert ok == {"a": True, "b": False, "c": False, "d": False}       # 0.02 > 0.05/3


def test_live_record_is_graded_against_the_line_at_the_pick_not_the_pool_line():
    sched = pl.DataFrame({"game_id": ["g1", "g2"], "home_team": ["AAA", "CCC"], "result": [3, 1],
                          "home_score": [20, 17], "away_score": [17, 16]})
    preds = [{"game_id": "g1", "market_at_lock": "-3.5"}, {"game_id": "g2", "market_at_lock": "-1.0"}]
    graded = [{"game_id": "g1", "pick": "AAA", "shadow_pick": "BBB", "hybrid": "AAA W"},
              {"game_id": "g2", "pick": "CCC", "shadow_pick": "CCC", "hybrid": "DDD L"}]
    out = LB.live(graded, preds, sched)
    # g1: home -3.5 wins by 3 -> away covers; g2: home -1 wins by 1 -> push
    assert (out["official"]["W"], out["official"]["L"], out["official"]["push"]) == (0, 1, 1)
    assert (out["keynum"]["W"], out["keynum"]["L"], out["keynum"]["push"]) == (1, 0, 1)
    assert out["v3"]["n"] == 0 and out["v3"]["win_rate"] is None
