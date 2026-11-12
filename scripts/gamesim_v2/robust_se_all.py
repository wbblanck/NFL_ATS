"""Audit: recompute every pooled, calibrated-form lineup test (D1-D10) with a game-cluster bootstrap standard error and compare with the two-way cluster z
used in the reports. Development seasons 2019-2020 only. Usage: G2_PRES=... G2_COMP=... G2_TAG=name python scripts/gamesim_v2/robust_se_all.py"""
from __future__ import annotations
import json, math, os, sys
from pathlib import Path
import numpy as np, polars as pl
sys.path.insert(0, str(Path(__file__).parent))
import lineup_dev_2019_2020 as L

TAG = os.environ.get("G2_TAG", "v1")
d, g = L.load()
pos = {(s, p): grp for s, p, grp in pl.read_parquet(L.FEAT / "position_lookup.parquet").filter(pl.col("season") <= L.LAST).iter_rows()}
T, _ = L.components(g, d, pos)
T = T.filter(pl.col("epa").is_not_null() & pl.col("comp").is_not_null())
ii = T.select("game_id", "posteam").join(g.with_row_index("i").select("game_id", "posteam", "i"), on=["game_id", "posteam"])["i"].to_numpy()
s_arr, wk = T["season"].to_numpy(), T["week"].to_numpy()
m19 = s_arr == 2019
zs = L.zs
sd_p, sd_c = T["sd_pres"].to_numpy(), T["sd_comp"].to_numpy()
comp_shift = T["qb"].to_numpy() + T["recv"].to_numpy() + T["cov"].to_numpy(); pres_shift = T["ol"].to_numpy() + T["rush"].to_numpy()
comp_ev = T["qb_ev"].to_numpy() + T["recv_ev"].to_numpy() + T["cov_ev"].to_numpy(); pres_ev = T["ol_ev"].to_numpy() + T["rush_ev"].to_numpy()
S = zs(comp_shift) + zs(pres_shift)
ok = ~(np.isnan(sd_p) | np.isnan(sd_c))
St = np.where(ok, zs(np.nan_to_num(comp_shift / sd_c, nan=0.0)) + zs(np.nan_to_num(pres_shift / sd_p, nan=0.0)), S)
Sev = zs(comp_ev) + zs(pres_ev)
Sact = zs(T["qb_act"].to_numpy() + T["recv_act"].to_numpy() + T["cov_act"].to_numpy()) + zs(T["ol_act"].to_numpy() + T["rush_act"].to_numpy())
preds = [("D1", S, ["epa"]), ("D2", comp_shift, ["epa", "comp"]), ("D3", pres_shift, ["epa", "press"]), ("D4", St, ["epa"]), ("D5", Sev, ["epa"]),
         ("D6", T["ol"].to_numpy(), ["press", "epa"]), ("D7", T["qb"].to_numpy(), ["comp", "epa"]), ("D8", T["recv"].to_numpy(), ["comp", "epa"]),
         ("D9a", T["rush"].to_numpy(), ["press", "epa"]), ("D9b", T["cov"].to_numpy(), ["comp", "epa"]), ("D10", Sact, ["epa"])]
forms = {}
for o, wc in L.OUTC.items():
    y, w = T[o].to_numpy(), T[wc].to_numpy().astype(float)
    best = None
    for hl in (3, 6, 12, 24):
        for k in (2, 4, 8):
            fo, fd = L.form(g, o, hl, k)
            X = np.column_stack([np.ones(len(ii)), fo[ii], fd[ii]])
            e = L.loo_week_mse(X[m19], y[m19], w[m19], wk[m19])
            mse = float((w[m19] * e).sum() / w[m19].sum())
            if best is None or mse < best[0]:
                best = (mse, hl, k)
    fo, fd = L.form(g, o, best[1], best[2]); forms[o] = (fo[ii], fd[ii])
gid = T["game_id"].to_numpy(); ug = np.unique(gid); cl = {u: np.where(gid == u)[0] for u in ug}
rng = np.random.default_rng(23)
boots = [np.concatenate([cl[u] for u in rng.choice(ug, len(ug))]) for _ in range(1000)]
team, blocks = T["posteam"].to_numpy(), np.array([f"{s}-{x}" for s, x in zip(s_arr, wk)])
rows = []
for pid, x, outs in preds:
    for o in outs:
        y, w = T[o].to_numpy(), T[L.OUTC[o]].to_numpy().astype(float)
        fo, fd = forms[o]
        xs = zs(x)
        X = np.column_stack([np.ones(len(y)), fo, fd, xs]); b = L.wls(X, y, w)
        two = L.cluster_se(X, y, w, b, [team, blocks])[-1]
        bs = np.array([L.wls(X[ix], y[ix], w[ix])[-1] for ix in boots])
        se_b = float(bs.std())
        zb = b[-1] / se_b
        rows.append({"id": pid, "outcome": o, "coef": float(b[-1]), "se_two_way": float(two), "z_two_way": float(b[-1] / two), "se_game_bootstrap": se_b, "z_game_bootstrap": float(zb),
                     "p_game_bootstrap": float(math.erfc(abs(zb) / math.sqrt(2))), "p_two_way": float(math.erfc(abs(b[-1] / two) / math.sqrt(2)))})
for key in ("p_two_way", "p_game_bootstrap"):
    order = sorted(range(len(rows)), key=lambda i: rows[i][key]); run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (len(rows) - rank) * rows[i][key])); rows[i]["holm_" + key[2:]] = run
Path(L.MAN / f"robust_se_all_{TAG}.json").write_text(json.dumps(rows, indent=1))
for r in rows:
    print(f'{TAG} {r["id"]:4s}{r["outcome"]:6s} coef {r["coef"]:+.4f} two-way z {r["z_two_way"]:+.2f} holm {r["holm_two_way"]:.2f} | boot SE {r["se_game_bootstrap"]:.4f} z {r["z_game_bootstrap"]:+.2f} holm {r["holm_game_bootstrap"]:.2f}')
