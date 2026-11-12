"""Audit: does keeping the 2,018 no-target attempts (the population used by the frozen v1 completion results) change the v1 player-vs-context and
player-vs-team conclusions? Development seasons 2019-2020 only, walk-forward, same settings as the frozen config. Usage: python scripts/gamesim_v2/null_target_sensitivity.py"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, polars as pl
sys.path.insert(0, str(Path(__file__).parent))
import estimation_v2 as E
from engine.gamesim_v2.players import abilities_v2 as B
from engine.gamesim_v2.validation import play_validation as V, play_validation_v2 as V2

ident = pl.read_parquet(E.ROOT / "data/gamesim_v2/processed/player_identity.parquet")
meta = B.player_meta(ident)
out = {}
for label, keep_null in (("with_null_target_plays", True), ("clean_target_only", False)):
    d = pl.read_parquet(E.FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season") <= E.LAST)
    pos = {(s, g): p for s, g, p in pl.read_parquet(E.FEAT / "position_lookup.parquet").filter(pl.col("season") <= E.LAST).iter_rows()}
    d = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
    if not keep_null:
        d = d.filter(pl.col("target").is_not_null())
    y = d["complete"].to_numpy().astype(float)
    designs = {"ctx": B.build_design_v2(d, pos, "completion", meta, prior=False, player_effects=False),
               "team": B.build_design_v2(d, pos, "completion", meta, prior=False, player_effects=False, team_effects=True),
               "player": B.build_design_v2(d, pos, "completion", meta, prior=False)}
    lams = {k: B.lam_vector(D, E.LAM) for k, D in designs.items()}
    pred, _ = V2.walk_forward_v2(d, "completion", y, designs, lams, "logit", 730.0, E.EVAL, 2016, meta, record="player")
    out[label] = {"n_plays_eval": int(pred.height), "logloss": {k: float(V.logloss(pred["y"].to_numpy(), pred[k].to_numpy()).mean()) for k in designs},
                  "player_minus_ctx": V.compare(pred, "ctx", "player"), "player_minus_team": V.compare(pred, "team", "player")}
    print(label, json.dumps(out[label]), flush=True)
(E.MAN / "null_target_sensitivity.json").write_text(json.dumps(out, indent=1, default=float))
