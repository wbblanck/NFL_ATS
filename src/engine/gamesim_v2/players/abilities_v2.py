"""Player effects with informative priors and a continuous outcome (gamesim v2, estimation v2; docs/gamesim_v2/PREREGISTRATION_estimation_v2.md).

Same on-field design as `abilities` (v1 stays frozen) plus, per position group, unpenalized group-level terms for what is known about a player
before any of his plays: draft round bucket (1, 2, 3, 4-7; undrafted is the baseline) and experience bucket (0, 1, 2-3 years; 4+ is the baseline).
A column counts how many players of that bucket in that group were on the field (the targeted receiver for receivers). The player-specific deviation
keeps its ridge penalty, so a player's effect is the group-bucket term plus his deviation: the prior mean now depends on draft pedigree and experience.
Families: 'logit' (pressure, completion) and 'gauss' (EPA per attempt, weighted ridge least squares on the outcome divided by its standard deviation).
"""
from __future__ import annotations

import numpy as np
import polars as pl
import scipy.sparse as sp
from scipy.sparse.linalg import cg

from . import abilities as A

MODEL_VERSION = "g2-onfield-ridge-v2-prior"
DRAFT = [("dr1", lambda r: r == 1), ("dr2", lambda r: r == 2), ("dr3", lambda r: r == 3), ("dr4", lambda r: 4 <= r <= 7)]
EXPER = [("e0", lambda e: e == 0), ("e1", lambda e: e == 1), ("e23", lambda e: 2 <= e <= 3)]
GROUPS = {"pressure": ["OL", "QB", "DL", "LB"], "completion": ["R", "QB", "DB", "LB"], "epa": ["R", "QB", "DB", "LB"]}


def player_meta(ident: pl.DataFrame) -> dict:
    """uid -> (draft round or 0 if undrafted/unknown, rookie season or None)."""
    return {u: (int(r) if r is not None else 0, int(s) if s is not None else None)
            for u, r, s in zip(ident["uid"], ident["draft_round"], ident["rookie_season"])}


def buckets(meta: dict, uid: str, season: int) -> list:
    r, rs = meta.get(uid, (0, None))
    out = [n for n, f in DRAFT if r and f(r)]
    if rs is not None:
        out += [n for n, f in EXPER if f(season - rs)]
    return out


def build_design_v2(d: pl.DataFrame, pos: dict, kind: str, meta: dict, prior: bool = True, team_effects: bool = False,
                    player_effects: bool = True) -> A.Design:
    ctx, ctx_names = (A.pressure_context if kind == "pressure" else A.completion_context)(d)
    off_groups = {"OL"} if kind == "pressure" else set()
    def_groups = {"DL", "LB"} if kind == "pressure" else {"DB", "LB"}
    season = d["season"].to_list()
    offp, defp = d["offense_players"].to_list(), d["defense_players"].to_list()
    qb, tgt, ot, dt = d["qb"].to_list(), d["target"].to_list(), d["posteam"].to_list(), d["defteam"].to_list()
    grow, covrow = [], {}
    for i in range(d.height):
        s = season[i]
        members = []
        if player_effects:
            if qb[i]:
                members.append(("QB", qb[i]))
            if kind != "pressure" and tgt[i]:
                members.append(("R", tgt[i]))
            members += [("OL", p) for p in (offp[i] or "").split(";") if p and pos.get((s, p)) in off_groups]
            members += [(pos.get((s, p)), p) for p in (defp[i] or "").split(";") if p and pos.get((s, p)) in def_groups]
        for g, u in members:
            grow.append((i, f"{g}:{u}"))
            if prior:
                for b in buckets(meta, u, s):
                    covrow[(i, f"cov|{g}|{b}")] = covrow.get((i, f"cov|{g}|{b}"), 0) + 1
        if team_effects:
            grow.append((i, "OT:" + ot[i]))
            grow.append((i, "DT:" + dt[i]))
    keys = sorted({k for _, k in grow})
    covkeys = sorted({k for _, k in covrow})
    index = {k: j for j, k in enumerate(keys)}
    rows = np.array([r for r, k in grow], dtype=np.int64)
    cols = np.array([index[k] for _, k in grow], dtype=np.int64)
    P = sp.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(d.height, len(keys)))
    blocks = [sp.csr_matrix(ctx)]
    names = list(ctx_names)
    group = ["ctx"] * len(ctx_names)
    if covkeys:
        ci = {k: j for j, k in enumerate(covkeys)}
        C = sp.csr_matrix(([v for v in covrow.values()], ([r for r, _ in covrow], [ci[k] for _, k in covrow])), shape=(d.height, len(covkeys)))
        blocks.append(C)
        names += covkeys
        group += ["cov"] * len(covkeys)
    blocks.append(P)
    names += keys
    group += [k.split(":")[0] for k in keys]
    X = sp.hstack(blocks).tocsr()
    return A.Design(X, names, np.array(group), np.zeros(len(names)), ctx_names)


def lam_vector(D: A.Design, lam: dict) -> np.ndarray:
    return np.array([1e-3 if g in ("ctx", "cov") else lam[g] for g in D.group])


def fit_gauss(X, y, w, lam, beta0=None):
    """Weighted ridge least squares with an unpenalized intercept column handled by centering. Returns (intercept, beta, residual sd).
    y is divided by its weighted sd inside, the result is returned in the original units."""
    sw = w.sum()
    mu = (w @ y) / sw
    sd = float(np.sqrt((w @ (y - mu) ** 2) / sw))
    ys = (y - mu) / sd
    XtWX = (X.T @ sp.diags(w) @ X).tocsc()
    xw_mean = np.asarray(X.T @ w).ravel() / sw
    # centered normal equations: (X'WX - sw m m') b = X'W ys, with ridge added on the diagonal
    A_op = lambda v: XtWX @ v - sw * xw_mean * (xw_mean @ v) + lam * v
    from scipy.sparse.linalg import LinearOperator
    op = LinearOperator(XtWX.shape, matvec=A_op)
    rhs = np.asarray(X.T @ (w * ys)).ravel() - sw * xw_mean * ((w @ ys) / sw)
    b, _ = cg(op, rhs, x0=beta0, rtol=1e-7, maxiter=400)
    resid = ys - (X @ b - xw_mean @ b)
    s2 = float((w @ resid ** 2) / sw)
    diag = np.asarray(XtWX.diagonal()).ravel() - sw * xw_mean ** 2
    return float(mu - sd * (xw_mean @ b)), sd * b, sd * np.sqrt(s2), diag, sd


def gauss_se(diag, lam, sd, s):
    return s / np.sqrt(np.maximum(diag + lam, 1e-9))
