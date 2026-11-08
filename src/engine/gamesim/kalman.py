"""Kalman-filter margin rating (nfl-betting-model docs/batch1_preregistration.md, B2 + M8).

Each team's strength is a hidden value with a mean and a variance (Glickman-Stern style, diagonal approximation:
team strengths are tracked independently, without their covariance). Forecast margin = home - away strength + h.
Between weeks every variance grows by tau_w^2; between seasons means shrink by rho and variances become
rho^2 * var + tau_s^2. Each game updates both teams by the Kalman gain on the observed margin. A week's forecasts use
the state before that week; every forecast uses only earlier games.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

PRIOR_VAR = 49.0
PARAMS = ("h", "sigma_m", "tau_w", "rho", "tau_s")


def update(mh, vh, ma, va, margin, h, sigma_m):
    """One game: returns new (mh, vh, ma, va), the forecast and its variance."""
    pred = mh - ma + h
    s = vh + va + sigma_m ** 2
    r = margin - pred
    return mh + vh / s * r, vh - vh * vh / s, ma - va / s * r, va - va * va / s, pred, s


def _arrays(games: pl.DataFrame):
    g = games.sort("season", "week", "game_id")
    return (g["game_id"].to_list(), g["season"].to_list(), g["week"].to_list(), g["home_team"].to_list(),
            g["away_team"].to_list(), g["result"].to_list(), g["neutral"].to_list())


def run(games: pl.DataFrame, p: dict, _arr=None):
    """games: game_id, season, week, home_team, away_team, result (home margin), neutral. Returns (forecasts frame,
    total normal log likelihood by season dict, final state)."""
    gid, sea, wk, ht, at, res, neu = _arr or _arrays(games)
    h, sm, tw, rho, ts = (p[k] for k in PARAMS)
    M: dict[str, float] = {}
    V: dict[str, float] = {}
    rows_f, rows_s = [], []
    ll: dict[int, float] = {}
    cur_season, cur_week = None, None
    pend = []
    n = len(gid)
    i = 0
    while i <= n:
        new_week = i == n or (sea[i], wk[i]) != (cur_season, cur_week)
        if new_week:
            for (a_h, a_a, nmh, nvh, nma, nva) in pend:
                M[a_h], V[a_h], M[a_a], V[a_a] = nmh, nvh, nma, nva
            pend = []
            if i == n:
                break
            if sea[i] != cur_season:
                for t in M:
                    M[t] *= rho
                    V[t] = rho * rho * V[t] + ts * ts
            else:
                for t in V:
                    V[t] += tw * tw
            cur_season, cur_week = sea[i], wk[i]
        a_h, a_a = ht[i], at[i]
        mh, vh = M.get(a_h, 0.0), V.get(a_h, PRIOR_VAR)
        ma, va = M.get(a_a, 0.0), V.get(a_a, PRIOR_VAR)
        hh = 0.0 if neu[i] else h
        nmh, nvh, nma, nva, pred, s = update(mh, vh, ma, va, res[i], hh, sm)
        pend.append((a_h, a_a, nmh, nvh, nma, nva))
        rows_f.append(pred)
        rows_s.append(s)
        ll[sea[i]] = ll.get(sea[i], 0.0) - 0.5 * (math.log(2 * math.pi * s) + (res[i] - pred) ** 2 / s)
        i += 1
    order = pl.DataFrame({"game_id": gid, "kalman": rows_f, "kalman_var": rows_s})
    return order, ll, (M, V)


def nelder_mead(f, x0, step, iters=400, tol=1e-6):
    n = len(x0)
    pts = [np.array(x0, float)] + [np.array(x0, float) + np.eye(n)[j] * step[j] for j in range(n)]
    val = [f(x) for x in pts]
    for _ in range(iters):
        o = np.argsort(val)
        pts, val = [pts[j] for j in o], [val[j] for j in o]
        if abs(val[-1] - val[0]) < tol:
            break
        c = np.mean(pts[:-1], axis=0)
        xr = c + (c - pts[-1])
        fr = f(xr)
        if fr < val[0]:
            xe = c + 2 * (c - pts[-1])
            fe = f(xe)
            pts[-1], val[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < val[-2]:
            pts[-1], val[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c)
            fc = f(xc)
            if fc < val[-1]:
                pts[-1], val[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (x - pts[0]) for x in pts[1:]]
                val = [val[0]] + [f(x) for x in pts[1:]]
    j = int(np.argmin(val))
    return pts[j], val[j]


def fit(games: pl.DataFrame, fit_seasons: list[int], x0=None) -> dict:
    """Maximum likelihood of the margins in fit_seasons (filter run over all of `games`)."""
    arr = _arrays(games)
    x0 = x0 or [2.0, 13.0, 1.0, 0.7, 3.0]

    def neg(x):
        p = dict(zip(PARAMS, (x[0], abs(x[1]), abs(x[2]), min(max(x[3], 0.0), 1.0), abs(x[4]))))
        _, ll, _ = run(games, p, arr)
        return -sum(ll.get(s, 0.0) for s in fit_seasons)

    x, v = nelder_mead(neg, x0, [0.5, 1.0, 0.3, 0.1, 1.0])
    return {"h": float(x[0]), "sigma_m": float(abs(x[1])), "tau_w": float(abs(x[2])),
            "rho": float(min(max(x[3], 0.0), 1.0)), "tau_s": float(abs(x[4])), "neg_loglik": float(v)}


def fit_blend(open_, model, margin) -> float:
    """w in f = open + w (model - open), least squares."""
    x = np.asarray(model, float) - np.asarray(open_, float)
    y = np.asarray(margin, float) - np.asarray(open_, float)
    return float((x * y).sum() / (x * x).sum())
