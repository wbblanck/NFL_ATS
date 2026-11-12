"""Development decomposition of the receiver draft-round effect in the completion model (estimation v2). Descriptive, 2016-2020, not confirmatory.
Usage: python scripts/gamesim_v2/receiver_decomposition.py"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, polars as pl, scipy.sparse as sp
sys.path.insert(0, str(Path(__file__).parent))
import estimation_v2 as E
from engine.gamesim_v2.players import abilities as A, abilities_v2 as B

ident = pl.read_parquet(E.ROOT / "data/gamesim_v2/processed/player_identity.parquet")
meta = B.player_meta(ident)
d, pos, y = E.population("completion")
n = d.height
season, tgt, qb = d["season"].to_numpy(), d["target"].to_list(), d["qb"].to_list()
rnd = np.array([meta.get(u, (0, None))[0] for u in tgt])
drafted = (rnd > 0).astype(float)
rd = {f"dr{k}": np.array([(r == k) if k < 4 else (4 <= r <= 7) for r in rnd], float) for k in (1, 2, 3, 4)}
tpos = np.array([pos.get((s, u), "NA") for s, u in zip(season, tgt)])
ctx, ctx_names = A.completion_context(d)
airy = d["air_yards"].to_numpy().astype(float)
res = {"n": int(n), "raw_completion": {}, "share": {}}
res["share"]["drafted"] = float(drafted.mean())
for k, v in (("drafted", drafted == 1), ("undrafted", drafted == 0)):
    res["raw_completion"][k] = float(y[v].mean())
res["raw_completion_by_position"] = {p: {"n": int((tpos == p).sum()), "drafted_share": float(drafted[tpos == p].mean()),
                                         "cr_drafted": float(y[(tpos == p) & (drafted == 1)].mean()), "cr_undrafted": float(y[(tpos == p) & (drafted == 0)].mean()),
                                         "mean_air_drafted": float(np.nanmean(airy[(tpos == p) & (drafted == 1)])), "mean_air_undrafted": float(np.nanmean(airy[(tpos == p) & (drafted == 0)]))}
                                     for p in ("WR", "TE", "RB") if (tpos == p).sum() > 200}
def fit(cols, names, lam=1e-3):
    X = sp.csr_matrix(np.column_stack(cols))
    b0, b = A.fit_logit(X, y, np.ones(n), np.full(X.shape[1], lam))
    return dict(zip(names, map(float, b)))
dr_cols, dr_names = [drafted], ["drafted"]
steps = {}
steps["1 drafted only"] = fit(dr_cols, dr_names)["drafted"]
steps["2 + air yards, pressure, down, distance, shotgun"] = fit(dr_cols + [ctx], dr_names + ctx_names)["drafted"]
pc = [(tpos == p).astype(float) for p in ("TE", "RB", "WR")][:2] + [(~np.isin(tpos, ["TE", "RB", "WR"])).astype(float)]
steps["3 + target position (TE, RB, other vs WR)"] = fit(dr_cols + [ctx] + pc, dr_names + ctx_names + ["TE", "RB", "othpos"])["drafted"]
qcount = {}
for q in qb: qcount[q] = qcount.get(q, 0) + 1
big = sorted(u for u, c in qcount.items() if c >= 300 and u)
qcols = [np.array([q == u for q in qb], float) for u in big]
steps["4 + quarterback fixed effects (QBs with 300+ attempts)"] = fit(dr_cols + [ctx] + pc + qcols, dr_names + ctx_names + ["TE", "RB", "othpos"] + [f"qb:{u}" for u in big])["drafted"]
steps["5 + offense team and season dummies"] = None
teams = sorted(set(d["posteam"].to_list())); tcols = [(np.array(d["posteam"].to_list()) == t).astype(float) for t in teams[1:]]
scols = [(season == s).astype(float) for s in sorted(set(season.tolist()))[1:]]
steps["5 + offense team and season dummies"] = fit(dr_cols + [ctx] + pc + qcols + tcols + scols, dr_names + ctx_names + ["TE", "RB", "othpos"] + [f"qb:{u}" for u in big] + [f"t:{t}" for t in teams[1:]] + [f"s:{s}" for s in range(len(scols))])["drafted"]
res["drafted_coefficient_logit_by_step"] = steps
# drafted effect within WR only, by season (stability) with contexts
for label, m in (("WR only", tpos == "WR"), ("TE only", tpos == "TE"), ("RB only", tpos == "RB")):
    X = sp.csr_matrix(np.column_stack([drafted[m], ctx[m]]))
    b0, b = A.fit_logit(X, y[m], np.ones(int(m.sum())), np.full(X.shape[1], 1e-3))
    res.setdefault("drafted_within_position_with_context", {})[label] = {"n": int(m.sum()), "coef": float(b[0])}
for s in sorted(set(season.tolist())):
    m = season == s
    X = sp.csr_matrix(np.column_stack([drafted[m], ctx[m]]))
    b0, b = A.fit_logit(X, y[m], np.ones(int(m.sum())), np.full(X.shape[1], 1e-3))
    res.setdefault("drafted_with_context_by_season", {})[str(s)] = float(b[0])
Path(E.MAN / "receiver_decomposition.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
