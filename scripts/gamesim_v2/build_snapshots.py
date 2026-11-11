"""Gamesim v2, task 4: build point-in-time pregame player snapshots and their calibration report.

Writes data/gamesim_v2/snapshots/pregame_players_<season>.parquet (not committed) and
data/gamesim_v2/manifests/snapshot_manifest.json (row counts, missingness, hashes, calibration of p_active and expected share,
pool recall). Seasons 2022-2025 are the locked holdout and are skipped unless --holdout is passed.
Usage: python scripts/gamesim_v2/build_snapshots.py <g2 cache> <schedules parquet> [--holdout]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.data import snapshots as S
from engine.gamesim_v2.data.identity import FRANCHISE
from engine.gamesim_v2.data.loaders import stack

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/gamesim_v2"


def main(cache: Path, sched_path: Path, holdout: bool):
    sched = pl.read_parquet(sched_path)
    ko = S.kickoffs(sched).filter(pl.col("season").is_between(2013, 2025))
    tg = S.team_games(ko, FRANCHISE)
    ident = pl.read_parquet(OUT / "processed/player_identity.parquet")
    sn = S.snap_table(stack("snap_counts", range(2013, 2026), cache), ident, FRANCHISE)
    inj = S.injury_table(stack("injuries", range(2013, 2026), cache).filter(pl.col("season") <= 2024), ko, FRANCHISE)
    inj25 = S.injury_table(stack("injuries", [2025], cache), ko, FRANCHISE)
    inj = pl.concat([inj, inj25], how="diagonal_relaxed")
    pool = S.build_pool(tg, sn, inj, ident)
    pa = S.p_active_table(pool)
    snap = S.finalize(pool, pa, ko).filter(pl.col("season") >= 2016)
    snap = S.add_position_group(snap, pl.read_parquet(OUT / "features/position_lookup.parquet"), ident)
    abf = [OUT / f"features/abilities_{k}.parquet" for k in ("pressure", "completion")]
    if all(f.exists() for f in abf):   # written by validate_plays.py; seasons without a fitted block keep null effects
        snap = S.add_abilities(snap, {"pressure": pl.read_parquet(abf[0]), "completion": pl.read_parquet(abf[1])})
    seasons = sorted(snap["season"].unique().to_list())
    if not holdout:
        seasons = [s for s in seasons if s <= 2021]
    (OUT / "snapshots").mkdir(exist_ok=True)
    man = {"snapshot_version": S.SNAPSHOT_VERSION, "cutoff": f"kickoff - {S.CUTOFF_MINUTES} min", "window_games": S.WINDOW,
           "identity_version": json.loads((OUT / "manifests/identity_diagnostics.json").read_text())["version"], "seasons": {}}
    for s in seasons:
        x = snap.filter(pl.col("season") == s)
        x.write_parquet(OUT / f"snapshots/pregame_players_{s}.parquet")
        scr = x.filter(pl.col("in_prev_pool"))
        # calibration of availability: among pool players, predicted p_active vs played a scrimmage snap
        yv, pv = scr["outcome_played_scrimmage"].to_numpy().astype(float), scr["p_active"].to_numpy()
        # pool recall: players who played >= 20% of their team's scrimmage snaps in the game and were in the pool
        reg = scr.filter(pl.col("snap_share_when_active") >= 0.25)   # regulars: >= 25% of snaps when active
        rr, pr = reg["outcome_played_scrimmage"].to_numpy().astype(float), reg["p_active"].to_numpy()
        # expected share vs actual share: actual share of team scrimmage snaps in this game is not stored, so compare played-ness only
        # pool recall: of players who played a scrimmage snap in the game, the share that were in the pool
        played = x.filter(pl.col("outcome_played_scrimmage"))
        recall = float(played["in_prev_pool"].mean())
        man["seasons"][str(s)] = {
            "rows": x.height, "games": x["game_id"].n_unique(),
            "pool_players_per_team_game": round(x.height / (2 * x["game_id"].n_unique()), 1),
            "missing_share": {c: round(float(x[c].null_count() / x.height), 4) for c in ("position", "pos_grp", "status", "injury_ts")},
            "injury_rows": int(x.filter(pl.col("status") != "no_report").height),
            "injury_ts_verified_share_of_report_rows": round(float(x.filter(pl.col("status") != "no_report")["injury_ts_verified"].mean()), 3),
            "p_active_brier": round(float(np.mean((yv - pv) ** 2)), 4), "p_active_base_brier": round(float(np.mean((yv - yv.mean()) ** 2)), 4),
            "regulars_n": int(reg.height), "regulars_played_rate": round(float(rr.mean()), 4), "regulars_mean_p_active": round(float(pr.mean()), 4),
            "regulars_p_active_brier": round(float(np.mean((rr - pr) ** 2)), 4),
            "pool_recall_of_players_who_played": round(recall, 4),
            "played_rate_in_pool": round(float(yv.mean()), 4), "mean_p_active_in_pool": round(float(pv.mean()), 4),
            "sha256": S.checksum(x)}
    (OUT / "manifests/snapshot_manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True))
    pa.write_csv(OUT / "manifests/p_active_by_status.csv")
    print(json.dumps(man["seasons"], indent=1)[:3000])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), "--holdout" in sys.argv)
