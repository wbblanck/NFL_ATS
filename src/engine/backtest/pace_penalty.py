"""Pace and penalties test (docs/pace_penalty_preregistration.md).

Team traits before each game from earlier games only: net penalty yards per game (committed - drawn) and
offensive plays per game, each an exponentially weighted mean (half-life 8 games) shrunk 35% toward the league
mean at a new season. They enter the same weekly re-fit logistic pick model as the adaptive test.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import polars as pl

from engine.models import adaptive as A

HALF_LIFE, SHRINK = 8.0, 0.35


def team_games(ts: pl.DataFrame, sched: pl.DataFrame) -> pl.DataFrame:
    """One row per team-game with penalty yards committed/drawn and offensive plays, in kickoff order."""
    from engine.data import nflverse
    from engine.features.efficiency_v6 import with_order_time
    t = ts.select("game_id", "season", pl.col("team").replace(A.FRANCHISE if hasattr(A, "FRANCHISE") else {}),
                  "opponent_team", "penalty_yards",
                  (pl.col("attempts").fill_null(0) + pl.col("carries").fill_null(0)
                   + pl.col("sacks_suffered").fill_null(0)).alias("plays"))
    opp = t.select("game_id", pl.col("team").alias("opponent_team"), pl.col("penalty_yards").alias("pen_drawn"))
    t = t.join(opp, on=["game_id", "opponent_team"], how="left")
    k = with_order_time(nflverse.with_kickoff(sched)).select("game_id", "kickoff_utc")
    return t.join(k, on="game_id").with_columns(
        (pl.col("penalty_yards") - pl.col("pen_drawn")).alias("net_pen")).sort("kickoff_utc", "game_id")


def traits(tg: pl.DataFrame) -> dict[tuple[str, str], tuple[float, float]]:
    """(game_id, team) -> (net penalty yards/game, plays/game) known before that game."""
    alpha = 1 - 0.5 ** (1 / HALF_LIFE)
    lg_pen, lg_pace = 0.0, 63.0
    st: dict[str, list] = {}
    seen: dict[str, int] = {}
    season_vals: dict[int, list] = defaultdict(list)
    out = {}
    for r in tg.iter_rows(named=True):
        t, s = A._f(r["team"]), r["season"]
        if s - 1 in season_vals and season_vals[s - 1]:
            lg_pace = float(np.mean(season_vals[s - 1]))
        if t not in st:
            st[t] = [lg_pen, lg_pace]
        elif seen.get(t) != s:
            st[t] = [(1 - SHRINK) * st[t][0] + SHRINK * lg_pen, (1 - SHRINK) * st[t][1] + SHRINK * lg_pace]
        seen[t] = s
        out[(r["game_id"], t)] = (st[t][0], st[t][1])
        if r["net_pen"] is not None:
            st[t][0] += alpha * (r["net_pen"] - st[t][0])
        if r["plays"]:
            st[t][1] += alpha * (r["plays"] - st[t][1])
            season_vals[s].append(r["plays"])
    return out


def with_features(d: pl.DataFrame, tr: dict, sched: pl.DataFrame) -> pl.DataFrame:
    """Adds pen_edge and pace_fav (pace standardized with the mean/sd of seasons before each game's season)."""
    ht = dict(zip(sched["game_id"].to_list(), zip(sched["home_team"].to_list(), sched["away_team"].to_list())))
    pen, pace = [], []
    for g in d["game_id"].to_list():
        h, a = (A._f(x) for x in ht[g])
        th, ta = tr.get((g, h)), tr.get((g, a))
        pen.append(None if th is None or ta is None else (ta[0] - th[0]) / 10.0)
        pace.append(None if th is None or ta is None else th[1] + ta[1])
    d = d.with_columns(pl.Series("pen_edge", pen, dtype=pl.Float64), pl.Series("pace_sum", pace, dtype=pl.Float64))
    z = np.full(d.height, np.nan)
    s = d["season"].to_numpy()
    ps = d["pace_sum"].to_numpy()
    for yr in np.unique(s):
        past = ps[s < yr]
        past = past[~np.isnan(past)]
        mu, sd = (float(past.mean()), float(past.std())) if past.size > 50 else (float(np.nanmean(ps)), float(np.nanstd(ps)))
        z[s == yr] = (ps[s == yr] - mu) / sd
    fav = np.where(d["line"].to_numpy() < 0, 1.0, -1.0)
    return d.with_columns(pl.Series("pace_fav", z * fav)).filter(pl.col("pen_edge").is_not_null())


def design(d: pl.DataFrame) -> np.ndarray:
    p = np.clip(d["p_live"].to_numpy(), 1e-4, 1 - 1e-4)
    return np.column_stack([np.ones(d.height), np.log(p / (1 - p)), d["pen_edge"].to_numpy(), d["pace_fav"].to_numpy()])


def walk(d: pl.DataFrame, H: float, lam: float, lo: int, hi: int):
    X, y = design(d), d["y"].to_numpy()
    s, w = d["season"].to_numpy(), d["week"].to_numpy()
    t = s * 100 + w
    out = np.full(d.height, np.nan)
    coefs = []
    for key in np.unique(t[(s >= lo) & (s <= hi)]):
        tr = t < key
        wt = np.ones(tr.sum()) if math.isinf(H) else 0.5 ** (((key // 100) - s[tr]) / H)
        b = A.fit_logit(X[tr], y[tr], wt, lam)
        out[t == key] = 1 / (1 + np.exp(-(X[t == key] @ b)))
        coefs.append({"season": int(key // 100), "week": int(key % 100), "b": [float(v) for v in b]})
    return out, coefs


def pooled_weights(d: pl.DataFrame, lo: int, hi: int) -> dict:
    """Unpenalized fit on lo..hi with standard errors (reported only)."""
    m = (d["season"] >= lo) & (d["season"] <= hi)
    X, y = design(d.filter(m)), d.filter(m)["y"].to_numpy()
    b = A.fit_logit(X, y, np.ones(len(y)), 0.0)
    p = 1 / (1 + np.exp(-(X @ b)))
    cov = np.linalg.inv((X * (p * (1 - p))[:, None]).T @ X)
    names = ["intercept", "live_logit", "pen_edge", "pace_fav"]
    return {n: {"b": float(bi), "se": float(math.sqrt(cov[i, i]))} for i, (n, bi) in enumerate(zip(names, b))}
