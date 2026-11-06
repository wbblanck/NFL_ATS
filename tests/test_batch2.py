"""Known-answer checks for batch 2 grading (docs/batch2_preregistration.md, checks 2-3)."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("batch2", Path(__file__).resolve().parents[1] / "scripts" / "batch2.py")
B2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B2)


def test_grading_hand_cases():
    c = B2.home_covers([4, 3, -2], [-3.5, -3, 2.5])
    assert c[0] == 1 and np.isnan(c[1]) and c[2] == 1
    assert B2.pick_home([5.0], [-3.5])[0] == 1 and B2.pick_home([2.0], [-3.5])[0] == 0
    r = B2.record([2.0, 5.0], [-3.5, -3.5], [7, 7])
    assert r[0] == 0 and r[1] == 1


def test_binomial_known_answers():
    assert abs(B2.binom_p(7, 10) - 176 / 1024) < 1e-12
    assert abs(B2.binom_lower(65, 100, 0.05) - 0.5639) < 0.002  # exact Clopper-Pearson one-sided bound


def test_planted_and_null():
    rng = np.random.default_rng(1)
    y = (rng.random(2000) < 0.65).astype(int)
    assert B2.binom_p(int(y.sum()), 2000) < 0.05
    hits = sum(B2.binom_p(int((np.random.default_rng(s).random(130) < 0.5).sum()), 130) <= 0.05 for s in range(200))
    assert hits <= 0.07 * 200
    # C1: game-level bootstrap of a paired mean with no true difference
    B2.B = 300
    hit = 0
    for s in range(200):
        d = np.random.default_rng(s).normal(0, 1.5, 130)
        hit += np.quantile(B2.boot(lambda ix, d=d: d[ix].mean(), np.arange(130)), 0.05) > 0
    B2.B = 2000
    assert hit <= 0.08 * 200
