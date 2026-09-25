"""QB change feature (docs/phase6_preregistration.md, group 1).
qb_change = this game's starting QB differs from the team's starter in its previous
regular-season game. The comparison value (previous starter) is fully known pre-game."""
from __future__ import annotations

import polars as pl


def qb_change(sched: pl.DataFrame) -> pl.DataFrame:
    reg = sched.filter(pl.col("game_type") == "REG").sort("season", "week", "gameday")
    long = pl.concat([
        reg.select("game_id", "season", "week", "gameday", pl.col("home_team").alias("team"),
                   pl.col("home_qb_id").alias("qb"), pl.lit("home").alias("side")),
        reg.select("game_id", "season", "week", "gameday", pl.col("away_team").alias("team"),
                   pl.col("away_qb_id").alias("qb"), pl.lit("away").alias("side")),
    ]).sort("team", "season", "week", "gameday")
    long = long.with_columns(pl.col("qb").shift(1).over("team").alias("prev_qb"))
    long = long.with_columns(
        pl.when(pl.col("prev_qb").is_null() | pl.col("qb").is_null()).then(0)
        .when(pl.col("qb") != pl.col("prev_qb")).then(1).otherwise(0).alias("qb_change"))
    wide = long.pivot(on="side", index="game_id", values="qb_change")
    return wide.rename({"home": "qb_change_home", "away": "qb_change_away"})
