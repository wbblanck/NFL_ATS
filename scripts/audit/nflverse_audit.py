"""Phase 0: audit nflverse datasets exposed by nflreadpy.

For every load_* function: try the current and one past season, record row
count, schema, season coverage, and any timestamp-like columns. Output is
written to docs/evidence/nflverse_audit.json and is cited by data_audit.md.
"""
from __future__ import annotations

import datetime as dt
import json
import traceback
from pathlib import Path

import nflreadpy as nfl
import polars as pl

OUT = Path(__file__).resolve().parents[2] / "docs" / "evidence" / "nflverse_audit.json"
TS_HINT = ("date", "time", "_at", "timestamp", "modified", "updated", "gameday")

# (loader, kwargs for "current" probe, kwargs for "history" probe)
PROBES = {
    "load_schedules": ({}, None),
    "load_teams": ({}, None),
    "load_pbp": ({"seasons": [2025]}, {"seasons": [1999]}),
    "load_player_stats": ({"seasons": [2025]}, {"seasons": [1999]}),
    "load_team_stats": ({"seasons": [2025]}, {"seasons": [1999]}),
    "load_injuries": ({"seasons": [2025]}, {"seasons": [2009]}),
    "load_depth_charts": ({"seasons": [2025]}, {"seasons": [2001]}),
    "load_rosters": ({"seasons": [2025]}, {"seasons": [1999]}),
    "load_rosters_weekly": ({"seasons": [2025]}, {"seasons": [2002]}),
    "load_snap_counts": ({"seasons": [2025]}, {"seasons": [2012]}),
    "load_officials": ({"seasons": [2025]}, {"seasons": [2015]}),
    "load_participation": ({"seasons": [2025]}, {"seasons": [2016]}),
    "load_nextgen_stats": ({"seasons": [2025]}, {"seasons": [2016]}),
    "load_pfr_advstats": ({"seasons": [2025]}, {"seasons": [2018]}),
    "load_ftn_charting": ({"seasons": [2025]}, {"seasons": [2022]}),
    "load_players": ({}, None),
    "load_trades": ({}, None),
    "load_draft_picks": ({}, None),
    "load_combine": ({}, None),
    "load_contracts": ({}, None),
}


def describe(df: pl.DataFrame) -> dict:
    d = {"rows": df.height, "cols": df.width,
         "schema": {k: str(v) for k, v in df.schema.items()}}
    if "season" in df.columns:
        d["season_min"] = int(df["season"].min()) if df.height else None
        d["season_max"] = int(df["season"].max()) if df.height else None
    ts_cols = [c for c in df.columns if any(h in c.lower() for h in TS_HINT)]
    d["timestamp_like_columns"] = {}
    for c in ts_cols:
        s = df[c].drop_nulls()
        d["timestamp_like_columns"][c] = {
            "dtype": str(df.schema[c]),
            "non_null": s.len(),
            "min": str(s.min()) if s.len() else None,
            "max": str(s.max()) if s.len() else None,
            "sample": [str(x) for x in s.head(3).to_list()],
        }
    d["sample_row"] = {k: str(v) for k, v in (df.row(0, named=True).items() if df.height else [])}
    return d


def main() -> None:
    res = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
           "nflreadpy_version": getattr(nfl, "__version__", "unknown"),
           "current_season": nfl.get_current_season(),
           "current_week": nfl.get_current_week(),
           "datasets": {}}
    for fn, (cur, hist) in PROBES.items():
        entry = {}
        for label, kw in (("current", cur), ("history", hist)):
            if kw is None:
                continue
            try:
                df = getattr(nfl, fn)(**kw)
                entry[label] = {"kwargs": kw, **describe(df)}
            except Exception as e:
                entry[label] = {"kwargs": kw, "error": f"{type(e).__name__}: {e}",
                                "trace": traceback.format_exc(limit=1)}
            print(fn, label, entry[label].get("rows", entry[label].get("error")))
        res["datasets"][fn] = entry
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
