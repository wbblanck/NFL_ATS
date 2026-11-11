import numpy as np

from engine.gamesim_v2.matchups import coverage as C


def _p(tables, play, target="r1", qb="q", db=None, pressure=False, air=10.0):
    eff = {k: v[0] for k, v in tables["completion"].eff.items()}
    d = {"DB": db or [f"b{i}" for i in range(4)], "LB": [f"l{i}" for i in range(3)]}
    z, _ = C.completion_logit(tables["completion"], eff, {**play, "air_yards": [air], "was_pressure": [pressure]}, target, qb, d)
    return 1 / (1 + np.exp(-z))


def test_better_receiver_qb_and_worse_coverage_all_raise_completion(tables, play):
    base = _p(tables, play)
    assert _p(tables, play, target="r2") < base < _p(tables, play, target="r1") or _p(tables, play, target="r2") < _p(tables, play, target="r1")
    assert _p(tables, play, qb="qelite") > _p(tables, play)
    assert _p(tables, play, db=["elite", "b1", "b2", "b3"]) < base


def test_pressure_lowers_completion(tables, play):
    assert _p(tables, play, pressure=True) < _p(tables, play, pressure=False)
