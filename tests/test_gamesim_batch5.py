"""Known-answer checks for batch 5 (nfl-betting-model docs/batch5_preregistration.md, checks 1-6)."""
import json
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim import batch5 as B, elo as E, tdfg as T

K = {"c_T": 0.11, "b_T": 0.1, "theta_T": float("inf"), "c_F": 0.07, "b_F": 0.03, "s": 0.03, "p": [0.1, 0.86, 0.04]}


def tdfg_margin(d, lv):
    ph, pa = T.game_pmfs(d, lv, K)
    _, pm = E.margin_dist(ph, pa)
    return pm


def test_s1_reduces_and_matches_monte_carlo():
    d, lv = np.array([60.0]), np.array([22.0])
    assert np.abs(B.s1_margin(d, lv, K, 0.0) - tdfg_margin(d, lv)).max() < 1e-6
    c0 = 0.02
    pm = B.s1_margin(d, lv, K, c0)[0]
    assert abs(pm.sum() - 1) < 1e-4  # only mass above 100 points per team is cut
    rng = np.random.default_rng(1)
    n = 200_000
    th, ta = T.rates(d, lv, K["c_T"], K["b_T"])
    fh, fa = T.rates(d, lv, K["c_F"], K["b_F"])
    l0 = c0 * 22.0
    x0 = rng.poisson(l0, n)
    t_h, t_a = rng.poisson(th[0] - l0, n) + x0, rng.poisson(ta[0] - l0, n) + x0

    def pts(t, f):
        conv = np.array([rng.choice(3, size=k, p=K["p"]).sum() for k in t])
        return 6 * t + conv + 3 * rng.poisson(f, n) + 2 * rng.poisson(K["s"], n)
    m = pts(t_h, fh[0]) - pts(t_a, fa[0])
    emp = np.array([np.mean(m == v) for v in range(-E.MAXPTS, E.MAXPTS + 1)])
    assert np.abs(emp - pm).max() < 0.003


def test_s1_fit_recovers_c0():
    rng = np.random.default_rng(2)
    n = 6000
    lv = np.full(n, 22.0)
    lt_h, lt_a = np.full(n, 2.6), np.full(n, 2.2)
    c0 = 0.03
    x0 = rng.poisson(c0 * 22.0, n)
    th = rng.poisson(lt_h - c0 * 22.0) + x0
    ta = rng.poisson(lt_a - c0 * 22.0) + x0
    got = B.fit_c0(th, ta, lv, lt_h, lt_a, hi=0.08)
    assert abs(got / c0 - 1) < 0.25


def test_k1_sums_and_recovers_weights():
    p = B.k1_dist([3.0, -2.0], 13.0, np.ones(B.KMAX + 1))
    assert np.allclose(p.sum(1), 1)
    rng = np.random.default_rng(3)
    mu = rng.normal(0, 5, 20000)
    w_true = np.ones(B.KMAX + 1)
    w_true[3] = 3.0
    pm = B.k1_dist(mu, 13.5, w_true)
    m = np.array([rng.choice(B.M, p=row) for row in pm])
    f = B.fit_k1(mu, m)
    assert abs(f["w"][3] / 3.0 - 1) < 0.2
    pm0 = B.k1_dist(mu, 13.5, np.ones(B.KMAX + 1))
    m0 = np.array([rng.choice(B.M, p=row) for row in pm0])
    f0 = B.fit_k1(mu, m0)
    assert max(abs(x - 1) for x in f0["w"][:21]) < 0.4


def test_r1_hand_case():
    ek = json.loads((Path(__file__).resolve().parents[1] / "data" / "gamesim" / "elo_constants.json").read_text())
    g = pl.DataFrame({"season": [2010, 2010], "week": [1, 2], "game_id": ["a", "b"], "home_team": ["X", "Y"],
                      "away_team": ["Y", "X"], "result": [7, -3], "neutral": [False, False]})
    lv = {"a": 22.0, "b": 22.0}
    r = B.run_market_start(g, ek["k"], ek["h"], ek["c"], ek["b"], lv, {"a": 3.0})
    d0 = r.filter(pl.col("game_id") == "a")["d"][0]
    assert abs(float(B.fair([d0], [22.0], ek["b"])[0]) - 3.0) < 0.05
    base = ek["h"]  # both teams start at 1500, so with no move d would equal home field
    assert d0 > base


def league(rng, st, weeks=6, sd=3.0):
    rows = []
    n = len(st)
    for w in range(1, weeks + 1):
        perm = rng.permutation(n)
        for j in range(0, n, 2):
            h, a = int(perm[j]), int(perm[j + 1])
            rows.append({"season": 2010, "week": w, "game_id": f"{w}_{h}_{a}", "home_team": f"T{h:02d}",
                         "away_team": f"T{a:02d}", "result": float(st[h] - st[a] + rng.normal(0, sd)), "neutral": True})
    return pl.DataFrame(rows)


def test_r2_recovers_and_no_lookahead():
    rng = np.random.default_rng(4)
    st = rng.normal(0, 7, 32)
    g = league(rng, st, weeks=7)
    full = B.ridge_run(g, 0.0, 1.0, 0.0)
    w7 = full.join(g, on="game_id").filter(pl.col("week") == 7)
    truth = [st[int(h[1:])] - st[int(a[1:])] for h, a in zip(w7["home_team"], w7["away_team"])]
    assert np.corrcoef(w7["ridge"], truth)[0, 1] >= 0.9
    part = B.ridge_run(g.filter(pl.col("week") <= 4), 0.0, 1.0, 0.0)
    j = part.join(full, on="game_id", suffix="_f")
    assert np.allclose(j["ridge"], j["ridge_f"])


def test_total_grading():
    over = lambda tot, line: "W" if tot > line else ("P" if tot == line else "L")  # noqa: E731
    assert over(45, 44.5) == "W" and over(44, 44) == "P"
