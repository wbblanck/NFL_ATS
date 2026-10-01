"""Weekly tiebreaker: total points in the week's last game (closest guess wins).

The guess that minimizes the expected miss is the median of the final total, and the market total is the best
estimate of that median we have: on 2018-2025 last games it missed by 9.9 points on average; no adjustment fitted on
2010-2017 beat it on 2018-2025 by a significant margin (docs/tiebreak_total_report.md). The guess is the market total
rounded to a whole number, with .5 rounded down (night games have finished slightly under the total since 2018; this
only moves the guess half a point). Ranges are 2010-2025 quantiles of actual total minus market total."""
from __future__ import annotations

import math

import polars as pl

# actual total - market total, 2010-2025 regular season (4,223 games)
RANGE_50 = (-8.5, 9.0)
RANGE_80 = (-15.5, 18.0)


def guess(total: float) -> int:
    return math.floor(total) if total - math.floor(total) == 0.5 else round(total)


def build(sched: pl.DataFrame, season: int) -> list[dict]:
    """One row per week: the last game by kickoff, its market total, the guess, ranges, and the result once played."""
    wk = sched.filter(pl.col("season") == season, pl.col("game_type") == "REG")
    out = []
    for w in sorted(set(wk["week"].to_list())):
        g = wk.filter(pl.col("week") == w).sort("kickoff_utc", "game_id").row(-1, named=True)
        t, sp = g.get("total_line"), g.get("spread_line")
        row = {"week": int(w), "game_id": g["game_id"], "away": g["away_team"], "home": g["home_team"],
               "kickoff_utc": g["kickoff_utc"].isoformat(), "market_total": t, "guess": None}
        if t is not None:
            row.update(guess=guess(t), r50=[round(t + RANGE_50[0]), round(t + RANGE_50[1])],
                       r80=[round(t + RANGE_80[0]), round(t + RANGE_80[1])])
            if sp is not None:              # nflverse spread_line: home margin, positive = home favored
                row.update(home_pts=round((t + sp) / 2, 1), away_pts=round((t - sp) / 2, 1))
        if g.get("home_score") is not None and g.get("away_score") is not None:
            row["actual"] = int(g["home_score"] + g["away_score"])
            if row["guess"] is not None:
                row["miss"] = abs(row["actual"] - row["guess"])
        out.append(row)
    return out
