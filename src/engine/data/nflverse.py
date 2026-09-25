"""nflverse ingestion via nflreadpy.

Raw pulls are written to data/raw/nflverse/<dataset>/<snapshot_id>.parquet
(snapshot_id = UTC pull time) and never overwritten, so any later run can
name exactly which data it used.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl

from engine import config


def snapshot_id(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def pull(dataset: str, save: bool = True, **kwargs) -> tuple[pl.DataFrame, str]:
    import nflreadpy as nfl

    df = getattr(nfl, f"load_{dataset}")(**kwargs)
    sid = snapshot_id()
    if save:
        out = config.path("raw") / "nflverse" / dataset / f"{sid}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out)
    return df, sid


def with_kickoff(sched: pl.DataFrame) -> pl.DataFrame:
    """Add kickoff_utc and lock_utc. nflverse gametime is Eastern local time
    (nflreadr dictionary: "24-hour time and the Eastern time zone")."""
    rules = config.league()
    tz = ZoneInfo(rules.timezone)

    def to_utc(d: str | None, t: str | None):
        if not d or not t:
            return None
        local = dt.datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        return local.astimezone(dt.timezone.utc)

    kick = [to_utc(d, t) for d, t in zip(sched["gameday"].to_list(), sched["gametime"].to_list())]
    s = sched.with_columns(pl.Series("kickoff_utc", kick, dtype=pl.Datetime("us", "UTC")))
    return s.with_columns(
        (pl.col("kickoff_utc") - pl.duration(minutes=rules.lock_buffer_minutes)).alias("lock_utc"))


def regular_season_schedule(seasons: list[int] | None = None, save: bool = True) -> tuple[pl.DataFrame, str]:
    df, sid = pull("schedules", save=save)
    df = df.filter(pl.col("game_type").is_in(list(config.league().game_types)))
    if seasons:
        df = df.filter(pl.col("season").is_in(seasons))
    return with_kickoff(df), sid
