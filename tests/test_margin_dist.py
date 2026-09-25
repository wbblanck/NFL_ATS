import numpy as np
import pytest

from engine.models.margin_dist import MarginDist, log_loss
from engine.picks.grading import InvalidLeagueLine


def data(n=5000, seed=0):
    rng = np.random.default_rng(seed)
    c = rng.choice(np.arange(-14, 14.5, 0.5), n)
    m = np.round(-c + rng.normal(0, 13, n))
    return c, m


@pytest.mark.parametrize("kind", ["normal", "shifted", "kernel", "kernel_sym"])
def test_cover_probs_sum_to_one_and_monotone(kind):
    c, m = data()
    md = MarginDist(kind=kind, h=1.5).fit(c, m)
    ph, pa = md.cover_probs(-3.0, -3.5)
    assert abs(ph + pa - 1) < 1e-12
    # a bigger number for the favorite is harder to cover
    lines = [-1.5, -3.5, -6.5, -9.5]
    ps = [md.cover_probs(-3.0, s)[0] for s in lines]
    assert all(a >= b for a, b in zip(ps, ps[1:]))


def test_whole_number_line_rejected():
    c, m = data()
    with pytest.raises(InvalidLeagueLine):
        MarginDist(kind="shifted").fit(c, m).cover_probs(-3.0, -3.0)


def test_sensitivity_half_points_only():
    c, m = data()
    t = MarginDist(kind="shifted").fit(c, m).sensitivity(-3.0, -3.5, span=3)
    assert [r["line"] for r in t] == [-6.5, -5.5, -4.5, -3.5, -2.5, -1.5, -0.5]
    assert all(abs(r["p_home"] + r["p_away"] - 1) < 1e-12 for r in t)


def test_key_number_mass_kept_by_kernel():
    # margins concentrated on 3: P(cover -2.5) - P(cover -3.5) should be large
    rng = np.random.default_rng(2)
    c = np.full(4000, -3.0)
    m = rng.choice([3, 3, 3, 7, -3, 10, 0, 14, -7, 1], 4000)
    md = MarginDist(kind="kernel", h=1.0).fit(c, m)
    jump = md.cover_probs(-3.0, -2.5)[0] - md.cover_probs(-3.0, -3.5)[0]
    assert abs(jump - np.mean(m == 3)) < 1e-9


def test_log_loss_coinflip():
    assert abs(log_loss(np.full(10, 0.5), np.array([0, 1] * 5)) - np.log(2)) < 1e-12
