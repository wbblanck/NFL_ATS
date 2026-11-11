"""Cached loaders for the nflverse datasets Generation 2 reads (through nflreadpy). One parquet per dataset and season
in the cache directory (never committed). Datasets are public nflverse releases."""
from __future__ import annotations

from pathlib import Path

import polars as pl


def load(name: str, season: int | None, cache: Path):
    import nflreadpy as nfl

    f = cache / (f"{name}_{season}.parquet" if season else f"{name}.parquet")
    if f.exists():
        return pl.read_parquet(f)
    fn = getattr(nfl, f"load_{name}")
    kw = {}
    if season:
        kw["seasons"] = [season]
    if name == "nextgen_stats":
        frames = [getattr(nfl, "load_nextgen_stats")(seasons=[season], stat_type=t) for t in ("passing", "rushing", "receiving")]
        df = pl.concat([x.with_columns(pl.lit(t).alias("stat_type_loaded")) for x, t in zip(frames, ("passing", "rushing", "receiving"))], how="diagonal_relaxed")
    elif name == "pfr_advstats":
        frames = [fn(seasons=[season], stat_type=t) for t in ("pass", "rush", "rec", "def")]
        df = pl.concat([x.with_columns(pl.lit(t).alias("stat_type_loaded")) for x, t in zip(frames, ("pass", "rush", "rec", "def"))], how="diagonal_relaxed")
    else:
        df = fn(**kw)
    df.write_parquet(f)
    return df


def stack(name: str, seasons, cache: Path) -> pl.DataFrame:
    """All requested seasons of a dataset stacked, seasons the loader does not have (or that are empty) skipped."""
    out = []
    for s in seasons:
        try:
            df = load(name, s, Path(cache))
        except ValueError:
            continue
        if df.height:
            out.append(df)
    return pl.concat(out, how="diagonal_relaxed")
