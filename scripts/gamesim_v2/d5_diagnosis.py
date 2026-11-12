"""Development diagnosis of the D5 standard error anomaly (estimation v2 EPA table, 2019-2020 team-games). Not confirmatory.
Usage: G2_PRES=abilities_v2_pressure G2_COMP=abilities_v2_epa python scripts/gamesim_v2/d5_diagnosis.py"""
from __future__ import annotations
import json, os, sys
from pathlib import Path
import numpy as np
import polars as pl
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("G2_PRES", "abilities_v2_pressure"); os.environ.setdefault("G2_COMP", "abilities_v2_epa")
import lineup_dev_2019_2020 as L

d, g = L.load()
pos = {(s, p): grp for s, p, grp in pl.read_parquet(L.FEAT / "position_lookup.parquet").filter(pl.col("season") <= L.LAST).iter_rows()}
T, _ = L.components(g, d, pos)
T = T.filter(pl.col("epa").is_not_null() & pl.col("comp").is_not_null())
ii = T.select("game_id", "posteam").join(g.with_row_index("i").select("game_id", "posteam", "i"), on=["game_id", "posteam"])["i"].to_numpy()
s_arr, wk = T["season"].to_numpy(), T["week"].to_numpy()
y, w = T["epa"].to_numpy(), T["n_db"].to_numpy().astype(float)
m19 = s_arr == 2019
best = None
for hl in (3, 6, 12, 24):
    for k in (2, 4, 8):
        fo, fd = L.form(g, "epa", hl, k)
        X = np.column_stack([np.ones(len(ii)), fo[ii], fd[ii]])
        e = L.loo_week_mse(X[m19], y[m19], w[m19], wk[m19])
        mse = float((w[m19] * e).sum() / w[m19].sum())
        if best is None or mse < best[0]:
            best = (mse, hl, k)
fo, fd = L.form(g, "epa", best[1], best[2]); fo, fd = fo[ii], fd[ii]
zs = L.zs
comp_shift = T["qb"].to_numpy() + T["recv"].to_numpy() + T["cov"].to_numpy(); pres_shift = T["ol"].to_numpy() + T["rush"].to_numpy()
comp_ev = T["qb_ev"].to_numpy() + T["recv_ev"].to_numpy() + T["cov_ev"].to_numpy(); pres_ev = T["ol_ev"].to_numpy() + T["rush_ev"].to_numpy()
scores = {"D1": zs(comp_shift) + zs(pres_shift), "D5": zs(comp_ev) + zs(pres_ev)}
team, blocks = T["posteam"].to_numpy(), np.array([f"{s}-{x}" for s, x in zip(s_arr, wk)])
gid = T["game_id"].to_numpy()
rng = np.random.default_rng(11)
ug = np.unique(gid); cl = {u: np.where(gid == u)[0] for u in ug}
out = {"form": {"half_life": best[1], "k": best[2]}}

def meat_se(X, b, clusters):
    e = y - X @ b; bread = np.linalg.inv(X.T @ (X * w[:, None])); sc = X * (w * e)[:, None]
    M = np.zeros((X.shape[1],) * 2)
    for u in np.unique(clusters):
        v = sc[clusters == u].sum(0); M += np.outer(v, v)
    return float(np.sqrt((bread @ M @ bread)[-1, -1]))

for name, x in scores.items():
    xs = zs(x)
    X = np.column_stack([np.ones(len(y)), fo, fd, xs]); b = L.wls(X, y, w)
    ab = np.array([f"{t}|{k}" for t, k in zip(team, blocks)])
    vt, vb, vab = (meat_se(X, b, c) ** 2 for c in (team, blocks, ab))
    two = L.cluster_se(X, y, w, b, [team, blocks])[-1]
    bs = []
    for _ in range(500):
        ix = np.concatenate([cl[u] for u in rng.choice(ug, len(ug))])
        bs.append(L.wls(X[ix], y[ix], w[ix])[-1])
    # pairs bootstrap resampling weeks (blocks) instead of games
    ub = np.unique(blocks); cb = {u: np.where(blocks == u)[0] for u in ub}
    bw = []
    for _ in range(500):
        ix = np.concatenate([cb[u] for u in rng.choice(ub, len(ub))])
        bw.append(L.wls(X[ix], y[ix], w[ix])[-1])
    out[name] = {"coef": float(b[-1]), "se_two_way": float(two), "var_team": vt, "var_week": vb, "var_obs_HC0": vab,
                 "se_team_only": vt ** 0.5, "se_week_only": vb ** 0.5, "se_HC0": vab ** 0.5, "se_game_bootstrap": float(np.std(bs)), "se_week_bootstrap": float(np.std(bw)),
                 "score_sd_raw": float(np.std(x)), "share_exact_zero": float(np.mean(x == 0)), "corr_with_form_o": float(np.corrcoef(xs, fo)[0, 1]), "corr_with_form_d": float(np.corrcoef(xs, fd)[0, 1])}
    # team-level persistence of the score: share of variance explained by team identity
    tm = {t: xs[team == t].mean() for t in np.unique(team)}
    out[name]["share_var_by_team"] = float(np.var([tm[t] for t in team]) / np.var(xs))
Path(L.MAN / os.environ.get("G2_D5_OUT", "d5_diagnosis.json")).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
