"""Dropback table for the player-level matchup models (gamesim v2, sprint 1, task 4/5).

One row per regular-season dropback (pass attempt, sack or scramble, penalty plays excluded) joined to nflverse
participation (who was on the field) with position groups from weekly rosters. Only facts about the play itself; nothing
here looks at later games. Rows without a participation match are kept with `has_part` False so coverage stays visible.
"""
from __future__ import annotations

import polars as pl

from .identity import FRANCHISE

GROUPS = ["QB", "RB", "WR", "TE", "OL", "DL", "LB", "DB"]


def position_lookup(rosters: pl.DataFrame, players: pl.DataFrame) -> pl.DataFrame:
    """(season, gsis_id) -> position group, the most frequent weekly-roster position that season; players table as fallback."""
    r = rosters.filter(pl.col("gsis_id").is_not_null(), pl.col("position").is_in(GROUPS)).group_by(
        pl.col("season").cast(pl.Int64), "gsis_id", "position").len().sort("len", descending=True).unique(["season", "gsis_id"], keep="first")
    return r.select("season", "gsis_id", pl.col("position").alias("grp"))


def build_dropbacks(pbp: pl.DataFrame, part: pl.DataFrame) -> pl.DataFrame:
    d = pbp.filter(pl.col("season_type") == "REG", pl.col("qb_dropback") == 1, pl.col("penalty").fill_null(0) == 0,
                   pl.col("play_type") == "pass").select(
        "game_id", pl.col("play_id").cast(pl.Int64), "season", "week", "game_date", "posteam", "defteam",
        pl.col("passer_player_id").alias("qb"), pl.col("receiver_player_id").alias("target"),
        (pl.col("sack") == 1).alias("sack"), (pl.col("qb_scramble") == 1).alias("scramble"),
        (pl.col("complete_pass") == 1).alias("complete"), (pl.col("interception") == 1).alias("interception"),
        (pl.col("pass_attempt") == 1).alias("attempt"), pl.col("air_yards"), pl.col("yards_gained"), pl.col("epa"),
        pl.col("down"), pl.col("ydstogo"), pl.col("yardline_100"), pl.col("score_differential"), pl.col("shotgun"),
        pl.col("no_huddle"), (pl.col("qb_hit") == 1).alias("qb_hit"), pl.col("game_seconds_remaining")).with_columns(
        pl.col("posteam").replace(FRANCHISE), pl.col("defteam").replace(FRANCHISE))
    p = part.select(pl.col("nflverse_game_id").alias("game_id"), pl.col("play_id").cast(pl.Int64), "offense_players", "defense_players",
                    "was_pressure", "time_to_throw", "number_of_pass_rushers", "defenders_in_box", "route",
                    "defense_man_zone_type", "defense_coverage_type", "offense_formation").unique(["game_id", "play_id"])
    j = d.join(p, on=["game_id", "play_id"], how="left").with_columns(pl.col("offense_players").is_not_null().alias("has_part"))
    return j.sort("game_date", "game_id", "play_id")
