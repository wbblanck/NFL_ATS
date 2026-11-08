"""Known-answer checks for batch 6 (docs/batch6_preregistration.md, checks 2-4)."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("batch6", Path(__file__).resolve().parents[1] / "scripts" / "batch6.py")
B6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B6)


def test_cover_probability_hand_cases():
    ms = np.arange(-5, 6)
    pm = np.zeros((3, len(ms)))
    pm[0, ms == 4] = 1.0                       # home wins by 4, home -3.5: certain cover
    pm[1, ms == 3] = 0.5
    pm[1, ms == 5] = 0.5                       # home -3: half pushes, rest covers -> 1 after removing pushes
    pm[2, ms == -2] = 0.5
    pm[2, ms == -4] = 0.5                      # home +2.5: -2 covers, -4 does not
    p = B6.p_home_cover(pm, ms, np.array([-3.5, -3.0, 2.5]))
    assert p[0] > 1 - 1e-9 and p[1] > 1 - 1e-9 and abs(p[2] - 0.5) < 1e-12


def test_logloss_known_answer():
    assert abs(B6.logloss(np.array([0.5]), np.array([1.0]))[0] - np.log(2)) < 1e-12


def test_planted_and_null_logloss():
    B6.B = 300
    rng = np.random.default_rng(3)
    p = rng.uniform(0.3, 0.7, 2000)
    y = (rng.random(2000) < p).astype(float)
    v = np.log(2) - B6.logloss(p, y)
    assert (B6.boot_mean(v) <= 0).mean() < 0.01           # planted signal found
    hits = 0
    for s in range(200):
        r = np.random.default_rng(s)
        q = np.clip(0.5 + r.normal(0, 0.05, 130), 0.01, 0.99)
        yy = (r.random(130) < 0.5).astype(float)
        hits += (B6.boot_mean(np.log(2) - B6.logloss(q, yy)) <= 0).mean() <= 0.05
    B6.B = 2000
    assert hits <= 0.05 * 200                               # noise not found


def test_holm_and_minimum():
    r = B6.holm({"a": {"p": 0.004, "n": 130}, "b": {"p": 0.03, "n": 130}, "c": {"p": 0.02, "n": 130},
                 "d": {"p": 0.001, "n": 90}})
    assert not r["d"]["pass"]                               # under 100 games never passes, and Holm stops there
    assert not r["a"]["pass"] and not r["b"]["pass"]
    r = B6.holm({"a": {"p": 0.004, "n": 130}, "b": {"p": 0.03, "n": 130}, "c": {"p": 0.012, "n": 130}})
    assert r["a"]["pass"] and r["c"]["pass"] and r["b"]["pass"]
