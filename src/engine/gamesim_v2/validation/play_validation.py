"""Walk-forward validation of the on-field player models against context-only and team-level baselines (sprint 1, task 6)."""
from __future__ import annotations

import numpy as np
import polars as pl

from ..players import abilities as A

VARIANTS = {"ctx": dict(player_effects=False, team_effects=False),
            "team": dict(player_effects=False, team_effects=True),
            "player": dict(player_effects=True, team_effects=False),
            "both": dict(player_effects=True, team_effects=True)}


def day_index(d: pl.DataFrame) -> np.ndarray:
    return d["game_date"].str.to_date().to_physical().to_numpy().astype(float)


def make_designs(d, pos, kind, variants=("ctx", "team", "player", "both")):
    """Design matrices are independent of the ridge strengths, so build them once and reuse them across a grid."""
    return {v: A.build_design(d, pos, kind, {g: 1.0 for g in ("OL", "DL", "LB", "DB", "QB", "R", "OT", "DT")}, **VARIANTS[v]) for v in variants}


def walk_forward(d: pl.DataFrame, pos: dict, kind: str, y: np.ndarray, lam: dict, half_life: float, eval_seasons: list,
                 train_from: int, variants=("ctx", "team", "player", "both"), record_abilities: str | None = "player",
                 designs: dict | None = None):
    """d: dropbacks (rows of one model's population). y: 0/1 outcome aligned to d. Returns (predictions frame, abilities frame).
    A block is one (season, week). Training rows are those dated strictly before the block's first game, season >= train_from."""
    days = day_index(d)
    season, week = d["season"].to_numpy(), d["week"].to_numpy()
    designs = designs or make_designs(d, pos, kind, variants)
    lams = {v: np.array([1e-3 if g == "ctx" else lam[g] for g in designs[v].group]) for v in variants}
    preds = {v: np.full(d.height, np.nan) for v in variants}
    ab_rows = []
    state = {v: (0.0, None) for v in variants}
    blocks = sorted({(s, w) for s, w in zip(season.tolist(), week.tolist()) if s in eval_seasons})
    for s, w in blocks:
        te = np.where((season == s) & (week == w))[0]
        t0 = days[te].min()
        tr = np.where((days < t0) & (season >= train_from))[0]
        if len(tr) < 5000:
            continue
        wt = A.decay_weights(t0 - days[tr], half_life)
        for v in variants:
            D = designs[v]
            b0, beta = A.fit_logit(D.X[tr], y[tr], wt, lams[v], *state[v])
            state[v] = (b0, beta)
            preds[v][te] = 1 / (1 + np.exp(-(D.X[te] @ beta + b0)))
            if v == record_abilities:
                p_tr = 1 / (1 + np.exp(-(D.X[tr] @ beta + b0)))
                se = A.posterior_se(D.X[tr], p_tr, wt, lams[v])
                neff = np.asarray(D.X[tr].multiply(wt[:, None]).sum(0)).ravel()
                nraw = np.asarray(D.X[tr].sum(0)).ravel()
                ab_rows.append((int(s), int(w), "intercept", float(b0), 0.0, float(wt.sum()), len(tr)))
                for j, nm in enumerate(D.names):
                    if D.group[j] == "ctx" or nraw[j] > 0:
                        ab_rows.append((int(s), int(w), nm, float(beta[j]), float(se[j]), float(neff[j]), int(nraw[j])))
    out = d.select("game_id", "play_id", "season", "week", "posteam", "defteam").with_columns(
        pl.Series("y", y), *[pl.Series(v, preds[v]) for v in variants])
    ab = pl.DataFrame(ab_rows, schema=["season", "week", "key", "beta", "se", "n_eff", "n_raw"], orient="row") if ab_rows else None
    return out.filter(pl.col(variants[0]).is_not_nan()), ab


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def compare(pred: pl.DataFrame, base: str, other: str, seeds: int = 2000, rng_seed: int = 7) -> dict:
    """Paired log-loss difference (other - base; negative = other better) with a game-cluster bootstrap interval."""
    y = pred["y"].to_numpy()
    dl = logloss(y, pred[other].to_numpy()) - logloss(y, pred[base].to_numpy())
    g = pred.select("game_id").with_row_index("i").group_by("game_id").agg(pl.col("i")).get_column("i").to_list()
    sums = np.array([dl[ix].sum() for ix in g])
    cnt = np.array([len(ix) for ix in g])
    rng = np.random.default_rng(rng_seed)
    bs = []
    for _ in range(seeds):
        k = rng.integers(0, len(g), len(g))
        bs.append(sums[k].sum() / cnt[k].sum())
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"n_plays": int(len(y)), "mean_diff": float(dl.mean()), "ci95": [float(lo), float(hi)]}


def brier(y, p):
    return float(np.mean((y - p) ** 2))
