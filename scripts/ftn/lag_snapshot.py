"""Weekly FTN lag log (docs/ftn_shadow_preregistration.md, Amendment 1, check (c)).

For every played game in the season, record whether FTN charting rows exist yet, with the snapshot time.
Appends one row per game per run. Counts only: no FTN play rows are written.

Usage: python3 scripts/ftn/lag_snapshot.py [season]    (default 2026)
"""
import datetime as dt
import sys
from pathlib import Path

import nflreadpy as nfl
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "docs" / "evidence" / "ftn" / "lag_log.csv"


def as_polars(x):
    return x if isinstance(x, pl.DataFrame) else pl.from_pandas(x)


def main(season: int) -> None:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    played = (as_polars(nfl.load_schedules([season]))
              .filter(pl.col("result").is_not_null())
              .select("game_id", "season", "week", "gameday"))
    ftn = (as_polars(nfl.load_ftn_charting([season]))
           .group_by("nflverse_game_id").len()
           .rename({"len": "ftn_plays"}))
    rows = (played.join(ftn, left_on="game_id", right_on="nflverse_game_id", how="left")
            .with_columns(pl.col("ftn_plays").fill_null(0), pl.lit(now).alias("snapshot_utc"))
            .select("snapshot_utc", "season", "week", "game_id", "gameday", "ftn_plays"))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        if LOG.stat().st_size == 0:
            f.write(",".join(rows.columns) + "\n")
        f.write(rows.write_csv(include_header=False))
    charted = int((rows["ftn_plays"] > 0).sum())
    print(f"{now} {season}: {rows.height} played games, {charted} with FTN rows")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)
