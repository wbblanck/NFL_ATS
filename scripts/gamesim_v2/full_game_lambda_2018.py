"""Amendment 1: choose one ridge strength per play type by walk-forward play-level squared error on 2018 only (training from 2016).
Usage: python scripts/gamesim_v2/full_game_lambda_2018.py"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, polars as pl
sys.path.insert(0, str(Path(__file__).parent))
import full_game_ratings as R
from engine.gamesim_v2.players import abilities_full as F
from engine.gamesim_v2.validation import play_validation_v2 as V2

GRID = [100, 300, 1000, 3000, 10000, 30000]
pos = {(s, g): p for s, g, p in pl.read_parquet(R.FEAT / "position_lookup.parquet").filter(pl.col("season") <= 2018).iter_rows()}
out = {"grid": GRID}
for kind, d in R.tables().items():
    d = d.filter(pl.col("season") <= 2018)
    y = d["epa"].to_numpy().astype(float)
    Dp, _ = F.build_design_full(d, pos, True); Dc, _ = F.build_design_full(d, pos, False)
    designs = {"ctx": Dc}; lams = {"ctx": Dc.lam}
    for L in GRID:
        designs[f"lam{L}"] = Dp
        lams[f"lam{L}"] = np.where(Dp.group == "ctx", 1e-3, float(L))
    pred, _ = V2.walk_forward_v2(d, kind, y, designs, lams, "gauss", R.HL, [2018], R.START, {}, record=None)
    mse = {k: float(((pred["y"] - pred[k]) ** 2).mean()) for k in designs}
    best = min(GRID, key=lambda L: mse[f"lam{L}"])
    out[kind] = {"n_plays_2018": int(pred.height), "mse": mse, "chosen": best,
                 "chosen_minus_ctx": V2.compare_sq(pred, "ctx", f"lam{best}")}
    print(kind, json.dumps(out[kind]), flush=True)
(R.MAN / "full_game_lambda_2018.json").write_text(json.dumps(out, indent=1))
