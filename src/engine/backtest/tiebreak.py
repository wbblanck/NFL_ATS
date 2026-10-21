"""EPA/efficiency tie-breaker in no-move games (docs/tiebreak_preregistration.md)."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine.backtest import efficiency_residual as ER
from engine.backtest import total as T
from engine.backtest.common import record as _ats
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.data import nflverse
from engine.models.margin_dist import TotalDist
from engine.picks.grading import is_half_point


def fit_error_model(tr: pl.DataFrame) -> np.ndarray:
    """OLS, no intercept: market error (margin + close) on the four differentials."""
    X = tr.select(ER.DIFFS).to_numpy().astype(float)
    y = (tr["margin"] + tr["close"]).to_numpy().astype(float)
    return np.linalg.lstsq(X, y, rcond=None)[0]


def compare(g: pl.DataFrame) -> dict:
    """g: y (home covers), p_live, pred_err. Both pick rules on the same games, with a paired sign test."""
    y = g["y"].to_numpy() == 1
    live = (g["p_live"].to_numpy() > 0.5) == y
    tb = (g["pred_err"].to_numpy() > 0) == y
    a_only, b_only = int((tb & ~live).sum()), int((live & ~tb).sum())
    n = a_only + b_only
    return {"tiebreak": _ats(tb.sum(), len(y)), "live": _ats(live.sum(), len(y)),
            "picks_differ": int(((g["pred_err"].to_numpy() > 0) != (g["p_live"].to_numpy() > 0.5)).sum()),
            "tiebreak_only_wins": a_only, "live_only_wins": b_only, "z": (a_only - b_only) / math.sqrt(n) if n else 0.0}


def run(metrics: pl.DataFrame) -> dict:
    df, sched = T.load()
    dif = ER.differentials(nflverse.with_kickoff(sched).filter(pl.col("season").is_between(1999, 2025)), metrics)
    allg = df.join(dif, on="game_id", how="inner")
    base = ER.base_predictions(df).rename({"p": "p_live"})
    rows, coefs = [], []
    for s in range(2010, 2022):
        b = fit_error_model(allg.filter(pl.col("season").is_between(2007, s - 1)))
        coefs.append({"season": s, **{c: float(v) for c, v in zip(ER.DIFFS, b)}})
        te = base.filter(pl.col("season") == s).join(dif, on="game_id", how="inner")
        rows.append(te.with_columns(pl.Series("pred_err", te.select(ER.DIFFS).to_numpy().astype(float) @ b)))
    R = pl.concat(rows)
    move = (R["open"] - R["close"]).abs()
    out = {"coefs": coefs,
           "no_move": compare(R.filter(move == 0)),
           "half_point_move_diag": compare(R.filter(move == 0.5))}
    out["pass"] = (out["no_move"]["tiebreak"]["W"] > out["no_move"]["live"]["W"] and out["no_move"]["z"] >= 1.96)
    # 2025 check: CBS half-point opens where the close equals the open
    c = df.filter(pl.col("season") == 2025).join(cbs_opens_2025(sched), on="game_id") \
        .filter(pl.col("cbs_open").map_elements(is_half_point, return_dtype=pl.Boolean), pl.col("close") == pl.col("cbs_open")) \
        .join(dif, on="game_id", how="inner")
    tr = df.filter(pl.col("season") <= 2024)
    td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
    b = fit_error_model(allg.filter(pl.col("season").is_between(2007, 2024)))
    c = c.with_columns(pl.Series("p_live", td.sf(-c["cbs_open"].to_numpy(), c["close"].to_numpy(), c["total"].to_numpy())),
                       pl.Series("pred_err", c.select(ER.DIFFS).to_numpy().astype(float) @ b),
                       (pl.col("margin") > -pl.col("cbs_open")).cast(pl.Float64).alias("y"))
    out["check_2025"] = compare(c) if c.height else {"games": 0}
    return out
