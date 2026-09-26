import numpy as np

from engine.models import projection_v51 as S


def _toy():
    rng = np.random.default_rng(0)
    n = 30000
    half = rng.integers(1, 3, n)
    clock = rng.uniform(1, 1800, n)
    diff = rng.integers(-20, 21, n)
    cell = S.cell_index(diff, half, clock)
    lt, lf = np.log(rng.uniform(1.5, 3.5, n)), np.log(rng.uniform(1.2, 2.2, n))
    u = rng.random(n)
    out = np.where(u < 0.21, "TD", np.where(u < 0.35, "FG", np.where(u < 0.365, "OPP_TD", "NONE")))
    dur = np.minimum(rng.gamma(4, 40, n), clock)
    M = S.DriveModel.fit(lt, lf, cell, out)
    pool = S.DurationPool.fit(list(out), cell, dur, clock, half)
    return M, pool


def test_state_cells_separate_first_half_and_fourth_quarter_endings():
    assert S.period_index(np.array([1, 2, 2, 2, 2]), np.array([100, 100, 250, 600, 1200])).tolist() == [1, 4, 3, 2, 0]
    assert S.bucket_index(np.array([-20, -10, -5, -2, 0, 2, 5, 10, 20])).tolist() == list(range(9))


def test_both_halves_are_played():
    """Regression: v5.1 once switched simulations to half 2 before checking which had finished half 2."""
    M, pool = _toy()
    r = S.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.4, "fg": 1.7}, 0.93, 0.03, M, pool, sims=2000, seed=1)
    per_half = r.drives_by_half.mean(0)
    assert per_half[0] > 5 and per_half[1] > 5


def test_durations_never_exceed_the_clock():
    M, pool = _toy()
    clock = np.array([30.0, 90.0, 600.0, 1700.0])
    d = pool.draw(np.zeros(4, int), np.zeros(4, int), np.full(4, 0.99), clock, np.array([1, 2, 2, 1]))
    assert (d <= clock).all() and (d >= 0).all()


def test_environment_factor_raises_cross_team_td_correlation():
    M, pool = _toy()
    base = S.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.4, "fg": 1.7}, 0.93, 0.03, M, pool, env=(0.0, 0.0), sims=6000, seed=3)
    env = S.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.4, "fg": 1.7}, 0.93, 0.03, M, pool, env=(0.5, -0.5), sims=6000, seed=3)
    c0 = np.corrcoef(base.counts[:, 0], base.counts[:, 2])[0, 1]
    c1 = np.corrcoef(env.counts[:, 0], env.counts[:, 2])[0, 1]
    assert c1 > c0 + 0.05
