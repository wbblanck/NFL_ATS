"""Evaluation of proj-players-v1 on 2025 (docs/players_preregistration.md)."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine.backtest import calibration as C
from engine.backtest.holdout2025 import cbs_opens_2025
from engine.data import nflverse
from engine.features import availability as A
from engine.models import projection as P
from engine.models.margin_dist import MarginDist

H, LAM = 8, 5.0
FEATS = ["qb_backup", "off_out", "opp_def_out"]


def _ats(p, y):
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}


def v1_rates(games: pl.DataFrame, target: pl.DataFrame) -> pl.DataFrame:
    """Walk-forward v1 TD/FG rates for each (game_id, team) in target (team-game rows with season, week, team, opp, home)."""
    out = []
    for (s, w), grp in target.group_by(["season", "week"], maintain_order=True):
        r = P.fit(games, s * 25 + w, s, H, LAM)
        for x in grp.to_dicts():
            try:
                out.append({"game_id": x["game_id"], "team": x["team"],
                            "lam_td": r._lam(r.td, x["team"], x["opp"], x["home"]),
                            "lam_fg": r._lam(r.fg, x["team"], x["opp"], x["home"]), "p_xp": r.p_xp, "p_2": r.p_2})
            except ValueError:
                pass
    return pl.DataFrame(out)


def fit_offset_poisson(X, y, offset, iters=50):
    Xd = np.column_stack([np.ones(len(y)), X])
    b = np.zeros(Xd.shape[1])
    for _ in range(iters):
        mu = np.exp(offset + Xd @ b)
        H_ = Xd.T @ (Xd * mu[:, None])
        step = np.linalg.solve(H_, Xd.T @ (y - mu))
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    mu = np.exp(offset + Xd @ b)
    se = np.sqrt(np.diag(np.linalg.inv(Xd.T @ (Xd * mu[:, None]))))
    return b, se


def run():
    import nflreadpy as nfl
    sched, _ = nflverse.pull("schedules", save=False)
    rsched, _ = nflverse.regular_season_schedule(save=False)
    ts = nfl.load_team_stats(seasons=list(range(1999, 2027)))
    games = P.team_games(ts, sched)
    # ---- estimate beta on 2012-2024
    tr = games.filter(pl.col("season").is_between(2012, 2024))
    feats = A.train_features(sched, nfl.load_depth_charts(seasons=list(range(2012, 2025))),
                             nfl.load_injuries(seasons=list(range(2012, 2025))))
    rates = v1_rates(games, tr)
    d = tr.join(rates, on=["game_id", "team"]).join(feats, on=["game_id", "team"], how="left").fill_null(0)
    X = d.select(FEATS).to_numpy().astype(float)
    beta = {}
    for k in ("td", "fg"):
        b, se = fit_offset_poisson(X, d[k].to_numpy().astype(float), np.log(d[f"lam_{k}"].to_numpy()))
        beta[k] = {"intercept": b[0], **{f: b[i + 1] for i, f in enumerate(FEATS)},
                   "se": {f: se[i + 1] for i, f in enumerate(FEATS)}}
    # ---- 2025 test
    locks = rsched.filter(pl.col("season") == 2025).select(
        "game_id", "season", "week", pl.col("home_team").replace(P.FRANCHISE).alias("home"),
        pl.col("away_team").replace(P.FRANCHISE).alias("away"), "lock_utc")
    f25 = A.features_2025(sched, nfl.load_depth_charts(seasons=[2025]), nfl.load_injuries(seasons=[2025]), locks)
    g25 = games.filter(pl.col("season") == 2025)
    r25 = v1_rates(games, g25).join(f25, on=["game_id", "team"], how="left").fill_null(0)
    reg = rsched.filter(pl.col("season") == 2025, pl.col("result").is_not_null())
    opens = cbs_opens_2025(sched)
    tgt = reg.join(opens, on="game_id")
    rows = []
    for g in tgt.to_dicts():
        h, a = P.FRANCHISE.get(g["home_team"], g["home_team"]), P.FRANCHISE.get(g["away_team"], g["away_team"])
        rh = r25.filter((pl.col("game_id") == g["game_id"]) & (pl.col("team") == h))
        ra = r25.filter((pl.col("game_id") == g["game_id"]) & (pl.col("team") == a))
        if rh.height != 1 or ra.height != 1:
            continue
        rh, ra = rh.row(0, named=True), ra.row(0, named=True)
        adj = lambda r, k: r[f"lam_{k}"] * math.exp(sum(beta[k][f] * r[f] for f in FEATS))  # noqa: E731
        v1 = P.Projection(P.points_pmf(rh["lam_td"], rh["lam_fg"], rh["p_xp"], rh["p_2"]),
                          P.points_pmf(ra["lam_td"], ra["lam_fg"], ra["p_xp"], ra["p_2"]))
        v2 = P.Projection(P.points_pmf(adj(rh, "td"), adj(rh, "fg"), rh["p_xp"], rh["p_2"]),
                          P.points_pmf(adj(ra, "td"), adj(ra, "fg"), ra["p_xp"], ra["p_2"]))
        o = g["cbs_open"]
        mg = np.arange(-P.MAXP, P.MAXP + 1)
        rows.append({"game_id": g["game_id"], "open": o, "close": -g["spread_line"], "margin": g["result"],
                     "half": abs(abs(o) % 1 - 0.5) < 1e-9,
                     "p_v1": float(v1.margin_pmf[mg > -o].sum()), "p_v2": float(v2.margin_pmf[mg > -o].sum()),
                     "line_v1": v1.model_line(), "line_v2": v2.model_line(),
                     "qb_backup_any": int(rh["qb_backup"] or ra["qb_backup"]),
                     "home_qb_backup": rh["qb_backup"], "away_qb_backup": ra["qb_backup"]})
    R = pl.DataFrame(rows).filter(pl.col("margin") != -pl.col("open"))
    hist = rsched.filter(pl.col("season") <= 2024, pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    md = MarginDist("shifted").fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy())
    R = R.with_columns(pl.Series("p_live", md.sf(-R["open"].to_numpy(), R["close"].to_numpy())),
                       (pl.col("margin") > -pl.col("open")).cast(pl.Float64).alias("y"))
    out = {"beta": beta}
    for lab, x in (("half_point_opens", R.filter(pl.col("half"))), ("all_opens", R),
                   ("qb_backup_games", R.filter(pl.col("qb_backup_any") == 1))):
        y = x["y"].to_numpy()
        out[lab] = {m: {"log_loss": C.log_loss(x[f"p_{m}"].to_numpy(), y), **_ats(x[f"p_{m}"].to_numpy(), y)}
                    for m in ("live", "v1", "v2")} if x.height else None
    mar, cl = R["margin"].to_numpy(), R["close"].to_numpy()
    out["mae"] = {"market_close": float(np.mean(np.abs(mar + cl))),
                  "v1": float(np.mean(np.abs(mar + R["line_v1"].to_numpy()))),
                  "v2": float(np.mean(np.abs(mar + R["line_v2"].to_numpy())))}
    out["n_qb_backup_games"] = int(R["qb_backup_any"].sum())
    return out, R
