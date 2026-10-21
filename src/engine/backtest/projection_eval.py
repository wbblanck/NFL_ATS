"""Evaluation of proj-poisson-v1 (docs/projection_preregistration.md)."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine import config
from engine.backtest import calibration as C
from engine.backtest.common import ats as _ats
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.data import nflverse, sbro
from engine.models import projection as P
from engine.models.margin_dist import MarginDist

GRID_H, GRID_L = (8, 16, 32), (1, 5, 20)


def data():
    import nflreadpy as nfl
    sched, _ = nflverse.pull("schedules", save=False)
    ts = nfl.load_team_stats(seasons=list(range(1999, 2027)))
    return sched, P.team_games(ts, sched)


def project_games(games: pl.DataFrame, target: pl.DataFrame, H, lam) -> list[P.Projection]:
    """target: game_id, season, week, home_team, away_team. Refit once per (season, week)."""
    out = {}
    for (s, w), grp in target.group_by(["season", "week"], maintain_order=True):
        r = P.fit(games, s * 25 + w, s, H, lam)
        for row in grp.to_dicts():
            try:
                out[row["game_id"]] = P.project(r, row["home_team"], row["away_team"])
            except ValueError:
                out[row["game_id"]] = None
    return [out.get(g) for g in target["game_id"].to_list()]


def tune(sched, games):
    tgt = sched.filter(pl.col("game_type") == "REG", pl.col("season").is_between(2002, 2006),
                       pl.col("result").is_not_null(), pl.col("result") != 0)
    y = (tgt["result"].to_numpy() > 0).astype(float)
    res = []
    for H in GRID_H:
        for lam in GRID_L:
            pr = project_games(games, tgt, H, lam)
            p = np.array([x.margin_pmf[P.MAXP + 1:].sum() / (1 - x.margin_pmf[P.MAXP]) if x else 0.5 for x in pr])
            res.append({"H": H, "lam": lam, "log_loss": C.log_loss(p, y)})
    t = pl.DataFrame(res).sort("log_loss")
    return t, int(t["H"][0]), float(t["lam"][0])


def run():
    sched, games = data()
    tune_tbl, H, lam = tune(sched, games)
    sb = sbro.match_schedule(sbro.load_all(config.ROOT / "data" / "raw" / "sbro"), sched) \
        .select("game_id", pl.col("open_home_spread").alias("open"))
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    tgt = reg.filter(pl.col("season").is_between(2007, 2021)).join(sb, on="game_id").filter(
        pl.col("open").is_not_null(), pl.col("result") != -pl.col("open"))
    pr = project_games(games, tgt, H, lam)
    ok = np.array([x is not None for x in pr])
    tgt, pr = tgt.filter(pl.Series(ok)), [x for x in pr if x is not None]
    y = (tgt["result"].to_numpy() > -tgt["open"].to_numpy()).astype(float)
    p_proj = np.array([x.p_home_cover(o) if abs(abs(o) % 1 - 0.5) < 1e-9 else
                       x.margin_pmf[np.arange(-P.MAXP, P.MAXP + 1) > -o].sum() for x, o in zip(pr, tgt["open"].to_numpy())])
    # live model on same games (walk-forward by season)
    p_live = np.zeros(tgt.height)
    for s in range(2007, 2022):
        m = (tgt["season"] == s).to_numpy()
        hist = reg.filter(pl.col("season") < s)
        md = MarginDist("shifted").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy())
        p_live[m] = md.sf(-tgt.filter(pl.col("season") == s)["open"].to_numpy(),
                          -tgt.filter(pl.col("season") == s)["spread_line"].to_numpy())
    model_line = np.array([x.model_line() for x in pr])
    margin = tgt["result"].to_numpy()
    close = -tgt["spread_line"].to_numpy()
    a_proj, a_live = _ats(p_proj, y), _ats(p_live, y)
    z = (a_proj["win_rate"] - a_live["win_rate"]) / math.sqrt(a_proj["se"] ** 2 + a_live["se"] ** 2)
    big = np.abs(model_line - close) >= 3
    out = {"tuning": tune_tbl, "H": H, "lam": lam, "n": tgt.height,
           "proj": {"log_loss": C.log_loss(p_proj, y), **a_proj},
           "live": {"log_loss": C.log_loss(p_live, y), **a_live},
           "z_proj_vs_live": z,
           "switch": z >= 1.96 and C.log_loss(p_proj, y) < C.log_loss(p_live, y),
           "mae_model_margin": float(np.mean(np.abs(margin + model_line))),
           "mae_market_close": float(np.mean(np.abs(margin + close))),
           "big_disagree": {"n": int(big.sum()), **_ats(p_proj[big], y[big])} if big.any() else None,
           "agree_rate": float(np.mean((p_proj > 0.5) == (p_live > 0.5)))}
    # dispersion diagnostic
    out["dispersion"] = {"td_mean": float(games["td"].mean()), "td_var": float(games["td"].var()),
                         "fg_mean": float(games["fg"].mean()), "fg_var": float(games["fg"].var())}
    # 2025 confirmation
    g25 = reg.filter(pl.col("season") == 2025).join(cbs_opens_2025(sched), on="game_id")
    g25 = g25.filter(pl.col("cbs_open").map_elements(lambda v: abs(abs(v) % 1 - 0.5) < 1e-9, return_dtype=pl.Boolean))
    pr25 = project_games(games, g25, H, lam)
    y25 = (g25["result"].to_numpy() > -g25["cbs_open"].to_numpy()).astype(float)
    p25 = np.array([x.p_home_cover(o) if x else 0.5 for x, o in zip(pr25, g25["cbs_open"].to_numpy())])
    hist = reg.filter(pl.col("season") <= 2024)
    md = MarginDist("shifted").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy())
    pl25 = md.sf(-g25["cbs_open"].to_numpy(), -g25["spread_line"].to_numpy())
    out["confirm_2025"] = {"proj": {"log_loss": C.log_loss(p25, y25), **_ats(p25, y25)},
                           "live": {"log_loss": C.log_loss(pl25, y25), **_ats(pl25, y25)}}
    return out
