"""Audit 0.2/0.4: nflverse spread_line coverage, whole-number count, and games
landing exactly on a whole-number line (graded as pushes in backtests)."""
from pathlib import Path

import nflreadpy as nfl
import polars as pl

s = nfl.load_schedules()
r = s.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null())
t = (r.group_by("season")
     .agg(pl.len().alias("games"),
          pl.col("spread_line").is_not_null().sum().alias("has_spread"),
          ((pl.col("spread_line") % 1) == 0).sum().alias("whole_lines"),
          (((pl.col("spread_line") % 1) == 0) & (pl.col("result") == pl.col("spread_line"))).sum()
          .alias("pushes_on_proxy"))
     .sort("season"))
out = Path(__file__).resolve().parents[2] / "docs/evidence/spread_proxy_whole_numbers.csv"
t.write_csv(out)
print(t)
print(t.select(pl.col("games", "whole_lines", "pushes_on_proxy").sum()))
