"""Hand cases for scripts/hybrid_sim.py (docs/hybrid_sim_preregistration.md)."""
import importlib.util
from pathlib import Path

import numpy as np

from engine.backtest.edge2 import compare

_spec = importlib.util.spec_from_file_location("hybrid_sim", Path(__file__).resolve().parents[1] / "scripts" / "hybrid_sim.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)


def test_move_split():
    assert H.low_move([-3.5, -3.5, -3.5, -3.5, 2.5], [-3.5, -3.0, -4.0, -4.5, 1.5]).tolist() == [True, True, True, False, False]


def test_model_side_both_signs():
    live = np.array([False, True, False, True])
    # home -3.5: home covers when margin > 3.5
    # away favored +2.5: home covers when margin > -2.5
    fair = np.array([4.0, 3.0, -2.0, -3.0])
    op = np.array([-3.5, -3.5, 2.5, 2.5])
    assert H.model_side(fair, op, live).tolist() == [True, False, True, False]


def test_tie_keeps_live():
    assert H.model_side([3.5, 3.5], [-3.5, -3.5], [True, False]).tolist() == [True, False]


def test_hybrid_only_on_low_move():
    live = np.array([True, True, False, False])
    cand = np.array([False, False, True, True])
    low = np.array([True, False, True, False])
    assert H.hybrid(live, cand, low).tolist() == [False, True, True, False]


def test_net_and_z_planted():
    # 100 games differ: rule right on 60, live right on 40 -> net +20, z = 2.0; 50 equal games add nothing
    y = np.ones(150, bool)
    rule = np.r_[np.ones(60, bool), np.zeros(40, bool), np.ones(50, bool)]
    base = np.r_[np.zeros(60, bool), np.ones(40, bool), np.ones(50, bool)]
    r = compare(rule, base, y)
    assert (r["differ"], r["rule_only"], r["base_only"]) == (100, 60, 40)
    assert abs(r["z"] - 2.0) < 1e-12 and r["z"] >= H.Z_PASS
