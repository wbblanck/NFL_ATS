"""Team factors for the game simulator (nfl-betting-model docs/gamesim_preregistration.md).

Per team-game counts from play-by-play, then pre-game factors from the team's earlier games only: recency-weighted
(half-life h games) within the season, plus a prior worth k games equal to last season's final factor times r.
Factors are log-odds shifts for rates and log scales for yards, relative to the fit seasons' league values. Offense
and defense are estimated separately and not adjusted for opponents (disclosed).
"""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from . import league as L

# factor -> (success column, trials column) for rates; (yards column, count column) for yards
RATES = {"sack": ("sack", "db"), "scr": ("scr", "nsdb"), "int": ("int", "att"), "comp": ("comp", "natt")}
YARDS = {"ypc": ("comp_y", "comp"), "ypr": ("run_y", "run")}
KEYS = ["season", "week", "game_id"]


FRANCHISE = {"STL": "LA", "SD": "LAC", "OAK": "LV", "JAC": "JAX", "LAR": "LA"}


def game_stats(pbp: pl.DataFrame, T: dict) -> pl.DataFrame:
    """One row per team-game: offensive counts (the defense's are the opponent's offensive counts)."""
    s = L.scrimmage(pbp).filter(~pl.col("is_pen")).with_columns(
        pl.col("posteam").replace(FRANCHISE), pl.col("defteam").replace(FRANCHISE))
    sk = (pl.col("sack").fill_null(0) == 1)
    sc = (pl.col("qb_scramble").fill_null(0) == 1) & ~sk
    it = (pl.col("interception").fill_null(0) == 1) & ~sk & ~sc
    cp = (pl.col("complete_pass").fill_null(0) == 1) & ~sk & ~sc & ~it
    d = s.with_columns(sk.alias("sk"), sc.alias("sc"), it.alias("it"), cp.alias("cp"))
    # expected pass probability for downs 1-3 (league table + field-position shift)
    n3 = d.filter(pl.col("down") <= 3)
    dn = n3["down"].to_numpy().astype(int) - 1
    pp = np.array(T["pass_prob"])[dn, L.b_togo(n3["ydstogo"].to_numpy()), L.b_sdiff(n3["score_differential"].to_numpy()),
                                  L.b_time(n3["game_seconds_remaining"].to_numpy(), n3["half_seconds_remaining"].to_numpy(),
                                           n3["qtr"].to_numpy())]
    lg = np.log(pp / (1 - pp)) + np.array(T["pass_yl_shift"])[dn, L.b_yard(n3["yardline_100"].to_numpy())]
    n3 = n3.with_columns(pl.Series("xp", 1 / (1 + np.exp(-lg))))
    pe = n3.group_by(*KEYS, "posteam").agg(pl.col("is_db").sum().alias("p_obs"), pl.col("xp").sum().alias("p_exp"),
                                            pl.len().alias("p_n"))
    g = d.group_by(*KEYS, "posteam", "defteam").agg(
        pl.col("is_db").sum().alias("db"), pl.col("sk").sum().alias("sack"), pl.col("sc").sum().alias("scr"),
        pl.col("it").sum().alias("int"), pl.col("cp").sum().alias("comp"),
        (pl.col("is_db") & ~pl.col("sk") & ~pl.col("sc")).sum().alias("att"),
        pl.col("yards_gained").filter(pl.col("cp")).sum().alias("comp_y"),
        pl.col("is_run").sum().alias("run"), pl.col("yards_gained").filter(pl.col("is_run") | pl.col("sc")).sum().alias("run_y"),
        pl.col("sc").sum().alias("scr2"))
    g = g.with_columns((pl.col("db") - pl.col("sack")).alias("nsdb"), (pl.col("att") - pl.col("int")).alias("natt"),
                       (pl.col("run") + pl.col("scr2")).alias("run")).drop("scr2")
    g = g.join(pe, on=[*KEYS, "posteam"], how="left").rename({"posteam": "team", "defteam": "opp"})
    return g.sort(KEYS)


def league_rates(gs: pl.DataFrame) -> dict:
    out = {}
    for f, (a, b) in {**RATES, **YARDS}.items():
        out[f] = float(gs[a].sum() / gs[b].sum())
        out[f + "_n"] = float(gs[b].mean())
    return out


def _lo(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


FACT = list(RATES) + list(YARDS) + ["proe"]


def factors(gs: pl.DataFrame, lg: dict, h: float, k: float, r: float) -> pl.DataFrame:
    """Pre-game offense and defense factors for every team-game in gs (first season = history only, zero prior)."""
    opp = gs.select(*KEYS, pl.col("team").alias("opp"), *[pl.col(c).alias("d_" + c) for c in
                    ("sack", "db", "scr", "nsdb", "int", "att", "comp", "natt", "comp_y", "run", "run_y")])
    x = gs.join(opp, on=[*KEYS, "opp"], how="left")
    rows = []
    prior: dict = {}
    for season in sorted(x["season"].unique().to_list()):
        s = x.filter(pl.col("season") == season)
        hist: dict = {}

        def est(team):
            pr = prior.get(team, {})
            xs = hist.get(team, [])
            n = len(xs)
            w = np.array([0.5 ** ((n - 1 - i) / h) for i in range(n)]) if n else np.zeros(0)
            out = {}
            for side, pre in (("o", ""), ("d", "d_")):
                for f, (a, b) in RATES.items():
                    num = sum(wi * g[pre + a] for wi, g in zip(w, xs))
                    den = sum(wi * g[pre + b] for wi, g in zip(w, xs))
                    p0 = 1 / (1 + math.exp(-(_lo(lg[f]) + pr.get(side + f, 0.0))))
                    kn = k * lg[f + "_n"]
                    out[side + f] = _lo((num + kn * p0) / (den + kn)) - _lo(lg[f])
                for f, (a, b) in YARDS.items():
                    num = sum(wi * g[pre + a] for wi, g in zip(w, xs))
                    den = sum(wi * g[pre + b] for wi, g in zip(w, xs))
                    y0 = lg[f] * math.exp(pr.get(side + f, 0.0))
                    kn = k * lg[f + "_n"]
                    out[side + f] = math.log((num + kn * y0) / (den + kn) / lg[f])
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
                hist.setdefault(row["team"], []).append(row)
        prior = {t: {kk: r * v for kk, v in est(t).items()} for t in hist}
    return pl.DataFrame(rows)
