"""V1 team factors: opponent-adjusted version of teams.factors (docs/simulator_refit_v1_preregistration.md).

Same recency weights, season prior and shrinkage as teams.factors. The one change: each factor is corrected for the
strength of the opponents faced. For an offensive factor f the raw estimate is shifted by

    - s * m,   m = sum_i w_i n_i dF(opp_i) / sum_i w_i n_i,   s = sum_i w_i n_i / (sum_i w_i n_i + k * n_league)

where dF(opp_i) is the opponent's defensive factor f as it stood before game i (itself opponent-adjusted, so no
look-ahead), n_i the game's trials (or count, for yards), w_i the recency weight. Defensive factors use the
opponents' offensive factors the same way. s is the data share of the shrunk estimate, so the correction fades to
zero where the prior dominates. The pass-rate-over-expected factor (oproe) is left as it is. Research only.
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from .teams import KEYS, RATES, YARDS, _lo


def factors_adj(gs: pl.DataFrame, lg: dict, h: float, k: float, r: float) -> pl.DataFrame:
    opp = gs.select(*KEYS, pl.col("team").alias("opp"), *[pl.col(c).alias("d_" + c) for c in
                    ("sack", "db", "scr", "nsdb", "int", "att", "comp", "natt", "comp_y", "run", "run_y")])
    x = gs.join(opp, on=[*KEYS, "opp"], how="left")
    rows = []
    prior: dict = {}
    allf = list(RATES) + list(YARDS)
    for season in sorted(x["season"].unique().to_list()):
        s = x.filter(pl.col("season") == season)
        hist: dict = {}

        def est(team):
            pr = prior.get(team, {})
            xs = hist.get(team, [])
            n = len(xs)
            w = np.array([0.5 ** ((n - 1 - i) / h) for i in range(n)]) if n else np.zeros(0)
            out = {}
            for side, pre, oside in (("o", "", "d"), ("d", "d_", "o")):
                for f in allf:
                    a, b = RATES[f] if f in RATES else YARDS[f]
                    nums = np.array([g[pre + a] or 0.0 for g in xs], float)
                    dens = np.array([g[pre + b] or 0.0 for g in xs], float)
                    num, den = float((w * nums).sum()), float((w * dens).sum())
                    kn = k * lg[f + "_n"]
                    if f in RATES:
                        p0 = 1 / (1 + math.exp(-(_lo(lg[f]) + pr.get(side + f, 0.0))))
                        raw = _lo((num + kn * p0) / (den + kn)) - _lo(lg[f])
                    else:
                        y0 = lg[f] * math.exp(pr.get(side + f, 0.0))
                        raw = math.log((num + kn * y0) / (den + kn) / lg[f])
                    if den > 0:
                        oppf = np.array([g["opp_pre"].get(oside + f, 0.0) for g in xs], float)
                        m = float((w * dens * oppf).sum() / den)
                        raw -= den / (den + kn) * m
                    out[side + f] = raw
            a_ = [(_lo(g["p_obs"] / g["p_n"]) - _lo(g["p_exp"] / g["p_n"])) if g["p_n"] else 0.0 for g in xs]
            out["oproe"] = (sum(wi * ai for wi, ai in zip(w, a_)) + k * pr.get("oproe", 0.0)) / (w.sum() + k)
            out["dproe"] = 0.0
            return out

        for week in sorted(s["week"].unique().to_list()):
            g = s.filter(pl.col("week") == week)
            teams = g["team"].to_list()
            pre = {t: est(t) for t in teams}
            for row in g.iter_rows(named=True):
                rows.append({"season": season, "week": week, "game_id": row["game_id"], "team": row["team"], **pre[row["team"]]})
            for row in g.iter_rows(named=True):
                row = dict(row)
                row["opp_pre"] = pre.get(row["opp"], {})
                hist.setdefault(row["team"], []).append(row)
        prior = {t: {kk: r * v for kk, v in est(t).items()} for t in hist}
    return pl.DataFrame(rows)
