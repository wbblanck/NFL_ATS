"""Known-answer checks for the Kalman rating and the opener blend (nfl-betting-model docs/batch1_preregistration.md, checks 1-5)."""
import numpy as np
import polars as pl

from engine.gamesim import kalman as K

P = {"h": 0.0, "sigma_m": 13.0, "tau_w": 0.8, "rho": 0.7, "tau_s": 3.0}


def league(rng, strength, seasons, weeks=17, sd=13.5, drift=0.0):
    n = len(strength)
    s = np.array(strength, float)
    rows = []
    for y in range(seasons):
        for w in range(1, weeks + 1):
            s = s + rng.normal(0, drift, n) if drift else s
            perm = rng.permutation(n)
            for j in range(0, n, 2):
                h, a = int(perm[j]), int(perm[j + 1])
                rows.append({"season": 2000 + y, "week": w, "game_id": f"{y}_{w:02d}_{h}_{a}", "home_team": f"T{h}",
                             "away_team": f"T{a}", "result": int(round(rng.normal(s[h] - s[a], sd))), "neutral": True})
    return pl.DataFrame(rows)


def test_hand_case():
    mh, vh, ma, va, pred, s = K.update(0.0, 49.0, 0.0, 49.0, 10, 0.0, 13.0)
    assert abs(mh - 10 * 49 / (98 + 169)) < 1e-9 and abs(mh - 1.835) < 0.001 and abs(ma + mh) < 1e-12


def test_no_lookahead():
    g = league(np.random.default_rng(1), np.zeros(8), 1)
    full, _, _ = K.run(g, P)
    part, _, _ = K.run(g.filter(pl.col("week") < 9), P)
    j = full.join(part, on="game_id", suffix="_p")
    assert j.height == part.height and np.allclose(j["kalman"], j["kalman_p"])


def test_planted_signal_and_noise():
    rng = np.random.default_rng(3)
    top = 0
    for _ in range(200):
        st = np.zeros(32)
        st[0] = 7.0
        _, _, (M, _) = K.run(league(rng, st, 1), P)
        top += "T0" in sorted(M, key=M.get, reverse=True)[:8]
    assert top / 200 >= 0.9
    cors = []
    for _ in range(200):
        g = league(rng, np.zeros(32), 2)
        _, _, (M, _) = K.run(g.filter(pl.col("season") == 2000), P)
        nxt = g.filter(pl.col("season") == 2001)
        tot = {f"T{i}": 0.0 for i in range(32)}
        for h, a, m in zip(nxt["home_team"], nxt["away_team"], nxt["result"]):
            tot[h] += m
            tot[a] -= m
        ks = sorted(tot)
        cors.append(np.corrcoef([M[k] for k in ks], [tot[k] for k in ks])[0, 1])
    assert abs(np.mean(cors)) < 0.1


def test_blend_recovers_w():
    rng = np.random.default_rng(4)
    o = rng.normal(0, 6, 5000)
    m = o + rng.normal(0, 3, 5000)
    y = o + 0.3 * (m - o) + rng.normal(0, 13, 5000)
    assert abs(K.fit_blend(o, m, y) - 0.3) < 0.05


def test_fit_recovers_parameters():
    rng = np.random.default_rng(5)
    st = rng.normal(0, 5, 32)
    g = league(rng, st, 6, sd=12.0, drift=1.0)
    p = K.fit(g, list(range(2001, 2006)), x0=[0.0, 10.0, 0.5, 0.9, 2.0])
    assert abs(p["sigma_m"] / 12.0 - 1) < 0.25
    assert abs(p["tau_w"] / 1.0 - 1) < 0.25
