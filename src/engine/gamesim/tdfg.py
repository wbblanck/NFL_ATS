"""Touchdown/field-goal score model (nfl-betting-model docs/batch3_preregistration.md, D2 + M1) and the pregame expected starting QB (G1).

Each team independently: touchdowns T ~ NB(lam_T, theta_T), field goals F ~ Poisson(lam_F), safeties S ~ Poisson(s);
each touchdown adds 6 plus a conversion worth 0/1/2 with probabilities p. Points = 6T + conversions + 3F + 2S.
lam_T = c_T * L * exp(+-b_T d/100), lam_F = c_F * L * exp(+-b_F d/100), L = league scoring level, d = Elo gap.
"""
from __future__ import annotations

import math
from math import lgamma

import numpy as np
import polars as pl

from .elo import MAXPTS
from .kalman import nelder_mead

NT, NF, NS = 20, 15, 5  # truncation of touchdown, field-goal and safety counts (mass beyond is negligible)


def nb_counts(mu, theta, n):
    """(G, n+1) NB probabilities of 0..n; theta = inf gives Poisson."""
    k = np.arange(n + 1)
    mu = np.asarray(mu, float)[:, None]
    if not np.isfinite(theta):
        return np.exp(k * np.log(mu) - mu - np.array([lgamma(i + 1) for i in k]))
    lc = np.array([lgamma(i + theta) - lgamma(theta) - lgamma(i + 1) for i in k])
    return np.exp(lc + theta * np.log(theta / (theta + mu)) + k * np.log(mu / (theta + mu)))


def td_points_table(p):
    """Row n: distribution of 6n + conversions (points 0..MAXPTS) given n touchdowns."""
    conv = np.array([1.0])
    rows = np.zeros((NT + 1, MAXPTS + 1))
    for n in range(NT + 1):
        if n:
            conv = np.convolve(conv, p)
        seg = conv[: max(0, MAXPTS + 1 - 6 * n)]
        rows[n, 6 * n: 6 * n + len(seg)] = seg
    return rows


def points_pmf(lt, theta_t, lf, s, p):
    """(G, MAXPTS+1) distribution of one team's points."""
    pt = nb_counts(lt, theta_t, NT) @ td_points_table(p)
    pf = np.zeros((len(pt), MAXPTS + 1))
    pf[:, 0: 3 * NF + 1: 3] = nb_counts(lf, math.inf, NF)
    ps = np.zeros(MAXPTS + 1)
    ps[0: 2 * NS + 1: 2] = nb_counts([s], math.inf, NS)[0]
    out = np.zeros_like(pt)
    for i in range(len(pt)):
        out[i] = np.convolve(np.convolve(pt[i], pf[i])[: MAXPTS + 1], ps)[: MAXPTS + 1]
    return out


def rates(d, level, c, b):
    x = b * np.asarray(d, float) / 100.0
    base = c * np.asarray(level, float)
    return base * np.exp(x), base * np.exp(-x)


def game_pmfs(d, level, k):
    """Home and away points distributions from constants k (c_T, b_T, theta_T, c_F, b_F, s, p)."""
    th, ta = rates(d, level, k["c_T"], k["b_T"])
    fh, fa = rates(d, level, k["c_F"], k["b_F"])
    p = np.asarray(k["p"], float)
    return points_pmf(th, k["theta_T"], fh, k["s"], p), points_pmf(ta, k["theta_T"], fa, k["s"], p)


# ---------- fitting
def _nll_nb(y, mu, th):
    y = np.asarray(y, float)
    if not np.isfinite(th):
        return float(-(y * np.log(mu) - mu - np.array([lgamma(v + 1) for v in y])).sum())
    lg = np.array([lgamma(v + th) - lgamma(th) - lgamma(v + 1) for v in y])
    return float(-(lg + th * np.log(th / (th + mu)) + y * np.log(mu / (th + mu))).sum())


def fit_counts(d, level, yh, ya, nb=True):
    """ML for (c, b[, theta]) of a count with mean c*L*exp(+-b d/100). Returns dict."""
    dd = np.r_[np.asarray(d, float), -np.asarray(d, float)]
    lv = np.r_[np.asarray(level, float), np.asarray(level, float)]
    y = np.r_[yh, ya].astype(float)
    c0 = y.mean() / lv.mean()

    def f(x):
        c, b = math.exp(x[0]), x[1]
        th = math.exp(x[2]) if nb else math.inf
        return _nll_nb(y, c * lv * np.exp(b * dd / 100.0), th)
    x0 = [math.log(c0), 0.1] + ([math.log(20.0)] if nb else [])
    x, v = nelder_mead(f, x0, [0.1, 0.05] + ([0.5] if nb else []), iters=600, tol=1e-7)
    out = {"c": math.exp(x[0]), "b": float(x[1]), "nll": float(v)}
    if nb:
        out["theta"] = math.exp(x[2])
    return out


