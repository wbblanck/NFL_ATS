"""Full-game development test, stage 1: walk-forward on-field EPA ratings for dropbacks and designed runs (2019-2021 recorded, training from
2016). Seasons after 2021 are never loaded. Usage: python scripts/gamesim_v2/full_game_ratings.py"""
from __future__ import annotations
import json, os, time
from pathlib import Path
import numpy as np
import polars as pl
from engine.gamesim_v2.players import abilities_full as F
from engine.gamesim_v2.validation import play_validation_v2 as V2

ROOT = Path(__file__).resolve().parents[2]
FEAT, MAN = ROOT / "data/gamesim_v2/features", ROOT / "data/gamesim_v2/manifests"
LAST, EVAL, START, HL = 2021, [2019, 2020, 2021], 2016, 730.0
# Amendment 1: ridge chosen on 2018 (3,000 for both play types). G2_FULL_LAM=100 reproduces the original preregistered setting.
RIDGE = float(os.environ.get("G2_FULL_LAM", "3000"))
SUFFIX = "" if RIDGE == 3000 else f"_lam{int(RIDGE)}"


def tables():
    db = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season") <= LAST, pl.col("epa").is_not_null())
    ru = pl.read_parquet(FEAT / "runs.parquet").filter(pl.col("has_part"), pl.col("season") <= LAST, pl.col("epa").is_not_null())
    return {"pass": db, "run": ru}


def main():
    pos = {(s, g): p for s, g, p in pl.read_parquet(FEAT / "position_lookup.parquet").filter(pl.col("season") <= LAST).iter_rows()}
    res = {"settings": {"ridge": RIDGE, "half_life_days": HL, "train_from": START, "eval": EVAL}}
    T = tables()
    for kind, d in T.items():
        early = d.filter(pl.col("season") <= 2018).group_by("game_id", "posteam").len()
        res.setdefault("plays_per_team_game_2016_2018", {})[kind] = float(early["len"].mean())
        res.setdefault("plays", {})[kind] = {str(s): int(n) for s, n in d.group_by("season").len().sort("season").iter_rows()}
    for kind, d in T.items():
        t0 = time.time()
        y = d["epa"].to_numpy().astype(float)
        Dp, miss = F.build_design_full(d, pos, True)
        Dc, _ = F.build_design_full(d, pos, False)
        designs, lams = {"ctx": Dc, "player": Dp}, {"ctx": Dc.lam, "player": np.where(Dp.group == "ctx", 1e-3, RIDGE)}
        pred, ab = V2.walk_forward_v2(d, kind, y, designs, lams, "gauss", HL, EVAL, START, {}, record="player")
        ab.write_parquet(FEAT / f"abilities_full_{kind}{SUFFIX}.parquet")
        pred.write_parquet(FEAT / f"pred_full_{kind}{SUFFIX}.parquet")
        r = {"design_missing_position": miss, "n_columns_player": len(Dp.names), "n_eval_plays": int(pred.height),
             "mse": {k: float(((pred["y"] - pred[k]) ** 2).mean()) for k in designs},
             "player_minus_ctx": V2.compare_sq(pred, "ctx", "player")}
        for s in EVAL:
            r[f"player_minus_ctx_{s}"] = V2.compare_sq(pred.filter(pl.col("season") == s), "ctx", "player")
        r["minutes"] = round((time.time() - t0) / 60, 1)
        res[kind] = r
        print(kind, json.dumps(r), flush=True)
        (MAN / f"full_game_ratings{SUFFIX}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
