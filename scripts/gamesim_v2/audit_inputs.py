"""Gamesim v2, Task 2: audit the nflverse player-level datasets (schema, season coverage, ID columns, play-level fields).

Downloads each dataset by season through nflreadpy into <cache dir> (not committed), then writes
data/gamesim_v2/manifests/data_audit.json with, per dataset: loader, seasons with rows, row counts per season,
columns and dtypes, ID-like columns, null share per column for the latest full season, and download errors.

Usage: python scripts/gamesim_v2/audit_inputs.py <cache dir>
Research only. Nothing here touches the live pipeline."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from engine.gamesim_v2.data.loaders import load

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "gamesim_v2" / "manifests"
SEASONS = list(range(2009, 2027))
# loader name -> (kwargs builder, expected first season in docs/data_audit.md)
DATASETS = {
    "participation": 2016, "ftn_charting": 2022, "nextgen_stats": 2016, "pfr_advstats": 2018,
    "snap_counts": 2012, "rosters_weekly": 2002, "depth_charts": 2001, "injuries": 2009,
    "player_stats": 1999, "players": None,
}


def audit(cache: Path):
    res = {"audited_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "datasets": {}}
    for name, first in DATASETS.items():
        info = {"expected_first_season": first, "seasons": {}, "errors": {}}
        sample = None
        if name == "players":
            df = load(name, None, cache)
            info["rows"] = df.height
            info["schema"] = {c: str(t) for c, t in df.schema.items()}
            res["datasets"][name] = info
            continue
        for s in SEASONS:
            if first and s < first - 1:
                continue
            try:
                df = load(name, s, cache)
            except Exception as e:  # noqa: BLE001 - audit records every failure
                info["errors"][str(s)] = f"{type(e).__name__}: {str(e)[:120]}"
                continue
            info["seasons"][str(s)] = df.height
            if df.height and (sample is None or s <= 2025):
                sample = (s, df)
        if sample:
            s, df = sample
            info["schema_season"] = s
            info["schema"] = {c: str(t) for c, t in df.schema.items()}
            info["id_like_columns"] = [c for c in df.columns if "id" in c.lower() or c.lower() in ("gsis", "pfr", "player", "pfr_player_id")]
            info["null_share_schema_season"] = {c: round(df[c].null_count() / max(df.height, 1), 3) for c in df.columns}
        res["datasets"][name] = info
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data_audit.json").write_text(json.dumps(res, indent=1, sort_keys=True))
    return res


if __name__ == "__main__":
    r = audit(Path(sys.argv[1]))
    for n, i in r["datasets"].items():
        ss = sorted(i["seasons"]) if "seasons" in i else []
        print(n, "seasons", (ss[0], ss[-1], len(ss)) if ss else "-", "errors", len(i.get("errors", {})))
