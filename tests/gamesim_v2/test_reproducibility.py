import numpy as np

from engine.gamesim_v2.plays import passing as PS
from engine.gamesim_v2.probability.random_streams import streams


def _run(seed, tables, emp, play, lineup, n=200, extra_outcome_draws=0):
    off, dfn = lineup
    eff = {k: v[0] for t in tables.values() for k, v in t.eff.items()}
    out = []
    for i in range(n):
        rs = streams(seed, i)
        if extra_outcome_draws:
            rs["outcome"].random(extra_outcome_draws)
        out.append(PS.simulate_pass_play(rs, tables, eff, emp, play, off, dfn, {"r1": 0.6, "r2": 0.4}))
    return out


def test_same_seed_same_trace(tables, emp, play, lineup):
    a, b = _run(5, tables, emp, play, lineup), _run(5, tables, emp, play, lineup)
    assert a == b


def test_different_seed_differs(tables, emp, play, lineup):
    assert _run(5, tables, emp, play, lineup) != _run(6, tables, emp, play, lineup)


def test_streams_are_independent(tables, emp, play, lineup):
    """Drawing extra numbers from the outcome stream must not change which plays get pressured by the matchup stream."""
    a = [t["p_pressure"] for t in _run(9, tables, emp, play, lineup)]
    b = [t["p_pressure"] for t in _run(9, tables, emp, play, lineup, extra_outcome_draws=7)]
    assert a == b


def test_trace_is_causally_ordered(tables, emp, play, lineup):
    for t in _run(1, tables, emp, play, lineup, n=300):
        if t["outcome"] in ("sack", "scramble"):
            assert t["target"] is None and "p_complete" not in t
        else:
            assert t["target"] in ("r1", "r2") and "p_complete" in t
        if t["outcome"] in ("incomplete", "interception"):
            assert t["yards"] == 0.0
