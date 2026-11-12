"""Build data/gamesim_v2/features/runs.parquet (designed runs with participation), seasons 2016-2021 only (full-game development test).
Usage: python scripts/gamesim_v2/build_runs.py <g2 cache> <pbp cache>"""
from __future__ import annotations
import json, sys
from pathlib import Path
import polars as pl
from engine.gamesim_v2.data import plays as P

ROOT = Path(__file__).resolve().parents[2]
SEASONS = range(2016, 2022)

def main(cache: Path, pbp_cache: Path):
    pbp = pl.concat([pl.read_parquet(pbp_cache / f"pbp_{s}.parquet") for s in SEASONS], how="diagonal_relaxed")
    part = pl.concat([pl.read_parquet(cache / f"participation_{s}.parquet") for s in SEASONS], how="diagonal_relaxed")
    r = P.build_runs(pbp, part)
    r.write_parquet(ROOT / "data/gamesim_v2/features/runs.parquet")
    summ = r.group_by("season").agg(pl.len().alias("runs"), pl.col("has_part").mean().alias("part_share"), pl.col("epa").is_null().sum().alias("epa_null")).sort("season")
    (ROOT / "data/gamesim_v2/manifests/runs_build.json").write_text(json.dumps(summ.to_dicts(), indent=1))
    print(summ)

if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
