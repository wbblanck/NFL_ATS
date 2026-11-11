import numpy as np
import polars as pl
import pytest

from engine.gamesim_v2.matchups.protection import AbilityTable
from engine.gamesim_v2.plays.passing import Empirics


def _table(kind):
    ctx = {"nr=4": 0.0, "nr=5": 0.2, "air1": 0.3, "air2": 0.5, "air3": 0.1, "pressure": -0.9}
    eff = {}
    if kind == "pressure":
        eff = {f"OL:ol{i}": (0.0, 0.05) for i in range(8)} | {"OL:elite": (-0.25, 0.05), "OL:scrub": (0.25, 0.05),
               "DL:avg": (0.0, 0.05), "DL:elite": (0.2, 0.05), "QB:q": (0.0, 0.05)} | {f"DL:d{i}": (0.0, 0.05) for i in range(4)} | {f"LB:l{i}": (0.0, 0.05) for i in range(3)}
        return AbilityTable(-1.0, ctx, eff)
    eff = {"R:r1": (0.1, 0.05), "R:r2": (-0.1, 0.05), "QB:q": (0.0, 0.05), "QB:qelite": (0.2, 0.05), "DB:elite": (-0.2, 0.05)} | {f"DB:b{i}": (0.0, 0.05) for i in range(4)} | {f"LB:l{i}": (0.0, 0.05) for i in range(3)}
    return AbilityTable(0.6, ctx, eff)


@pytest.fixture
def tables():
    return {"pressure": _table("pressure"), "completion": _table("completion")}


@pytest.fixture
def emp():
    rng = np.random.default_rng(0)
    return Empirics(nr=np.array([4, 4, 4, 5, 5, 6]), ttt={False: np.full(50, 2.5), True: np.full(50, 2.0)},
                    sack_given={(f, n): (0.2 if f else 0.001) for f in (False, True) for n in range(2, 8)},
                    scramble_given={(f, n): (0.1 if f else 0.02) for f in (False, True) for n in range(2, 8)},
                    air={False: rng.integers(-2, 25, 200).astype(float), True: rng.integers(-2, 15, 200).astype(float)},
                    int_rate={(f, b): 0.04 for f in (False, True) for b in range(6)},
                    yards_complete={b: np.array([5.0, 8.0, 12.0]) for b in range(6)}, yards_sack=np.array([-6.0, -7.0]),
                    yards_scramble=np.array([4.0, 6.0]))


@pytest.fixture
def play():
    return {"down": [1], "ydstogo": [10], "shotgun": [1], "no_huddle": [0]}


@pytest.fixture
def lineup():
    off = {"QB": ["q"], "OL": [f"ol{i}" for i in range(5)]}
    dfn = {"DL": [f"d{i}" for i in range(4)], "LB": [f"l{i}" for i in range(3)], "DB": [f"b{i}" for i in range(4)]}
    return off, dfn
