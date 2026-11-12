"""Audit: held-out completion log loss from each group's prior columns, on the clean population and on the leaked one (all attempts, including the 2,018
with no recorded target). Fit on 2016-2018, test on 2019-2020, same ridge settings, no decay. Usage: python scripts/gamesim_v2/prior_ablation.py"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, polars as pl
sys.path.insert(0, str(Path(__file__).parent))
import estimation_v2 as E
from engine.gamesim_v2.players import abilities as A, abilities_v2 as B

ident = pl.read_parquet(E.ROOT / "data/gamesim_v2/processed/player_identity.parquet")
meta = B.player_meta(ident)
res = {}
for label, keep_null in (("clean_target_only", False), ("with_null_target_plays", True)):
    d = pl.read_parquet(E.FEAT / "dropbacks.parquet").filter(pl.col("has_part"), pl.col("season") <= E.LAST)
    pos = {(s, g): p for s, g, p in pl.read_parquet(E.FEAT / "position_lookup.parquet").filter(pl.col("season") <= E.LAST).iter_rows()}
    d = d.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
    if not keep_null:
        d = d.filter(pl.col("target").is_not_null())
    y = d["complete"].to_numpy().astype(float)
    D = B.build_design_v2(d, pos, "completion", meta, prior=True)
    s = d["season"].to_numpy(); tr, te = np.where(s <= 2018)[0], np.where(s >= 2019)[0]
    names = np.array(D.names)
    def run(drop):
        keep = np.ones(len(names), bool)
        for g in drop:
            keep &= ~np.array([n.startswith(f"cov|{g}|") for n in names])
        X = D.X[:, np.where(keep)[0]]; lam = B.lam_vector(D, E.LAM)[keep]
        b0, beta = A.fit_logit(X[tr], y[tr], np.ones(len(tr)), lam)
        p = 1 / (1 + np.exp(-(b0 + X[te] @ beta)))
        return float(-(y[te] * np.log(p) + (1 - y[te]) * np.log(1 - p)).mean()), dict(zip(names[keep], map(float, beta)))
    allg = ["R", "QB", "DB", "LB"]
    base, _ = run(allg); full, bf = run([])
    r = {"n_train": int(len(tr)), "n_test": int(len(te)), "logloss_no_prior_columns": base, "logloss_all_prior_columns": full, "change_by_group_alone": {}}
    for g in allg:
        r["change_by_group_alone"][g] = run([x for x in allg if x != g])[0] - base
    r["coefficients"] = {k: v for k, v in bf.items() if k.startswith("cov|")}
    res[label] = r
    print(label, json.dumps({k: v for k, v in r.items() if k != "coefficients"}), flush=True)
(E.MAN / "prior_ablation.json").write_text(json.dumps(res, indent=1))
