"""Hierarchical (ridge) on-field player effects for dropbacks (gamesim v2, sprint 1).

A play outcome y (pressure, completion) is modelled as  logit P = context + sum of effects of the players on the field.
Each player-group (offensive line, pass rushers, quarterbacks, receivers, defensive backs, team) has its own ridge penalty,
so a player with few plays is pulled to the group average and a player with many plays is driven by his own plays. That is
the partial pooling the spec asks for. Uncertainty per player is the diagonal Laplace approximation
    se_j = 1 / sqrt(lambda_g + sum_i w_i p_i (1 - p_i) x_ij^2).
Fits are walk-forward: a block (season, week) is predicted by a model trained on plays dated strictly before the block,
weighted by 0.5 ** (age_days / half_life).

What this is not: an assignment model. Participation says who was on the field, not who blocked whom or who covered whom,
so effects are on-field effects, shared across everyone in the group on that play.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl
import scipy.sparse as sp
from scipy.optimize import minimize

MODEL_VERSION = "g2-onfield-ridge-v1"


@dataclass
class Design:
    """Sparse design matrix with named columns, a ridge penalty per column, and the group of each column."""
    X: sp.csr_matrix
    names: list
    group: np.ndarray            # group label per column ('ctx' for context columns)
    lam: np.ndarray              # ridge penalty per column
    ctx_names: list = field(default_factory=list)


def _bucket(x, edges):
    return np.digitize(np.nan_to_num(np.asarray(x, float), nan=-99.0), edges)


def pressure_context(d: pl.DataFrame) -> tuple[np.ndarray, list]:
    nr = np.clip(d["number_of_pass_rushers"].fill_null(4).to_numpy(), 2, 7)
    cols, names = [], []
    for v in range(2, 8):
        cols.append((nr == v).astype(float)); names.append(f"nr={v}")
    dn = d["down"].fill_null(1).to_numpy()
    for v in (2, 3, 4):
        cols.append((dn == v).astype(float)); names.append(f"down={v}")
    yb = _bucket(d["ydstogo"].fill_null(10).to_numpy(), [4, 7, 11])
    for v in (1, 2, 3):
        cols.append((yb == v).astype(float)); names.append(f"togo{v}")
    cols.append(d["shotgun"].fill_null(0).to_numpy().astype(float)); names.append("shotgun")
    cols.append(d["no_huddle"].fill_null(0).to_numpy().astype(float)); names.append("no_huddle")
    return np.column_stack(cols), names


def completion_context(d: pl.DataFrame) -> tuple[np.ndarray, list]:
    ay = d["air_yards"].to_numpy().astype(float)
    ab = np.where(np.isnan(ay), 0, _bucket(ay, [0, 5, 10, 15, 20]) + 1)
    cols, names = [], []
    for v in range(1, 7):
        cols.append((ab == v).astype(float)); names.append(f"air{v}")
    cols.append(d["was_pressure"].fill_null(False).to_numpy().astype(float)); names.append("pressure")
    dn = d["down"].fill_null(1).to_numpy()
    for v in (2, 3, 4):
        cols.append((dn == v).astype(float)); names.append(f"down={v}")
    yb = _bucket(d["ydstogo"].fill_null(10).to_numpy(), [4, 7, 11])
    for v in (1, 2, 3):
        cols.append((yb == v).astype(float)); names.append(f"togo{v}")
    cols.append(d["shotgun"].fill_null(0).to_numpy().astype(float)); names.append("shotgun")
    return np.column_stack(cols), names


def build_design(d: pl.DataFrame, pos: dict, kind: str, lam: dict, team_effects: bool = False, player_effects: bool = True,
                 columns: list | None = None) -> Design:
    """kind 'pressure': OL (offense), QB, DL and LB (defense) on field.  kind 'completion': targeted receiver, QB, DB and LB.
    pos: {(season, gsis_id): group}.  lam: ridge penalty by group name ('OL','QB','DL','LB','DB','R','OT','DT')."""
    ctx, ctx_names = (pressure_context if kind == "pressure" else completion_context)(d)
    off_groups = {"OL"} if kind == "pressure" else set()
    def_groups = {"DL", "LB"} if kind == "pressure" else {"DB", "LB"}
    season = d["season"].to_list()
    offp, defp = d["offense_players"].to_list(), d["defense_players"].to_list()
    qb, tgt = d["qb"].to_list(), d["target"].to_list()
    ot, dt = d["posteam"].to_list(), d["defteam"].to_list()
    index = {c: i for i, c in enumerate(columns)} if columns is not None else {}
    grow = []  # (row, colkey)
    for i in range(d.height):
        s = season[i]
        if player_effects:
            if qb[i]:
                grow.append((i, "QB:" + qb[i]))
            if kind == "completion" and tgt[i]:
                grow.append((i, "R:" + tgt[i]))
            for pid in (offp[i] or "").split(";"):
                if pid and pos.get((s, pid)) in off_groups:
                    grow.append((i, "OL:" + pid))
            for pid in (defp[i] or "").split(";"):
                g = pos.get((s, pid)) if pid else None
                if g in def_groups:
                    grow.append((i, g + ":" + pid))
        if team_effects:
            grow.append((i, "OT:" + ot[i]))
            grow.append((i, "DT:" + dt[i]))
    if columns is None:
        keys = sorted({k for _, k in grow})
        index = {k: j for j, k in enumerate(keys)}
    else:
        keys = list(columns)
    rows = np.array([r for r, k in grow if k in index], dtype=np.int64)
    cols = np.array([index[k] for _, k in grow if k in index], dtype=np.int64)
    P = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(d.height, len(keys)))
    X = sp.hstack([sp.csr_matrix(ctx), P]).tocsr()
    names = ctx_names + keys
    group = np.array(["ctx"] * len(ctx_names) + [k.split(":")[0] for k in keys])
    lamv = np.array([1e-3 if g == "ctx" else lam[g] for g in group])
    return Design(X, names, group, lamv, ctx_names)


def fit_logit(X, y, w, lam, intercept0=0.0, beta0=None):
    """Weighted L2-penalised logistic regression (intercept unpenalised). Returns (intercept, beta)."""
    n, k = X.shape
    w = np.asarray(w, float)
    y = np.asarray(y, float)

    def f(theta):
        b0, b = theta[0], theta[1:]
        z = X @ b + b0
        # log(1+e^z) - y z, stable
        ll = np.logaddexp(0, z) - y * z
        p = 0.5 * (1 + np.tanh(z / 2))
        r = w * (p - y)
        val = float(w @ ll + 0.5 * np.sum(lam * b * b))
        g = np.empty(k + 1)
        g[0] = r.sum()
        g[1:] = X.T @ r + lam * b
        return val, g

    t0 = np.zeros(k + 1)
    t0[0] = intercept0
    if beta0 is not None:
        t0[1:] = beta0
    res = minimize(f, t0, jac=True, method="L-BFGS-B", options={"maxiter": 300, "gtol": 1e-5})
    return float(res.x[0]), res.x[1:]


def posterior_se(X, p, w, lam):
    """Diagonal Laplace approximation of each coefficient's standard error."""
    h = w * p * (1 - p)
    info = np.asarray(X.multiply(X).T @ h).ravel() + lam
    return 1.0 / np.sqrt(info)


def decay_weights(days_before: np.ndarray, half_life: float) -> np.ndarray:
    return 0.5 ** (days_before / half_life)
