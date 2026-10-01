"""Pre-game projection of a player's prop stat (docs/projection_props_declaration.md).

    projection = usage x team_factor^a x opp_factor^b

- usage: the player's exponentially weighted mean of the stat over his EARLIER games (any season; half-life
  HALF_LIFE games). The current game never enters.
- team_factor: the team's implied points from the closing spread and total, over the season's average implied
  points. (Closing lines are known at kickoff, before the props settle.)
- opp_factor: what the opponent's defense allowed to this position group in its earlier games (weighted the same
  way), over the league average for that position, shrunk toward 1 by SHRINK games, clipped to [0.5, 2].
- a, b: fitted per market on a training season by least squares on a grid.
Only players with at least MIN_GAMES earlier games get a projection. Known limit: nflverse player stats have no
row for a game a player played without recording a stat, so those zeros are missing from usage (slightly high).
"""
from __future__ import annotations

import numpy as np
import polars as pl

from engine.backtest.props import STAT

HALF_LIFE = 4.0
SHRINK = 4.0
MIN_GAMES = 3
GRID = np.round(np.arange(0.0, 1.51, 0.25), 2)
POS_GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE"}


def stats(seasons: list[int]) -> pl.DataFrame:
    import nflreadpy as nfl

    s = nfl.load_player_stats(seasons=seasons).filter(pl.col("season_type") == "REG")
    return (s.with_columns(pl.col("position").replace_strict(POS_GROUP, default=None).alias("pos"))
            .filter(pl.col("pos").is_not_null())
            .select("player_id", "season", "week", "team", "opponent_team", "pos", *[e.alias(m) for m, e in STAT.items()])
            .with_columns((pl.col("season") * 100 + pl.col("week")).alias("t")).sort("t"))


def implied_points(seasons: list[int]) -> pl.DataFrame:
    import nflreadpy as nfl

    g = nfl.load_schedules(seasons=seasons).filter(pl.col("game_type") == "REG", pl.col("spread_line").is_not_null(),
                                                   pl.col("total_line").is_not_null())
    # nflverse spread_line > 0 means the home team is favored by that many points
    rows = pl.concat([
        g.select("season", "week", pl.col("home_team").alias("team"),
                 ((pl.col("total_line") + pl.col("spread_line")) / 2).alias("imp")),
        g.select("season", "week", pl.col("away_team").alias("team"),
                 ((pl.col("total_line") - pl.col("spread_line")) / 2).alias("imp"))])
    return rows.with_columns((pl.col("imp") / pl.col("imp").mean().over("season")).alias("team_factor"))


def _ewm_prior(col: str, by: str) -> pl.Expr:
    """Weighted mean of `col` over strictly earlier rows of the group (rows sorted by time)."""
    return pl.col(col).shift(1).ewm_mean(half_life=HALF_LIFE, ignore_nulls=True).over(by)


def features(st: pl.DataFrame, imp: pl.DataFrame) -> pl.DataFrame:
    markets = list(STAT)
    f = st.with_columns(*[_ewm_prior(m, "player_id").alias(f"u_{m}") for m in markets],
                        pl.col("t").cum_count().over("player_id").alias("n_prior"))
    f = f.with_columns(pl.col("n_prior") - 1)
    # opponent allowance by position group: per defense-game totals, then weighted over its earlier games
    allowed = (st.group_by("opponent_team", "pos", "t")
               .agg(*[pl.col(m).sum() for m in markets]).sort("t")
               .with_columns(*[_ewm_prior(m, ["opponent_team", "pos"]).alias(f"a_{m}") for m in markets],
                             (pl.col("t").cum_count().over(["opponent_team", "pos"]) - 1).alias("a_n")))
    league = allowed.group_by("pos").agg(*[pl.col(m).mean().alias(f"l_{m}") for m in markets])
    allowed = allowed.join(league, on="pos").with_columns(
        *[((pl.col("a_n") * (pl.col(f"a_{m}") / pl.col(f"l_{m}")).fill_null(1.0) + SHRINK)
           / (pl.col("a_n") + SHRINK)).clip(0.5, 2.0).alias(f"o_{m}") for m in markets])
    f = f.join(allowed.select("opponent_team", "pos", "t", *[f"o_{m}" for m in markets]),
               on=["opponent_team", "pos", "t"], how="left")
    return f.join(imp.select("season", "week", "team", "team_factor"), on=["season", "week", "team"], how="left")


def long(f: pl.DataFrame) -> pl.DataFrame:
    """One row per player-game-market with usage, factors and the actual value."""
    parts = []
    for m in STAT:
        parts.append(f.select("player_id", "season", "week", "team", "pos", "n_prior", "team_factor",
                              pl.lit(m).alias("market"), pl.col(f"u_{m}").alias("usage"),
                              pl.col(f"o_{m}").alias("opp_factor"), pl.col(m).cast(pl.Float64).alias("actual")))
    return pl.concat(parts).filter(pl.col("n_prior") >= MIN_GAMES, pl.col("usage").is_not_null(),
                                   pl.col("team_factor").is_not_null())


def fit(train: pl.DataFrame) -> dict:
    """(a, b) per market minimizing squared error of the projection on `train`."""
    out = {}
    for m in train["market"].unique().sort().to_list():
        x = train.filter(pl.col("market") == m)
        u, tf = x["usage"].to_numpy(), x["team_factor"].to_numpy()
        of, y = x["opp_factor"].fill_null(1.0).to_numpy(), x["actual"].to_numpy()
        best = min(((float(np.mean((u * tf ** a * of ** b - y) ** 2)), a, b) for a in GRID for b in GRID))
        out[m] = {"a": float(best[1]), "b": float(best[2]), "mse": best[0], "n": x.height}
    return out


def project(x: pl.DataFrame, params: dict) -> pl.DataFrame:
    a = pl.col("market").replace_strict({m: p["a"] for m, p in params.items()}, default=0.0)
    b = pl.col("market").replace_strict({m: p["b"] for m, p in params.items()}, default=0.0)
    return x.with_columns((pl.col("usage") * pl.col("team_factor").pow(a)
                           * pl.col("opp_factor").fill_null(1.0).pow(b)).alias("proj"))
