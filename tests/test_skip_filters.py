import numpy as np

from engine.backtest import skip_filters as S
from engine.backtest import bettable as B


def _m():
    # four picks, worked by hand
    return {
        "pick_home": np.array([True, False, True, False]),
        "stale": np.array([-3.5, 3.5, 0.0, -7.5]),          # home spreads on the stale line
        "close": np.array([-4.0, 3.5, 1.0, -6.5]),          # closing: move 0.5, 0, 1, 1
        "week": np.array([3, 10, 5, 12]),
        "total": np.array([44.0, 46.0, np.nan, 50.0]),
        "div": np.array([True, False, False, True]),
    }


def test_move_and_tier_rules():
    k = S.masks(_m())
    # moves: 0.5, 0, 1, 1
    assert list(k["M1"]) == [True, False, True, True]          # move > 0
    assert list(k["M2"]) == [False, False, True, True]         # move >= 1
    assert list(k["M4"]) == [False, False, False, False]       # move >= 3
    assert list(k["M5"]) == [True, True, False, False]         # move < 1 (Lean)
    assert list(k["M7"]) == [True, True, True, True]           # move < 3


def test_crossing_key_numbers_uses_the_patterns_definition():
    # idx 3: stale 7.5, closing 6.5 -> 7 is strictly between 6.5 and 7.5? no: 7 lies in (6.5, 7.5): crossed
    k = S.masks(_m())
    assert list(k["K1"]) == [False, False, False, True]
    assert list(k["K2"]) == [True, True, True, False]


def test_size_favorite_total_week_division_rules():
    k = S.masks(_m())
    assert list(k["S1"]) == [False, False, True, False]        # |stale| <= 3 (idx 2 is 0)
    assert list(k["S2"]) == [True, True, False, False]         # 3 < |stale| <= 7
    assert list(k["S3"]) == [False, False, False, True]        # |stale| > 7
    assert list(k["U1"]) == [True, True, False, False]         # favorite on the stale line
    assert list(k["U2"]) == [False, False, False, True]        # underdog on the stale line
    assert list(k["T1"]) == [False, True, False, True]         # total >= 45; the missing total is in neither
    assert list(k["T2"]) == [True, False, False, False]
    assert list(k["W1"]) == [True, False, True, False]         # week <= 8
    assert list(k["D1"]) == [True, False, False, True]


def test_probability_and_agreement_rules_only_when_available():
    m = _m()
    assert "P1" not in S.masks(m)
    m["prob"] = np.array([0.50, 0.53, 0.55, 0.58])
    m["agree"] = np.array([True, True, False, False])
    k = S.masks(m)
    assert list(k["P1"]) == [False, True, True, True]
    assert list(k["P2"]) == [False, False, True, True]
    assert list(k["A1"]) == [True, True, False, False] and list(k["A2"]) == [False, False, True, True]


def test_stats_leave_pushes_out_and_use_break_even():
    g = np.array([1, 1, -1, 0, 1, -1])
    s = S._stats(g, np.ones(6, bool))
    assert (s["W"], s["L"], s["n"]) == (3, 2, 5)
    assert abs(s["win_rate"] - 0.6) < 1e-12
    assert abs(s["roi"] - (3 * B.WIN - 2) / 5) < 1e-12
    assert s["z"] > 0
    empty = S._stats(g, np.zeros(6, bool))
    assert empty["n"] == 0 and empty["win_rate"] is None


def test_holm_is_strict_for_the_best_of_many():
    ps = {f"t{i}": 0.001 * (i + 1) for i in range(60)}          # 60 tests; smallest p 0.001 > 0.05/60
    ok = B.holm(ps)
    assert ok["t0"] is False and not any(ok.values())
    assert B.holm({"a": 0.0001, "b": 0.5})["a"] is True
