"""Phase 3 drift strategies (pre-registered in docs/phase3_preregistration.md).

drift = market_home_spread_at_lock - frozen_home_spread (canonical sign: negative
= home favored). Negative drift => market moved toward home => pick home.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

K_GRID = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0)
BUCKETS = [("0.5", 0.5, 0.5), ("1", 1.0, 1.0), ("1.5", 1.5, 1.5), ("2-2.5", 2.0, 2.5),
           ("3-4", 3.0, 4.0), (">=4.5", 4.5, 99.0)]


def add_outcomes(df: pl.DataFrame) -> pl.DataFrame:
    """df: home_spread (frozen), market_spread, margin. Adds drift, result, drift_pick_home."""
    m, s = pl.col("margin"), pl.col("home_spread")
    return df.with_columns(
        (pl.col("market_spread") - s).alias("drift"),
        pl.when(m > -s).then(pl.lit("home")).when(m < -s).then(pl.lit("away")).otherwise(pl.lit("push"))
        .alias("result"),
    ).with_columns(
        pl.when(pl.col("drift") < 0).then(True).when(pl.col("drift") > 0).then(False).otherwise(None)
        .alias("drift_pick_home"),
        pl.col("drift").abs().alias("abs_drift"),
    )


def outcome(pick_home: pl.Expr) -> pl.Expr:
    return (pl.when(pick_home.is_null()).then(pl.lit("none"))
            .when(pl.col("result") == "push").then(pl.lit("P"))
            .when((pl.col("result") == "home") == pick_home).then(pl.lit("W"))
            .otherwise(pl.lit("L")))


def strategy_picks(df: pl.DataFrame, k: float | None = None, fallback_home: bool = False) -> pl.Expr:
    """k=None: pure sign-of-drift (None when drift == 0). Else follow drift when |drift| >= k,
    otherwise the fallback side."""
    fb = pl.lit(fallback_home)
    if k is None:
        return pl.col("drift_pick_home")
    return pl.when(pl.col("abs_drift") >= k).then(pl.col("drift_pick_home")).otherwise(fb) \
        .fill_null(fb)


def summarize(o: pl.Series) -> dict:
    w, l, p, none = (int((o == x).sum()) for x in ("W", "L", "P", "none"))
    n = w + l
    rate = w / n if n else float("nan")
    se = math.sqrt(rate * (1 - rate) / n) if n else float("nan")
    return {"W": w, "L": l, "P": p, "no_signal": none, "N": n, "win_rate": rate, "se": se,
            "z_vs_50": (rate - 0.5) / se if n and se > 0 else float("nan")}


def logistic(x: np.ndarray, y: np.ndarray, iters: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Plain Newton-Raphson logistic regression with intercept. Returns (beta, se)."""
    X = np.column_stack([np.ones_like(x, dtype=float), x.astype(float)])
    b = np.zeros(2)
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None])
        step = np.linalg.solve(H, X.T @ (y - p))
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    p = 1 / (1 + np.exp(-X @ b))
    H = X.T @ (X * (p * (1 - p))[:, None])
    return b, np.sqrt(np.diag(np.linalg.inv(H)))


def choose_k(train: pl.DataFrame, fallback_home: bool = False) -> float:
    """Pick k from K_GRID maximizing win rate on the training seasons only (ties -> smaller k)."""
    best, best_rate = K_GRID[0], -1.0
    for k in K_GRID:
        s = summarize(train.select(outcome(strategy_picks(train, k, fallback_home)).alias("o"))["o"])
        if s["win_rate"] > best_rate + 1e-12:
            best, best_rate = k, s["win_rate"]
    return best
