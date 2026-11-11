"""Gamesim v2, task 1: record the frozen Generation 1 baseline (file hashes, constants, reproduction result, tests, environment).

Run scripts/gamesim_reproduce.py first (it writes data/gamesim/g3_2022_2025.parquet, which is not tracked by git).
Writes data/gamesim_v2/manifests/g1_baseline_manifest.json. Does not modify any G1 file.
Usage: python scripts/gamesim_v2/freeze_g1.py"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
G1 = (sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src/engine/gamesim").glob("*.py"))
      + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "data/gamesim").glob("*.json"))
      + ["scripts/gamesim_reproduce.py"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_gamesim*.py")))
REGISTERED_MAE = 9.983


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    m = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label": "gamesim-g1-baseline",
         "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
         "environment": {"python": platform.python_version(), "platform": platform.platform(),
                         **{k: version(k) for k in ("numpy", "polars", "pyarrow", "nflreadpy", "pytest")}},
         "files": {f: sha(ROOT / f) for f in G1}}
    k = json.loads((ROOT / "data/gamesim/gamesim_constants.json").read_text())
    m["constants"] = {"gamesim_constants.json": k, "note": "frozen in nfl-betting-model; not refit on 2022+ data"}
    out = ROOT / "data/gamesim/g3_2022_2025.parquet"
    if out.exists():
        r = pl.read_parquet(out)
        m["reproduction"] = {
            "script": "scripts/gamesim_reproduce.py <cache>", "seed": 101, "sims_per_game": 1000, "games": r.height,
            "seasons": "2022-2025 regular season, weeks 2-18", "registered_g3_margin_mae": REGISTERED_MAE,
            "reproduced_g3_margin_mae": round(float((r["sim_fair"] - r["margin"]).abs().mean()), 4),
            "elo_margin_mae": round(float((r["elo_fair"] - r["margin"]).abs().mean()), 4),
            "close_margin_mae": round(float((r["close_spread"] + r["margin"]).abs().mean()), 4),
            "output_sha256": sha(out), "output_tracked_in_git": False,
            "game_ids_sha256": hashlib.sha256(",".join(sorted(r["game_id"].to_list())).encode()).hexdigest()}
    t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("test_gamesim*.py"))],
                       cwd=ROOT, capture_output=True, text=True)
    m["g1_tests"] = {"command": "pytest tests/test_gamesim*.py", "result": t.stdout.strip().splitlines()[-1], "returncode": t.returncode}
    dst = ROOT / "data/gamesim_v2/manifests/g1_baseline_manifest.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(m, indent=1, sort_keys=True))
    print(json.dumps({k: m[k] for k in ("reproduction", "g1_tests") if k in m}, indent=1))


if __name__ == "__main__":
    main()
