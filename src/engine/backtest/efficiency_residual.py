"""Line-movement model + EPA/efficiency differentials (docs/phase8_efficiency_preregistration.md).

Base: the live estimator (TotalDist "shifted_total") walk-forward, frozen line = SBRO open, market = nflverse close.
Residual: logit(p) = a + b*logit(p_base) + gamma*[d_db, d_rush, d_sr, d_rz], fit on earlier seasons only
(phase 6 framework). Differentials come from the v6 point-in-time ratings with a-priori h = 6, s = 0.5.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest import total as T
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.data import nflverse
from engine.features import efficiency_v6 as F
from engine.models.margin_dist import TotalDist
from engine.models.projection import FRANCHISE
from engine.picks.grading import is_half_point

H, S = 6, 0.5
DIFFS = [f"d_{m}" for m in F.METRICS]
GROUPS = {"all four (decides)": DIFFS, "EPA only (db, rush)": ["d_db", "d_rush"],
          "efficiency only (sr, rz)": ["d_sr", "d_rz"]}


def differentials(sched: pl.DataFrame, metrics: pl.DataFrame) -> pl.DataFrame:
    """game_id -> d_m = (home off + away allowed) - (away off + home allowed), from pre-game ratings."""
    f = F.build(sched, metrics, H, S)
    g = sched.select("game_id", pl.col("home_team").replace(FRANCHISE).alias("home"),
                     pl.col("away_team").replace(FRANCHISE).alias("away"))
    h = f.select("game_id", pl.col("team").alias("home"), *[(pl.col(f"off_{m}") + pl.col(f"def_{m}")).alias(f"h_{m}")
                                                            for m in F.METRICS])
    a = f.select("game_id", pl.col("team").alias("away"), *[(pl.col(f"off_{m}") + pl.col(f"def_{m}")).alias(f"a_{m}")
                                                            for m in F.METRICS])
    j = g.join(h, on=["game_id", "home"]).join(a, on=["game_id", "away"])
    return j.select("game_id", *[(pl.col(f"h_{m}") - pl.col(f"a_{m}")).alias(f"d_{m}") for m in F.METRICS])


def base_predictions(df: pl.DataFrame) -> pl.DataFrame:
    """Walk-forward live-model P(home covers the SBRO open), 2007-2021, pushes excluded."""
    out = []
    for s in range(2007, 2022):
        tr = df.filter(pl.col("season") < s)
        te = df.filter(pl.col("season") == s, pl.col("open").is_not_null(), pl.col("margin") != -pl.col("open"))
        p, _ = T._predict("shifted_total", tr, te)
        out.append(te.with_columns(pl.Series("p", p), (pl.col("margin") > -pl.col("open")).cast(pl.Float64).alias("y")))
    return pl.concat(out)


def _summ(p, y, raw):
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"n": n, "log_loss": C.log_loss(p, y), "brier": C.brier(p, y), "ats_W": w, "ats_win_rate": r,
            "ats_se": math.sqrt(r * (1 - r) / n), "picks_changed_vs_raw": int(((p > 0.5) != (raw > 0.5)).sum())}


def walk_forward(d: pl.DataFrame, cols: list[str] | None):
    ps, ys, raws, coefs = [], [], [], []
    for s in range(2010, 2022):
        tr, te = d.filter(pl.col("season") < s), d.filter(pl.col("season") == s)
        f = C.platt(tr["p"].to_numpy(), tr["y"].to_numpy(), tr.select(cols).to_numpy().astype(float) if cols else None)
        ps.append(f(te["p"].to_numpy(), te.select(cols).to_numpy().astype(float) if cols else None))
        ys.append(te["y"].to_numpy()); raws.append(te["p"].to_numpy())
        coefs.append({"season": s, **{f"g_{c}": float(v) for c, v in zip(cols or [], f.coef[2:])}})
    return np.concatenate(ps), np.concatenate(ys), np.concatenate(raws), coefs


def run(metrics: pl.DataFrame, log=print) -> dict:
    df, sched = T.load()
    s_all = nflverse.with_kickoff(sched).filter(pl.col("season").is_between(1999, 2025))
    dif = differentials(s_all, metrics)
    base = base_predictions(df)
    d = base.join(dif, on="game_id", how="left")
    miss = d.filter(pl.any_horizontal([pl.col(c).is_null() for c in DIFFS]))
    d = d.fill_null(0)
    test = d.filter(pl.col("season") >= 2010)
    raw_p, y = test["p"].to_numpy(), test["y"].to_numpy()
    rows = [{"model": "raw (live model)", **_summ(raw_p, y, raw_p)}]
    pp, py, pr, _ = walk_forward(d, None)
    rows.append({"model": "platt (no features)", **_summ(pp, py, pr)})
    coefs = {}
    for name, cols in GROUPS.items():
        p, yy, r, cf = walk_forward(d, cols)
        rows.append({"model": f"+ {name}", **_summ(p, yy, r)})
        coefs[name] = cf
    prim = rows[2]
    kept = prim["log_loss"] < rows[0]["log_loss"] and prim["log_loss"] < rows[1]["log_loss"] \
        and prim["ats_win_rate"] >= rows[0]["ats_win_rate"]
    # diagnostic: does each differential predict the margin the market missed?
    g = df.join(dif, on="game_id").filter(pl.col("season").is_between(2007, 2021))
    resid = (g["margin"] + g["close"]).to_numpy()
    corr = {c: {"with_market_residual": float(np.corrcoef(g[c].to_numpy(), resid)[0, 1]),
                "with_market_spread": float(np.corrcoef(g[c].to_numpy(), -g["close"].to_numpy())[0, 1]),
                "with_margin": float(np.corrcoef(g[c].to_numpy(), g["margin"].to_numpy())[0, 1])} for c in DIFFS}
    # confirmation 2025 (reported; decisive only as the second condition if kept)
    c25 = df.filter(pl.col("season") == 2025).join(cbs_opens_2025(sched), on="game_id") \
        .filter(pl.col("cbs_open").map_elements(is_half_point, return_dtype=pl.Boolean)).join(dif, on="game_id", how="left")
    tr = df.filter(pl.col("season") <= 2024)
    td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
    p_live = td.sf(-c25["cbs_open"].to_numpy(), c25["close"].to_numpy(), c25["total"].to_numpy())
    y25 = (c25["margin"].to_numpy() > -c25["cbs_open"].to_numpy()).astype(float)
    fit = C.platt(d["p"].to_numpy(), d["y"].to_numpy(), d.select(DIFFS).to_numpy().astype(float))
    p_res = fit(p_live, c25.select(DIFFS).fill_null(0).to_numpy().astype(float))
    conf = {"live": {"log_loss": C.log_loss(p_live, y25), **_summ(p_live, y25, p_live)},
            "live + differentials": {"log_loss": C.log_loss(p_res, y25), **_summ(p_res, y25, p_live)},
            "games": int(len(y25)), "gamma_fit_2007_2021": [float(v) for v in fit.coef]}
    confirmed = conf["live + differentials"]["log_loss"] <= conf["live"]["log_loss"]
    return {"table": rows, "kept": kept, "confirm_2025": conf, "confirmed_2025": confirmed,
            "adopt_proposal": bool(kept and confirmed), "coefs": coefs, "corr": corr,
            "games_missing_differentials": miss.height, "test_games": test.height}
