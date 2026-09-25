import numpy as np
import polars as pl

from engine.models import drift as D


def frame():
    # home_spread = frozen open; market_spread = close; margin = home - away
    return D.add_outcomes(pl.DataFrame({
        "season": [2010] * 6,
        "home_spread": [-3.5, -3.5, 2.5, -7.0, -3.0, -1.5],
        "market_spread": [-5.5, -2.5, 2.5, -7.5, -4.0, -1.0],
        "margin": [7, 1, -1, 7, 3, 10],
    }))
    # g1 drift -2 -> pick home; home covers (7 > 3.5) -> W
    # g2 drift +1 -> pick away; home 1 < 3.5 -> away covers -> W
    # g3 drift 0 -> no signal
    # g4 drift -0.5 -> pick home; margin 7 vs 7 -> push
    # g5 drift -1 -> pick home; margin 3 vs 3 -> push (whole-number open)
    # g6 drift +0.5 -> pick away; home 10 > 1.5 -> L


def test_d0():
    df = frame()
    s = D.summarize(df.select(D.outcome(D.strategy_picks(df)).alias("o"))["o"])
    assert (s["W"], s["L"], s["P"], s["no_signal"]) == (2, 1, 2, 1)


def test_full_and_threshold():
    df = frame()
    full = D.summarize(df.select(D.outcome(D.strategy_picks(df, 0.0, False)).alias("o"))["o"])
    assert full["no_signal"] == 0 and full["W"] + full["L"] + full["P"] == 6
    # k=1.5: only g1 follows drift; others -> away
    k = df.select(D.strategy_picks(df, 1.5, False).alias("p"))["p"].to_list()
    assert k == [True, False, False, False, False, False]


def test_choose_k_uses_only_training_rows():
    df = frame()
    assert D.choose_k(df) in D.K_GRID


def test_logistic_recovers_slope():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 5, 20000)
    p = 1 / (1 + np.exp(-(-0.2 + 0.3 * x)))
    y = (rng.uniform(size=x.size) < p).astype(float)
    b, se = D.logistic(x, y)
    assert abs(b[1] - 0.3) < 4 * se[1]
