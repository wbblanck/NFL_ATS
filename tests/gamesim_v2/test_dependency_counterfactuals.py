"""Spec 14.2: an elite tackle should lower pressure, and any change in completion must come through pressure, not a fixed bonus."""
import numpy as np

from engine.gamesim_v2.plays import passing as PS
from engine.gamesim_v2.probability.random_streams import streams


def _rates(tables, emp, play, lineup, ol, n=6000, seed=11):
    off, dfn = lineup
    off = {**off, "OL": ol}
    eff = {k: v[0] for t in tables.values() for k, v in t.eff.items()}
    tr = [PS.simulate_pass_play(streams(seed, i), tables, eff, emp, play, off, dfn, {"r1": 0.5, "r2": 0.5}) for i in range(n)]
    pres = np.mean([t["pressure"] for t in tr])
    thr = [t for t in tr if t["decision"] == "throw"]
    comp = np.mean([t["outcome"] == "complete" for t in thr])
    comp_np = np.mean([t["outcome"] == "complete" for t in thr if not t["pressure"]])
    comp_p = np.mean([t["outcome"] == "complete" for t in thr if t["pressure"]])
    return pres, comp, comp_np, comp_p


def test_elite_line_reduces_pressure_and_changes_completion_only_through_pressure(tables, emp, play, lineup):
    avg = [f"ol{i}" for i in range(5)]
    elite = ["elite"] * 5
    pa, ca, cna, cpa = _rates(tables, emp, play, lineup, avg)
    pe, ce, cne, cpe = _rates(tables, emp, play, lineup, elite)
    assert pe < pa                                   # protection helps
    # completion given the pressure state is unchanged by the line (no hidden direct effect), within Monte Carlo error
    assert abs(cne - cna) < 0.03 and abs(cpe - cpa) < 0.06
    assert ce >= ca - 0.01                           # overall completion can only rise via fewer pressured throws
