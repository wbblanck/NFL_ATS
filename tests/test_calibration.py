import numpy as np

from engine.backtest import calibration as C


def test_platt_identity_when_calibrated():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.3, 0.7, 20000)
    y = (rng.uniform(size=p.size) < p).astype(float)
    f = C.platt(p, y)
    assert abs(f.coef[1] - 1) < 0.15 and abs(f.coef[0]) < 0.05


def test_platt_shrinks_overconfident():
    rng = np.random.default_rng(1)
    true = rng.uniform(0.4, 0.6, 20000)
    y = (rng.uniform(size=true.size) < true).astype(float)
    over = C.expit(2 * C.logit(true))            # overconfident version
    f = C.platt(over, y)
    assert 0.35 < f.coef[1] < 0.65


def test_isotonic_monotone():
    rng = np.random.default_rng(2)
    p = rng.uniform(0, 1, 2000)
    y = (rng.uniform(size=p.size) < p).astype(float)
    g = C.isotonic(p, y)
    grid = np.linspace(0, 1, 101)
    out = g(grid)
    assert np.all(np.diff(out) >= -1e-12) and out.min() >= 0.01 and out.max() <= 0.99


def test_key_feature_signs():
    # market home -3 (centre +3); league -2.5 (t=2.5): margin 3 covers for home -> +1
    assert C.key_feature(np.array([-2.5]), np.array([-3.0]))[0] == 1
    # league -3.5 (t=3.5): margin 3 is an away cover -> -1
    assert C.key_feature(np.array([-3.5]), np.array([-3.0]))[0] == -1
    # league -6.5 vs market -7.5: 7 lies between -> +1
    assert C.key_feature(np.array([-6.5]), np.array([-7.5]))[0] == 1
    assert C.key_feature(np.array([-4.5]), np.array([-5.0]))[0] == 0


def test_ece_and_reliability_counts():
    p = np.array([0.35, 0.41, 0.5, 0.61])
    y = np.array([0.0, 1.0, 1.0, 1.0])
    rows = C.reliability(p, y)
    assert sum(r["n"] for r in rows) == 4 and len(rows) == 12
    assert 0 <= C.ece(p, y) <= 1
