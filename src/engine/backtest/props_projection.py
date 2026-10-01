"""Projection rule for props (docs/projection_props_confirm.md): fitted on 2024, checked on 2025, tested 2026.

P1: on DraftKings' quote, bet the under when (a) at least two real books post different lines for the prop and
DraftKings has the highest, and (b) DraftKings' line is at least 10% above the player's pre-game projection
(engine.models.player_proj, constants fitted on 2024). Screen as in props_confirm.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from engine.backtest import props as P
from engine.backtest import props_confirm as C
from engine.models import player_proj as M

GAP = 0.10
FIT_SEASON = 2024


def projections(season: int) -> pl.DataFrame:
    seasons = sorted({FIT_SEASON - 1, FIT_SEASON, season - 1, season})
    L = M.long(M.features(M.stats(seasons), M.implied_points(seasons)))
    params = M.fit(L.filter(pl.col("season") == FIT_SEASON))
    return M.project(L.filter(pl.col("season") == season), params)


def dk_bets(season: int, proj: pl.DataFrame) -> pl.DataFrame:
    g = P.graded(P.join(P.load_lines(season), P.load_stats(season), P.load_snaps(season)))
    s = C.screened(g).filter(pl.col("result") != "push")
    agg = s.group_by(C.KEY).agg(pl.col("line").n_unique().alias("nl"), pl.col("line").max().alias("hi"))
    dk = s.filter(pl.col("book") == "DK NJ").unique(subset=C.KEY).join(agg, on=C.KEY)
    return dk.join(proj.select("player_id", "season", "week", "market", "proj"),
                   on=["player_id", "season", "week", "market"], how="inner") \
        .with_columns(((pl.col("line") - pl.col("proj")) / pl.col("line").abs().clip(lower_bound=1)).alias("gap"))


def rule_p1(b: pl.DataFrame) -> pl.DataFrame:
    return b.filter(pl.col("nl") >= 2, pl.col("line") == pl.col("hi"), pl.col("gap") >= GAP)


def run(season: int) -> dict:
    from engine.backtest.props_selective import evaluate

    x = rule_p1(dk_bets(season, projections(season)))
    return {"P1_projection_under_dk_high_line": evaluate(x, level=0.025)}
