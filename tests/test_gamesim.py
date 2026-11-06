"""Known-answer checks for the game simulator (ported from nfl-betting-model; docs/HANDOFF_game_simulator.md)."""
import json

import numpy as np
import polars as pl

from pathlib import Path

from engine.gamesim import engine as E, teams as TM

TB = E.Tables(json.loads((Path(__file__).resolve().parents[1] / "data" / "gamesim" / "gamesim_league.json").read_text()))
KS = np.full(200, 75.0)


def sim(N, off=None, hfa=0.0, seed=1):
    z = {f: np.zeros((N, 2)) for f in E.FACTORS}
    return E.simulate(TB, off or z, z, ([KS], np.zeros(N, int)), np.full(N, 0.94), np.full(N, 2019), hfa, seed=seed)


def test_reproducible_and_finishes():
    a, b = sim(500), sim(500)
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    assert 15 < (a[0] + a[1]).mean() / 2 < 30


def test_planted_offense_wins():
    z = {f: np.zeros((4000, 2)) for f in E.FACTORS}
    z["ypc"][:, 0] = np.log(1.3)
    z["comp"][:, 0] = 0.5
    h, a = sim(4000, off=z, seed=3)
    assert (h - a).mean() > 4


def test_home_field_raises_margin():
    h0, a0 = sim(20000, seed=4)
    h1, a1 = sim(20000, hfa=0.05, seed=4)
    assert (h1 - a1).mean() > (h0 - a0).mean() + 0.8


def _gs(n_weeks):
    rows = []
    for w in range(1, n_weeks + 1):
        for t, o in (("A", "B"), ("B", "A")):
            rows.append({"season": 2020, "week": w, "game_id": f"g{w}", "team": t, "opp": o, "db": 40, "sack": 2 + w % 3,
                         "scr": 1, "int": 1, "comp": 25, "att": 37, "comp_y": 280, "run": 25, "run_y": 110, "nsdb": 38,
                         "natt": 36, "p_obs": 30, "p_exp": 28.0, "p_n": 55})
    return pl.DataFrame(rows)


def test_factors_have_no_lookahead():
    lg = {"sack": 0.06, "sack_n": 38, "scr": 0.04, "scr_n": 36, "int": 0.023, "int_n": 35, "comp": 0.65, "comp_n": 34,
          "ypc": 11.3, "ypc_n": 22, "ypr": 4.4, "ypr_n": 25}
    full = TM.factors(_gs(10), lg, 8, 8, 0.7).filter(pl.col("week") == 6).sort("team")
    cut = TM.factors(_gs(6), lg, 8, 8, 0.7).filter(pl.col("week") == 6).sort("team")
    for c in full.columns:
        if c[0] in "od":
            assert np.allclose(full[c].to_numpy(), cut[c].to_numpy())