# ---------- counts from play-by-play
def counts(pbp: pl.DataFrame) -> pl.DataFrame:
    """Per game: home/away touchdowns, conversion points split (ones, twos), made field goals, safeties."""
    p = pbp.filter(pl.col("season_type") == "REG")
    side = lambda col: pl.when(pl.col(col) == pl.col("home_team")).then(pl.lit("home")).otherwise(pl.lit("away"))  # noqa: E731
    td = p.filter(pl.col("touchdown") == 1, pl.col("td_team").is_not_null()).with_columns(side("td_team").alias("side")) \
        .group_by("game_id", "side").agg(pl.len().alias("T"))
    fg = p.filter(pl.col("field_goal_result") == "made").with_columns(side("posteam").alias("side")) \
        .group_by("game_id", "side").agg(pl.len().alias("F"))
    sf = p.filter(pl.col("safety") == 1, pl.col("defteam").is_not_null()).with_columns(side("defteam").alias("side")) \
        .group_by("game_id", "side").agg(pl.len().alias("S"))
    x1 = p.filter(pl.col("extra_point_result") == "good").with_columns(side("posteam").alias("side")) \
        .group_by("game_id", "side").agg(pl.len().alias("C1"))
    x2 = p.filter(pl.col("two_point_conv_result") == "success").with_columns(side("posteam").alias("side")) \
        .group_by("game_id", "side").agg(pl.len().alias("C2"))
    base = p.select("game_id").unique().join(pl.DataFrame({"side": ["home", "away"]}), how="cross")
    for t in (td, fg, sf, x1, x2):
        base = base.join(t, on=["game_id", "side"], how="left")
    base = base.fill_null(0)
    h = base.filter(pl.col("side") == "home").drop("side")
    a = base.filter(pl.col("side") == "away").drop("side")
    return h.join(a, on="game_id", suffix="_a").rename({c: f"{c}_h" for c in ("T", "F", "S", "C1", "C2")})


# ---------- G1: expected starter from the previous game and the final injury report
def expected_starters(sched: pl.DataFrame, qg: pl.DataFrame, inj: pl.DataFrame, franchise: dict, day_fn) -> pl.DataFrame:
    """Returns sched (REG) with home_qb_id / away_qb_id replaced by the pregame expected starter. Week-1 games (no
    previous game that season) keep the recorded starter; the evaluation starts at week 2."""
    out_ids = set()
    for s, w, t, g, st in zip(inj["season"], inj["week"], inj["team"], inj["gsis_id"], inj["report_status"]):
        if st in ("Out", "Doubtful") and g:
            out_ids.add((int(s), int(w), franchise.get(t, t), g))
    games = {}
    for t, s, day, q, n in zip(qg["team"], qg["season"], qg["day"], qg["qb"], qg["n"]):
        games.setdefault((t, int(s)), {}).setdefault(day, {})
        games[(t, int(s))][day][q] = games[(t, int(s))][day].get(q, 0) + n
    reg = sched.filter(pl.col("game_type") == "REG")
    cols = {"home_qb_id": [], "away_qb_id": []}
    for r in reg.iter_rows(named=True):
        day = day_fn(r["gameday"])
        for side in ("home", "away"):
            team = franchise.get(r[f"{side}_team"], r[f"{side}_team"])
            cols[f"{side}_qb_id"].append(pick(games.get((team, int(r["season"])), {}), day, int(r["season"]),
                                              int(r["week"]), team, out_ids, r[f"{side}_qb_id"]))
    return reg.with_columns(pl.Series("home_qb_id", cols["home_qb_id"], pl.String),
                            pl.Series("away_qb_id", cols["away_qb_id"], pl.String))


def pick(team_games: dict, day: int, season: int, week: int, team: str, out_ids: set, recorded):
    prev = [d for d in team_games if d < day]
    if not prev:
        return recorded
    last = team_games[max(prev)]
    e = top_qb(last)
    if (season, week, team, e) not in out_ids:
        return e
    tot: dict = {}
    for d in prev:
        for q, n in team_games[d].items():
            if q != e:
                tot[q] = tot.get(q, 0) + n
    return top_qb(tot) if tot else "UNKNOWN"


def top_qb(counts: dict):
    """The QB with the most dropbacks; a tie goes to the smallest id, so the result never depends on row order.
    (Audit 2026-11-09: `max(counts, key=counts.get)` broke ties by dict insertion order, which followed an
    unordered group_by, so the batch 6 reproduce check moved by up to 0.005 MAE from run to run.)"""
    return min(counts, key=lambda q: (-counts[q], q))
