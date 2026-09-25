"""Game-total fix evaluation (docs/total_preregistration.md)."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest import calibration as C
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.data import nflverse, sbro
from engine.models.margin_dist import MarginDist, TotalDist
from engine.picks.grading import is_half_point

KINDS = ("shifted", "shifted_total", "normal_total")


def _ats(p, y):
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}


def load():
    sched, _ = nflverse.pull("schedules", save=False)
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                       pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    base = reg.select("game_id", "season", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close"),
                      pl.col("total_line").alias("total"))
    sb = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched) \
        .select("game_id", pl.col("open_home_spread").alias("open"))
    return base.join(sb, on="game_id", how="left"), sched


def _predict(kind, tr, te, open_col="open"):
    if kind == "shifted":
        md = MarginDist("shifted").fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
        return md.sf(-te[open_col].to_numpy(), te["close"].to_numpy()), None
    td = TotalDist(kind=kind).fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
    return td.sf(-te[open_col].to_numpy(), te["close"].to_numpy(), te["total"].to_numpy()), td.beta


def run():
    df, sched = load()
    rows, betas = [], []
    for s in range(2007, 2022):
        tr = df.filter(pl.col("season") < s)
        te = df.filter(pl.col("season") == s, pl.col("open").is_not_null(), pl.col("margin") != -pl.col("open"))
        y = (te["margin"].to_numpy() > -te["open"].to_numpy()).astype(float)
        for k in KINDS:
            p, b = _predict(k, tr, te)
            if b is not None and k == "shifted_total":
                betas.append({"season": s, "beta": float(b)})
            rows += [{"season": s, "kind": k, "p": pi, "y": yi, "total": T} for pi, yi, T in zip(p, y, te["total"].to_numpy())]
    R = pl.DataFrame(rows)
    q1, q2 = np.quantile(R.filter(pl.col("kind") == "shifted")["total"].to_numpy(), [1 / 3, 2 / 3])
    out = {"betas": pl.DataFrame(betas), "terciles": (float(q1), float(q2))}
    for k in KINDS:
        x = R.filter(pl.col("kind") == k)
        p, y = x["p"].to_numpy(), x["y"].to_numpy()
        terc = {}
        for lab, cond in [("low", pl.col("total") <= q1), ("mid", pl.col("total").is_between(q1, q2, closed="right")),
                          ("high", pl.col("total") > q2)]:
            xx = x.filter(cond)
            terc[lab] = _ats(xx["p"].to_numpy(), xx["y"].to_numpy())
        out[k] = {"log_loss": C.log_loss(p, y), "brier": C.brier(p, y), **_ats(p, y), "by_total": terc}
    base = R.filter(pl.col("kind") == "shifted")["p"].to_numpy() > 0.5
    out["picks_changed"] = {k: int((base != (R.filter(pl.col("kind") == k)["p"].to_numpy() > 0.5)).sum()) for k in KINDS[1:]}
    # confirmation 2025
    g = df.filter(pl.col("season") == 2025).join(cbs_opens_2025(sched), on="game_id")
    g = g.filter(pl.col("cbs_open").map_elements(is_half_point, return_dtype=pl.Boolean))
    tr = df.filter(pl.col("season") <= 2024)
    y = (g["margin"].to_numpy() > -g["cbs_open"].to_numpy()).astype(float)
    out["confirm_2025"] = {k: {"log_loss": C.log_loss(_predict(k, tr, g, "cbs_open")[0], y),
                               **_ats(_predict(k, tr, g, "cbs_open")[0], y)} for k in KINDS}
    return out
