import numpy as np
import pytest

from engine.models import projection as P
from engine.models import projection_v41 as L


def test_reduces_to_independent_poisson_v1():
    a = L.project((2.4, 1.7, 2.1, 1.5), 0.92, 0.03, L.Params())
    b = P.Projection(P.points_pmf(2.4, 1.7, 0.92, 0.03), P.points_pmf(2.1, 1.5, 0.92, 0.03))
    assert np.abs(a.margin_pmf - b.margin_pmf).max() < 1e-6


def test_latent_factors_preserve_expected_scores():
    p = L.Params(0.25, -0.2, 0.3, 0.35, 0.15, 0.1, n_td=12, n_fg=None)
    a = L.project((2.4, 1.7, 2.1, 1.5), 0.92, 0.03, p)
    b = P.Projection(P.points_pmf(2.4, 1.7, 0.92, 0.03), P.points_pmf(2.1, 1.5, 0.92, 0.03))
    assert a.mean_scores() == pytest.approx(b.mean_scores(), abs=0.02)
    assert a.margin_pmf.sum() == pytest.approx(1.0) and (a.margin_pmf >= 0).all()
    assert 0 < a.p_home_cover(-2.5) < 1


def test_dominance_sign_flip_is_the_same_model():
    mu = np.array([[2.4, 1.7, 2.1, 1.5]] * 200)
    p = L.Params(0.2, -0.2, 0.3, 0.3, 0.15, 0.1, n_td=12, n_fg=None)
    y = L.simulate(p, mu, 1, 3)[0]
    q = L.Params(0.2, -0.2, 0.3, 0.3, -0.15, -0.1, n_td=12, n_fg=None)
    assert L.loglik(p, mu, y)[0] == pytest.approx(L.loglik(q, mu, y)[0])


def test_true_parameters_beat_independence_on_simulated_data():
    rng = np.random.default_rng(1)
    mu = np.column_stack([rng.uniform(1.6, 3.3, 1500), rng.uniform(1.2, 2.2, 1500),
                          rng.uniform(1.6, 3.3, 1500), rng.uniform(1.2, 2.2, 1500)])
    p = L.Params(0.3, -0.25, 0.3, 0.35, 0.15, 0.1, n_td=12, n_fg=None)
    y = L.simulate(p, mu, 1, 2)[0]
    assert L.loglik(p, mu, y)[0] > L.loglik(L.Params(n_td=None, n_fg=None), mu, y)[0]


def test_binomial_rejects_counts_above_trials():
    lp, _ = L._logpmf(np.array([13.0]), np.array([2.0]), 12)
    assert lp[0] == -np.inf
