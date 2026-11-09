"""Hybrid rule with the simulator (docs/hybrid_sim_preregistration.md).

  python scripts/hybrid_sim.py     needs data/gamesim/g3_2022_2025.parquet (scripts/gamesim_reproduce.py) and the
                                   AusSportsBetting file in data/raw/aussportsbetting/nfl.xlsx (local only, never
                                   committed); writes data/backtests/hybrid_sim.json (counts only, no line data)

Rule: market moved 1+ point from the book open to the close -> live pick; moved 1/2 point or not at all -> the
simulator's side against the open (fair home margin > -open: home). One test on 2022-2024: net wins over the live
model on the games where the picks differ, one-sided z >= 1.645. Plain Elo and 2025 are descriptive only.
Research only: never touches the pick pipeline or the live record.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
G3 = ROOT / "data" / "gamesim" / "g3_2022_2025.parquet"
OUT = ROOT / "data" / "backtests" / "hybrid_sim.json"
TEST, DESC = (2022, 2024), (2025, 2025)
Z_PASS = 1.645


# ---------------------------------------------------------------- rule (pure functions, hand-tested)
def low_move(open_, close) -> np.ndarray:
    """1/2-point or no move from the open to the close."""
    return np.abs(np.asarray(close, float) - np.asarray(open_, float)) <= 0.5


def model_side(fair, open_, live) -> np.ndarray:
    """True = home. fair: model's fair HOME margin (positive = home wins by that much); open_: canonical home spread
    (negative = home favored), so home covers when margin > -open. Equal keeps the live pick."""
    fair, t = np.asarray(fair, float), -np.asarray(open_, float)
    out = np.asarray(live, bool).copy()
    out[fair > t] = True
    out[fair < t] = False
    return out


def hybrid(live, cand, low) -> np.ndarray:
    h = np.asarray(live, bool).copy()
    low = np.asarray(low, bool)
    h[low] = np.asarray(cand, bool)[low]
    return h


# ---------------------------------------------------------------- data and evaluation
def dataset() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Book open/close (half-point opens) joined to nflverse results and totals and to the simulator output,
    2022-2025 regular season weeks 2-18 (as engine.backtest.edge2.dataset, without the price filters)."""
    from engine.backtest import gap2022 as G, total as T
    from engine.picks.grading import is_half_point

    df, sched = T.load()
    reg = sched.filter(pl.col("game_type") == "REG")
    m = G.match(G.load_xlsx(), reg.filter(pl.col("season").is_between(2022, 2025)))
    g3 = pl.read_parquet(G3).select("game_id", "sim_fair", "elo_fair")
    d = df.join(m, on="game_id").join(reg.select("game_id", "week"), on="game_id").join(g3, on="game_id") \
        .filter(pl.col("b_open").is_not_null(), pl.col("b_close").is_not_null()) \
        .filter(pl.col("b_open").map_elements(is_half_point, return_dtype=pl.Boolean)) \
        .with_columns((pl.col("margin") > -pl.col("b_open")).alias("home_cov"))
    return d.sort("season", "week", "game_id"), df


def evaluate(d: pl.DataFrame, live: np.ndarray) -> dict:
    from engine.backtest.edge2 import compare

    y = d["home_cov"].to_numpy()
    op, cl = d["b_open"].to_numpy(), d["b_close"].to_numpy()
    low = low_move(op, cl)
    seasons = d["season"].to_numpy()
    out = {"games": int(d.height), "low_move_games": int(low.sum()),
           "live_on_low_move": {"W": int((live == y)[low].sum()), "N": int(low.sum())},
           "live_all": {"W": int((live == y).sum()), "N": int(d.height)}}
    for name, col in (("sim", "sim_fair"), ("elo", "elo_fair")):
        cand = model_side(d[col].to_numpy(), op, live)
        h = hybrid(live, cand, low)
        r = compare(h[low], live[low], y[low])
        r["pass_z_1645"] = bool(r["z"] >= Z_PASS)
        r["model_on_low_move"] = {"W": int((cand == y)[low].sum()), "N": int(low.sum())}
        r["hybrid_all"] = {"W": int((h == y).sum()), "N": int(d.height)}
        r["by_season"] = {}
        for s in sorted(set(seasons.tolist())):
            k = low & (seasons == s)
            c = compare(h[k], live[k], y[k])
            c.update(model_W=int((cand == y)[k].sum()), live_W=int((live == y)[k].sum()), low_move_games=int(k.sum()))
            r["by_season"][str(s)] = c
        out[name] = r
    return out


def main() -> None:
    from engine.backtest import edge2 as E2

    d, df = dataset()
    D = E2.dists(df, range(2022, 2026))
    live = E2.p_cover(d, D, d["b_close"].to_numpy()) > 0.5
    s = d["season"].to_numpy()
    res = {}
    for label, (lo, hi) in (("test_2022_2024", TEST), ("desc_2025", DESC)):
        k = (s >= lo) & (s <= hi)
        res[label] = evaluate(d.filter(pl.Series(k)), live[k]) if k.any() else {"games": 0}
    res["test"] = {"candidate": "sim", "z": res["test_2022_2024"]["sim"]["z"],
                   "pass": res["test_2022_2024"]["sim"]["pass_z_1645"]}
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    sys.exit(main())
