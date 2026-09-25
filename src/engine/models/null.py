"""Phase 2 null baselines: fixed-side strategies graded against an opening line.

Strategies: always home, always away, always favorite, always underdog.
Grading uses the canonical home spread S (negative = home favored); a game
landing exactly on a whole-number line is a push, excluded from the win rate
and counted separately (spec 0.4). Pick'em lines (S == 0) have no favorite, so
they are excluded from the favorite/underdog strategies and counted as `no_fav`.

Win rate p = W / (W + L); SE = sqrt(p (1 - p) / (W + L)); z_vs_50 = (p - 0.5) / SE.
"""
from __future__ import annotations

import math

import polars as pl

STRATEGIES = ("home", "away", "favorite", "underdog")


def _pick_home(strategy: str) -> pl.Expr:
    s = pl.col("home_spread")
    return {
        "home": pl.lit(True),
        "away": pl.lit(False),
        "favorite": pl.when(s < 0).then(True).when(s > 0).then(False).otherwise(None),
        "underdog": pl.when(s > 0).then(True).when(s < 0).then(False).otherwise(None),
    }[strategy]


def grade_frame(df: pl.DataFrame) -> pl.DataFrame:
    """df needs home_spread and margin (home - away). Adds result in {home, away, push}."""
    m, s = pl.col("margin"), pl.col("home_spread")
    return df.with_columns(
        pl.when(m > -s).then(pl.lit("home")).when(m < -s).then(pl.lit("away")).otherwise(pl.lit("push"))
        .alias("result"))


def se(p: float, n: int) -> float:
    return math.sqrt(p * (1 - p) / n) if n else float("nan")


def baseline_table(df: pl.DataFrame, by: list[str] | None = None) -> pl.DataFrame:
    """One row per (group, strategy): W, L, P, no_fav, N, win_rate, se."""
    g = grade_frame(df)
    out = []
    for strat in STRATEGIES:
        x = g.with_columns(_pick_home(strat).alias("pick_home"))
        x = x.with_columns(
            pl.when(pl.col("pick_home").is_null()).then(pl.lit("no_fav"))
            .when(pl.col("result") == "push").then(pl.lit("P"))
            .when((pl.col("result") == "home") == pl.col("pick_home")).then(pl.lit("W"))
            .otherwise(pl.lit("L")).alias("o"))
        counts = [(pl.col("o") == k).sum().alias(k) for k in ("W", "L", "P", "no_fav")]
        agg = x.group_by(by).agg(counts) if by else x.select(counts)
        agg = agg.with_columns(pl.lit(strat).alias("strategy"))
        out.append(agg)
    t = pl.concat(out, how="vertical_relaxed")
    t = t.with_columns((pl.col("W") + pl.col("L")).alias("N"))
    t = t.with_columns((pl.col("W") / pl.col("N")).alias("win_rate"))
    t = t.with_columns(
        pl.struct("win_rate", "N").map_elements(lambda r: se(r["win_rate"], r["N"]), return_dtype=pl.Float64)
        .alias("se"))
    t = t.with_columns(((pl.col("win_rate") - 0.5) / pl.col("se")).alias("z_vs_50"))
    return t.sort((by or []) + ["strategy"])
