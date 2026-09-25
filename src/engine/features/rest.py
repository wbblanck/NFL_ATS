"""Rest/schedule features (group 2). nflverse home_rest/away_rest are schedule facts."""
from __future__ import annotations

import polars as pl


def rest_features(sched: pl.DataFrame) -> pl.DataFrame:
    return sched.select(
        "game_id",
        (pl.col("home_rest") - pl.col("away_rest")).clip(-7, 7).cast(pl.Float64).alias("rest_diff"),
        (pl.col("home_rest") <= 5).cast(pl.Int8).alias("home_short"),
        (pl.col("away_rest") <= 5).cast(pl.Int8).alias("away_short"),
        (pl.col("home_rest") >= 13).cast(pl.Int8).alias("home_bye"),
        (pl.col("away_rest") >= 13).cast(pl.Int8).alias("away_bye"),
    )
