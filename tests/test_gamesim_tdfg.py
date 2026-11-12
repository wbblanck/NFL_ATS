"""Known-answer checks for the touchdown/field-goal score model and the expected-starter rule
(nfl-betting-model docs/batch3_preregistration.md, checks 1-5)."""

import numpy as np

from engine.gamesim import elo as E, tdfg as T

K = {"c_T": 0.11, "b_T": 0.12, "theta_T": 15.0, "c_F": 0.075, "b_F": 0.05, "s": 0.03, "p": [0.06, 0.88, 0.06]}


def draw(rng, d, level, k, home=True):
    sg = 1 if home else -1
    lt = k["c_T"] * level * np.exp(sg * k["b_T"] * d / 100)
    lf = k["c_F"] * level * np.exp(sg * k["b_F"] * d / 100)
    th = k["theta_T"]
    t = rng.negative_binomial(th, th / (th + lt))
    f = rng.poisson(lf)
    s = rng.poisson(k["s"], len(d))
    conv = np.array([rng.choice(3, size=n, p=k["p"]).sum() for n in t])
    return t, f, s, 6 * t + conv + 3 * f + 2 * s


def test_sums_and_mean():
    p = np.array(K["p"])
    pm = T.points_pmf([2.4], K["theta_T"], [1.6], K["s"], p)[0]
    assert abs(pm.sum() - 1) < 1e-5  # only mass above MAXPTS (100) points is cut: 6e-6 here
    mean = (pm * np.arange(len(pm))).sum()
    assert abs(mean - (2.4 * (6 + p[1] + 2 * p[2]) + 3 * 1.6 + 2 * K["s"])) < 1e-3  # the cut mass above 100 points moves the mean by 7e-4


def test_monte_carlo():
    rng = np.random.default_rng(1)
    d, lv = np.full(200_000, 80.0), np.full(200_000, 22.0)
    *_, pts = draw(rng, d, lv, K)
    emp = np.bincount(pts, minlength=E.MAXPTS + 1)[: E.MAXPTS + 1] / len(pts)
    ph, _ = T.game_pmfs([80.0], [22.0], K)
    assert np.abs(emp - ph[0]).max() < 0.003


def test_fit_recovers():
    rng = np.random.default_rng(2)
    d, lv = rng.normal(0, 120, 6000), rng.uniform(20, 24, 6000)
    th, fh, *_ = draw(rng, d, lv, K, True)
    ta, fa, *_ = draw(rng, d, lv, K, False)
    ft = T.fit_counts(d, lv, th, ta, nb=True)
    ff = T.fit_counts(d, lv, fh, fa, nb=False)
    for got, want in ((ft["c"], K["c_T"]), (ft["b"], K["b_T"]), (ff["c"], K["c_F"]), (ff["b"], K["b_F"])):
        assert abs(got / want - 1) < 0.10


def margin_lp(ph, pa, m):
    ms, pm = E.margin_dist(ph, pa)
    return np.log(np.maximum(pm[np.arange(len(m)), m + E.MAXPTS], 1e-300))


def nb_fit(rng, k_gen, smooth):
    d, lv = rng.normal(0, 120, 3000), np.full(3000, 22.0)
    if smooth:
        mh, ma = E.means(d, lv, 0.09)
        hs, as_ = rng.negative_binomial(6.0, 6.0 / (6.0 + mh)), rng.negative_binomial(6.0, 6.0 / (6.0 + ma))
    else:
        hs, as_ = draw(rng, d, lv, k_gen, True)[3], draw(rng, d, lv, k_gen, False)[3]
    b = E.fit_b(d, lv, hs, as_)
    return b, E.fit_theta(d, lv, hs, as_, b)


def t1(rng, smooth):
    b, th = nb_fit(rng, K, smooth)
    d, lv = rng.normal(0, 120, 2000), np.full(2000, 22.0)
    if smooth:
        mh, ma = E.means(d, lv, 0.09)
        hs, as_ = rng.negative_binomial(6.0, 6.0 / (6.0 + mh)), rng.negative_binomial(6.0, 6.0 / (6.0 + ma))
    else:
        hs, as_ = draw(rng, d, lv, K, True)[3], draw(rng, d, lv, K, False)[3]
    mh, ma = E.means(d, lv, b)
    nb = margin_lp(E.nb_pmf(mh, th), E.nb_pmf(ma, th), hs - as_)
    ph, pa = T.game_pmfs(d, lv, K)
    return float((margin_lp(ph, pa, hs - as_) - nb).mean())


def test_planted_and_noise():
    assert t1(np.random.default_rng(3), smooth=False) > 0
    assert t1(np.random.default_rng(4), smooth=True) <= 0


def test_expected_starter_rule():
    g = {100: {"A": 30, "B": 2}, 107: {"A": 35}, 90: {"C": 10}}
    assert T.pick(g, 114, 2024, 3, "X", {(2024, 3, "X", "A")}, "R") == "C"
    assert T.pick(g, 114, 2024, 3, "X", set(), "R") == "A"  # Questionable or healthy: keep the previous starter
    assert T.pick({107: {"A": 35}}, 114, 2024, 3, "X", {(2024, 3, "X", "A")}, "R") == "UNKNOWN"
    assert T.pick({}, 114, 2024, 1, "X", set(), "R") == "R"


def test_expected_starter_tie_goes_to_smallest_id_whatever_the_row_order():
    a = {"Q2": 30, "Q1": 30, "Q3": 5}
    b = {"Q3": 5, "Q1": 30, "Q2": 30}
    assert T.top_qb(a) == T.top_qb(b) == "Q1"
    assert T.top_qb({"Q9": 31, "Q1": 30}) == "Q9"
