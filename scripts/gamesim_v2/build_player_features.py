"""Gamesim v2: build the dropback table (data/gamesim_v2/features/dropbacks.parquet, not committed) and position lookup.
Usage: python scripts/gamesim_v2/build_player_features.py <g2 cache> <pbp cache (gamesim_cache)>"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

from engine.gamesim_v2.data import plays as P
from engine.gamesim_v2.data.loaders import load, stack

ROOT = Path(__file__).resolve().parents[2]


def main(cache: Path, pbp_cache: Path):
    pbp = pl.concat([pl.read_parquet(pbp_cache / f"pbp_{s}.parquet") for s in range(2016, 2026)], how="diagonal_relaxed")
    part = stack("participation", range(2016, 2026), cache)
    d = P.build_dropbacks(pbp, part)
    rosters = stack("rosters_weekly", range(2016, 2026), cache)
    pos = P.position_lookup(rosters, load("players", None, cache))
    out = ROOT / "data" / "gamesim_v2" / "features"
    out.mkdir(parents=True, exist_ok=True)
    d.write_parquet(out / "dropbacks.parquet")
    pos.write_parquet(out / "position_lookup.parquet")
    print(d.shape, pos.shape)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
