"""Walk-forward harness for the v2 designs (priors, EPA outcome). Same block rule as v1: a (season, week) block is predicted by a model fit
on plays dated strictly before it, decayed by half-life."""
from __future__ import annotations

import numpy as np
import polars as pl

from ..players import abilities as A, abilities_v2 as B
from .play_validation import day_index


def walk_forward_v2(d, kind, y, designs, lams, family, half_life, eval_seasons, train_from, meta, record=None):
    days = day_index(d)
    season, week = d["season"].to_numpy(), d["week"].to_numpy()
    preds = {k: np.full(d.height, np.nan) for k in designs}
    state = {k: (0.0, None) for k in designs}
    ab = []
    for s, w in sorted({(s, w) for s, w in zip(season.tolist(), week.tolist()) if s in eval_seasons}):
        te = np.where((season == s) & (week == w))[0]
        t0 = days[te].min()
        tr = np.where((days < t0) & (season >= train_from))[0]
        if len(tr) < 5000:
            continue
        wt = A.decay_weights(t0 - days[tr], half_life)
        for k, D in designs.items():
            lam = lams[k]
            Xtr = D.X[tr]
            if family == "logit":
                b0, beta = A.fit_logit(Xtr, y[tr], wt, lam, *state[k])
                state[k] = (b0, beta)
                preds[k][te] = 1 / (1 + np.exp(-(D.X[te] @ beta + b0)))
                p_tr = 1 / (1 + np.exp(-(Xtr @ beta + b0)))
                se = A.posterior_se(Xtr, p_tr, wt, lam) if k == record else None
            else:
                b0, beta, sres, diag, sd = B.fit_gauss(Xtr, y[tr], wt, lam, state[k][1])
                state[k] = (b0, beta)
                preds[k][te] = D.X[te] @ beta + b0
                se = B.gauss_se(diag, lam, sd, sres) if k == record else None
            if k == record:
                neff = np.asarray(Xtr.multiply(wt[:, None]).sum(0)).ravel()
                nraw = np.asarray(Xtr.sum(0)).ravel()
                cov = {n: beta[j] for j, n in enumerate(D.names) if n.startswith("cov|")}
                for j, nm in enumerate(D.names):
                    if D.group[j] in ("ctx", "cov") or nraw[j] <= 0 or ":" not in nm:
                        continue
                    g, u = nm.split(":", 1)
                    tot = beta[j] + sum(cov.get(f"cov|{g}|{b}", 0.0) for b in B.buckets(meta, u, int(s)))
                    ab.append((int(s), int(w), nm, float(tot), float(se[j]), float(neff[j]), int(nraw[j]), float(beta[j])))
                ab.append((int(s), int(w), "intercept", float(b0), 0.0, float(wt.sum()), len(tr), 0.0))
    out = d.select("game_id", "play_id", "season", "week", "posteam", "defteam").with_columns(
        pl.Series("y", y), *[pl.Series(k, v) for k, v in preds.items()])
    first = next(iter(designs))
    ab_df = pl.DataFrame(ab, schema=["season", "week", "key", "beta", "se", "n_eff", "n_raw", "dev"], orient="row") if ab else None
    return out.filter(pl.col(first).is_not_nan()), ab_df


def compare_sq(pred: pl.DataFrame, base: str, other: str, n=2000, seed=7) -> dict:
    """Paired mean squared-error difference (other - base) with a game-cluster bootstrap."""
    y = pred["y"].to_numpy()
    dl = (y - pred[other].to_numpy()) ** 2 - (y - pred[base].to_numpy()) ** 2
    g = pred.select("game_id").with_row_index("i").group_by("game_id").agg(pl.col("i")).get_column("i").to_list()
    sums, cnt = np.array([dl[ix].sum() for ix in g]), np.array([len(ix) for ix in g])
    rng = np.random.default_rng(seed)
    bs = []
    for _ in range(n):
        k = rng.integers(0, len(g), len(g))
        bs.append(sums[k].sum() / cnt[k].sum())
    return {"n": int(len(y)), "mean_diff": float(dl.mean()), "ci95": [float(v) for v in np.percentile(bs, [2.5, 97.5])]}
