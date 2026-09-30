"""Adaptive in-season model (docs/adaptive_preregistration.md).

Layer 1 (`ratings`): one net rating per team in points, updated after every game by a Kalman filter with two
measurements, the final margin and a scaled efficiency margin. Uncertainty grows before each game (q) and at a new
season ratings shrink toward 0 (s) with extra uncertainty (p0). Every prediction uses only earlier games.

Layer 2 (`fit_logit`, `features`): a logistic pick model re-fit before every week on earlier games, weighted by
age (half-life H seasons) with an L2 penalty on the slopes.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import polars as pl

from engine.models.projection import FRANCHISE

P_INIT = 36.0            # prior variance of a team never seen (points^2)


def _f(t: str) -> str:
    return FRANCHISE.get(t, t)


def efficiency_margin(metrics: pl.DataFrame) -> dict[tuple[str, str], float]:
    """(game_id, team) -> EPA per play on offense (dropbacks and designed runs, garbage time removed)."""
    m = metrics.with_columns(
        ((pl.col("db").fill_null(0) * pl.col("n_db") + pl.col("rush").fill_null(0) * pl.col("n_rush"))
         / (pl.col("n_db") + pl.col("n_rush"))).alias("epa"))
    return {(r[0], _f(r[1])): r[2] for r in m.select("game_id", "team", "epa").iter_rows() if r[2] is not None}


def ratings(games: pl.DataFrame, eff: dict, q: float, s: float, p0: float, rho: float, k: float, R: float = 170.0,
            end_season: int | None = None) -> pl.DataFrame:
    """Pre-game predictions for every game in `games` (completed REG+POST games in kickoff order with game_id,
    season, game_type, home_team, away_team, result, location). Returns game_id, pred_margin, pred_var, hfa."""
    r = defaultdict(float)
    P = defaultdict(lambda: P_INIT)
    seen: dict[str, int] = {}
    home_margins: dict[int, list] = defaultdict(list)
    out = []
    for g in games.iter_rows(named=True):
        season = g["season"]
        h, a = _f(g["home_team"]), _f(g["away_team"])
        for t in (h, a):
            if t in seen and seen[t] != season:
                r[t] *= (1 - s)
                P[t] = P[t] * (1 - s) ** 2 + p0
            seen[t] = season
            P[t] += q
        prev = [x for yr in (season - 1, season - 2, season - 3) for x in home_margins.get(yr, [])]
        hfa = float(np.mean(prev)) if prev else 2.5
        neutral = (g.get("location") or "") == "Neutral"
        edge = 0.0 if neutral else hfa
        pred = edge + r[h] - r[a]
        var = P[h] + P[a]
        out.append({"game_id": g["game_id"], "pred_margin": pred, "pred_var": var, "hfa": edge})
        if g["result"] is None:
            continue
        if not neutral and g["game_type"] == "REG":
            home_margins[season].append(g["result"])
        meas = [(float(g["result"]), R)]
        eh, ea = eff.get((g["game_id"], h)), eff.get((g["game_id"], a))
        if eh is not None and ea is not None and rho > 0:
            meas.append((edge + k * (eh - ea), R * rho))
        for y, Rv in meas:                                  # sequential scalar Kalman updates, H = [1, -1]
            S = P[h] + P[a] + Rv
            innov = y - (edge + r[h] - r[a])
            kh, ka = P[h] / S, -P[a] / S
            r[h] += kh * innov
            r[a] += ka * innov
            ph, pa, cov = P[h], P[a], 0.0
            P[h] = ph - ph * ph / S
            P[a] = pa - pa * pa / S                         # cross-covariance is not tracked (diagonal filter)
    return pl.DataFrame(out)


def fit_logit(X: np.ndarray, y: np.ndarray, w: np.ndarray, lam: float, iters: int = 50) -> np.ndarray:
    """Weighted logistic regression with an L2 penalty on all but the first (intercept) column. Newton steps."""
    b = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], lam)
    pen[0] = 0.0
    for _ in range(iters):
        z = X @ b
        p = 1 / (1 + np.exp(-z))
        g = X.T @ (w * (p - y)) + pen * b
        Hm = (X * (w * p * (1 - p))[:, None]).T @ X + np.diag(pen) + 1e-9 * np.eye(X.shape[1])
        step = np.linalg.solve(Hm, g)
        b -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return b


def features(p_live: np.ndarray, pred_margin: np.ndarray, line: np.ndarray, drift: np.ndarray) -> np.ndarray:
    p = np.clip(p_live, 1e-4, 1 - 1e-4)
    edge = (pred_margin + line) / 13.0
    low = (np.abs(drift) < 1).astype(float)
    return np.column_stack([np.ones_like(p), np.log(p / (1 - p)), edge, edge * low])
