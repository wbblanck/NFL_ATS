import numpy as np
import polars as pl
import pytest

from engine.models import projection_v5 as S5


def _toy_model():
    rng = np.random.default_rng(0)
    n = 20000
    cell = rng.integers(0, S5.N_CELLS, n)
    lt, lf = np.log(rng.uniform(1.5, 3.5, n)), np.log(rng.uniform(1.2, 2.2, n))
    # trailing-late cells score TDs more often than leading-late
    base_td = 0.18 * np.exp(lt - np.log(2.4))
    late_trail = np.isin(cell, [0 * 3 + 1, 1 * 3 + 1])
    late_lead = np.isin(cell, [3 * 3 + 1, 4 * 3 + 1])
    p_td = np.clip(base_td * np.where(late_trail, 1.3, np.where(late_lead, 0.6, 1.0)), 0, 0.6)
    u = rng.random(n)
    out = np.where(u < p_td, "TD", np.where(u < p_td + 0.14, "FG", np.where(u < p_td + 0.16, "OPP_TD", "NONE")))
    M = S5.DriveModel.fit(lt, lf, cell, out)
    dur = rng.gamma(4, 40, n)
    pool = S5.DurationPool.fit(list(out), cell, dur)
    return M, pool


def test_state_cells():
    assert S5.bucket_index(np.array([-12, -3, 0, 5, 14])).tolist() == [0, 1, 2, 3, 4]
    assert S5.period_index(np.array([1, 1, 2, 2]), np.array([1500, 100, 800, 1000])).tolist() == [0, 2, 1, 0]


def test_drive_model_recovers_game_script_and_strength():
    M, _ = _toy_model()
    assert M.coef["TD"][1] == pytest.approx(1.0, abs=0.15)          # TD odds scale with expected TDs
    tab = M.cell_table(np.log(2.4), np.log(1.7))
    assert tab[0 * 3 + 1, 0] > tab[4 * 3 + 1, 0]                     # trailing 9+ late > leading 9+ late
    assert np.allclose(tab.sum(1), 1.0)


def test_simulation_is_a_valid_distribution_and_reacts_to_strength():
    M, pool = _toy_model()
    even = S5.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.4, "fg": 1.7}, 0.93, 0.03, M, pool, sims=4000, seed=1)
    strong = S5.simulate({"td": 3.4, "fg": 1.7}, {"td": 1.8, "fg": 1.7}, 0.93, 0.03, M, pool, sims=4000, seed=1)
    pm = S5.margin_pmf(even)
    assert pm.sum() == pytest.approx(1.0) and (pm >= 0).all()
    assert abs(even.margin.mean()) < 1.0
    assert strong.margin.mean() > even.margin.mean() + 4
    assert (strong.counts[:, 0].mean() > strong.counts[:, 2].mean())
    proj = S5.SimProjection(strong)
    assert 0 < proj.p_home_cover(-3.5) < 1


def test_overtime_leaves_few_ties():
    M, pool = _toy_model()
    r = S5.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.4, "fg": 1.7}, 0.93, 0.03, M, pool, sims=4000, seed=2)
    # toy rates: ~6% of games tied after regulation x ~21% with no OT score (0.68^4) = ~1.3% ties
    tied_reg = (r.margin == 0).mean()
    assert tied_reg < 0.02


def test_common_random_numbers_are_reproducible():
    M, pool = _toy_model()
    a = S5.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.1, "fg": 1.5}, 0.93, 0.03, M, pool, sims=2000, seed=5)
    b = S5.simulate({"td": 2.4, "fg": 1.7}, {"td": 2.1, "fg": 1.5}, 0.93, 0.03, M, pool, sims=2000, seed=5)
    assert np.array_equal(a.margin, b.margin)


def test_drive_training_table_durations_start_to_start():
    rows = pl.DataFrame({"game_id": ["g"] * 3, "season": [2020] * 3, "posteam": ["SEA", "SF", "SEA"],
                         "defteam": ["SF", "SEA", "SF"], "fixed_drive": [1, 2, 3], "diff": [0.0, -7.0, 7.0],
                         "hs0": [1800.0, 1600.0, 900.0], "hs1": [1650.0, 950.0, 30.0],
                         "half": ["Half1"] * 3, "qtr": [1, 1, 2], "res": ["Touchdown", "Punt", "Field goal"]})
    mu = pl.DataFrame({"game_id": ["g", "g"], "team": ["SEA", "SF"], "mu_td": [2.4, 2.1], "mu_fg": [1.7, 1.6]})
    t = S5.drive_training_table(rows, mu).sort("fixed_drive")
    assert t["dur"].to_list() == [200.0, 700.0, 900.0]       # last drive of the half runs to 0
    assert t["outcome"].to_list() == ["TD", "NONE", "FG"]
