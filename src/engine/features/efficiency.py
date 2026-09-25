"""Opponent-adjusted, recency-weighted EPA/play ratings (group 3).

Ratings before a game use only earlier games:
  adj_off  = off_epa_pp  - opp_def_rating_pre      (def rating = EPA/play allowed, above avg = bad)
  adj_def  = opp_off_epa_pp - opp_off_rating_pre
  rating  <- rating + alpha * (adj - rating),  alpha = 1 - 0.5**(1/half_life)
  at each new season: rating *= (1 - shrink)
"""
from __future__ import annotations

from collections import defaultdict

import polars as pl


def game_epa(team_stats: pl.DataFrame) -> pl.DataFrame:
    ts = team_stats.filter(pl.col("season_type") == "REG").select(
        "season", "week", "team", pl.col("opponent_team").alias("opp"),
        ((pl.col("passing_epa").fill_null(0) + pl.col("rushing_epa").fill_null(0))
         / (pl.col("attempts").fill_null(0) + pl.col("carries").fill_null(0)
            + pl.col("sacks_suffered").fill_null(0))).alias("off_epa_pp"))
    opp = ts.select("season", "week", pl.col("team").alias("opp"), pl.col("off_epa_pp").alias("opp_off_epa_pp"))
    return ts.join(opp, on=["season", "week", "opp"], how="left")


def ratings(games: pl.DataFrame, half_life: float = 6.0, shrink: float = 0.5) -> pl.DataFrame:
    """games: season, week, team, opp, off_epa_pp, opp_off_epa_pp.
    Returns season, week, team, off_pre, def_pre (ratings BEFORE that week's game)."""
    alpha = 1 - 0.5 ** (1 / half_life)
    off, de = defaultdict(float), defaultdict(float)
    season_seen = {}
    out = []
    for (season, week), wk in games.sort("season", "week").group_by(["season", "week"], maintain_order=True):
        rows = wk.to_dicts()
        for r in rows:  # season rollover shrink, once per team
            t = r["team"]
            if season_seen.get(t) != season:
                if t in season_seen:
                    off[t] *= (1 - shrink)
                    de[t] *= (1 - shrink)
                season_seen[t] = season
        pre = {r["team"]: (off[r["team"]], de[r["team"]]) for r in rows}
        for r in rows:
            out.append({"season": season, "week": week, "team": r["team"],
                        "off_pre": pre[r["team"]][0], "def_pre": pre[r["team"]][1]})
        for r in rows:  # update with opponent-adjusted values using PRE-game opponent ratings
            t, o = r["team"], r["opp"]
            o_off, o_def = pre.get(o, (off[o], de[o]))
            if r["off_epa_pp"] is not None:
                off[t] += alpha * ((r["off_epa_pp"] - o_def) - off[t])
            if r["opp_off_epa_pp"] is not None:
                de[t] += alpha * ((r["opp_off_epa_pp"] - o_off) - de[t])
    return pl.DataFrame(out)


def efficiency_feature(sched: pl.DataFrame, rt: pl.DataFrame) -> pl.DataFrame:
    reg = sched.filter(pl.col("game_type") == "REG").select("game_id", "season", "week", "home_team", "away_team")
    h = rt.rename({"team": "home_team", "off_pre": "h_off", "def_pre": "h_def"})
    a = rt.rename({"team": "away_team", "off_pre": "a_off", "def_pre": "a_def"})
    j = reg.join(h, on=["season", "week", "home_team"], how="left").join(a, on=["season", "week", "away_team"], how="left")
    return j.select("game_id", ((pl.col("h_off") - pl.col("h_def")) - (pl.col("a_off") - pl.col("a_def")))
                    .fill_null(0.0).alias("net_eff_diff"))
