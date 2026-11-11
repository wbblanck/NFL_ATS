"""Gamesim v2, task 3: build the canonical player identity table and its diagnostics.

Writes data/gamesim_v2/processed/player_identity.parquet, player_team_history.parquet and
data/gamesim_v2/manifests/identity_diagnostics.json. Usage: python scripts/gamesim_v2/build_identity.py <cache dir>"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import polars as pl

from engine.gamesim_v2.data import identity as ID
from engine.gamesim_v2.data.loaders import load, stack

ROOT = Path(__file__).resolve().parents[2]
SEASONS = list(range(2009, 2027))
VERSION = "identity-v1"


def main(cache: Path):
    players = load("players", None, cache)
    rosters = stack("rosters_weekly", SEASONS, cache)
    snaps = stack("snap_counts", range(2012, 2027), cache)
    ident = ID.build_identity(players, rosters, snaps)
    hist = ID.team_history(rosters, ident)
    diag = ID.diagnostics(ident, rosters, snaps)
    proc = ROOT / "data" / "gamesim_v2" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    ident.write_parquet(proc / "player_identity.parquet")
    hist.write_parquet(proc / "player_team_history.parquet")
    h = hashlib.sha256((proc / "player_identity.parquet").read_bytes()).hexdigest()
    diag.update(version=VERSION, identity_rows=ident.height, team_history_rows=hist.height, identity_sha256=h)
    (ROOT / "data" / "gamesim_v2" / "manifests" / "identity_diagnostics.json").write_text(
        json.dumps(diag, indent=1, sort_keys=True, default=str))
    print({k: v for k, v in diag.items() if not isinstance(v, (list, dict)) or len(str(v)) < 200})


if __name__ == "__main__":
    main(Path(sys.argv[1]))
