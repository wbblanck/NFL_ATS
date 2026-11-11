import numpy as np

from engine.gamesim_v2.matchups import protection as P


def _p(tables, play, ol=None, dl=None, qb="q", nr=4):
    lu = {"OL": ol or [f"ol{i}" for i in range(5)], "DL": dl or [f"d{i}" for i in range(4)], "LB": [f"l{i}" for i in range(3)], "QB": qb}
    z, _ = P.pressure_logit(tables["pressure"], {k: v[0] for k, v in tables["pressure"].eff.items()}, {**play, "number_of_pass_rushers": [nr]}, lu)
    return 1 / (1 + np.exp(-z))


def test_elite_tackle_lowers_pressure_and_scrub_raises_it(tables, play):
    base = _p(tables, play)
    assert _p(tables, play, ol=["elite", "ol1", "ol2", "ol3", "ol4"]) < base < _p(tables, play, ol=["scrub", "ol1", "ol2", "ol3", "ol4"])


def test_more_elite_linemen_means_more_protection(tables, play):
    one = _p(tables, play, ol=["elite", "ol1", "ol2", "ol3", "ol4"])
    two = _p(tables, play, ol=["elite", "elite", "ol2", "ol3", "ol4"])
    assert two < one < _p(tables, play)


def test_elite_rusher_raises_pressure_and_blitz_raises_pressure(tables, play):
    assert _p(tables, play, dl=["elite", "d1", "d2", "d3"]) > _p(tables, play)
    assert _p(tables, play, nr=5) > _p(tables, play, nr=4)


def test_pressure_probability_swing_is_plausible(tables, play):
    swing = _p(tables, play, ol=["scrub"] * 5) - _p(tables, play, ol=["elite"] * 5)
    assert 0 < swing < 0.5     # five replacement vs five elite linemen: large, but never most of the probability


def test_ability_uncertainty_draw_is_centered_and_reproducible(tables):
    t = tables["pressure"]
    d1 = t.draw(np.random.default_rng(3))
    d2 = t.draw(np.random.default_rng(3))
    assert d1 == d2
    big = np.mean([t.draw(np.random.default_rng(s))["OL:elite"] for s in range(400)])
    assert abs(big - (-0.25)) < 0.01
