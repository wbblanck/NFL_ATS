"""Gamesim v2 milestone: for one historical game and its pregame cutoff, reconstruct the expected players from the snapshot, take the
player effects as of that week, and simulate correlated dropbacks (offensive line vs rush, receiver vs coverage) with a full trace.

Prints simulated pressure, sack, completion and yards per dropback for each offense and the actual rates in that game, then one complete
play trace. Only seasons through 2021 (the locked holdout is never loaded). Not a game simulator: no clock, downs or special teams.
Usage: python scripts/gamesim_v2/simulate_historical_game.py <game_id> [n_plays=4000] [seed=1]"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim_v2.matchups.protection import AbilityTable
from engine.gamesim_v2.players import lineups
from engine.gamesim_v2.plays import passing as PS
from engine.gamesim_v2.probability.random_streams import streams

ROOT = Path(__file__).resolve().parents[2]
FEAT = ROOT / "data/gamesim_v2/features"


def main(game_id: str, n: int = 4000, seed: int = 1):
    season = int(game_id.split("_")[0])
    if season > 2021:
        raise SystemExit("seasons after 2021 are the locked holdout")
    d = pl.read_parquet(FEAT / "dropbacks.parquet").filter(pl.col("season") <= 2021)
    g = d.filter(pl.col("game_id") == game_id)
    week = int(g["week"][0])
    kickoff = g["game_date"][0]
    snap = pl.read_parquet(ROOT / f"data/gamesim_v2/snapshots/pregame_players_{season}.parquet").filter(pl.col("game_id") == game_id)
    tabs = {}
    for k in ("pressure", "completion"):
        ab = pl.read_parquet(FEAT / f"abilities_{k}.parquet").filter((pl.col("season") == season) & (pl.col("week") == week))
        tabs[k] = AbilityTable.from_long(ab)
    out = {}
    teams = g["posteam"].unique().to_list()
    for off_team in teams:
        def_team = [t for t in teams if t != off_team][0]
        prior = d.filter(pl.col("game_date") < kickoff)
        emp = PS.build_empirics(prior.filter(pl.col("season") >= 2018))
        shares = PS.target_shares(prior, off_team, kickoff)
        rs0 = streams(seed, 10**6)
        eff = {}
        for t in tabs.values():
            eff.update(t.draw(rs0["ability"]))           # one realization of every player's effect for this simulated game
        off = lineups.sample_lineup(rs0["strategy"], snap, off_team, True)
        dfn = lineups.sample_lineup(rs0["strategy"], snap, def_team, False)
        # receivers actually likely to be targeted: target-share leaders who are in the expected offense
        shares = {u: s for u, s in shares.items() if u in set(snap["uid"])}
        play = {"down": [2], "ydstogo": [8], "shotgun": [1], "no_huddle": [0]}
        tr = [PS.simulate_pass_play(streams(seed, i), tabs, eff, emp, play, off, dfn, shares) for i in range(n)]
        sim = {"pressure": np.mean([t["pressure"] for t in tr]), "sack": np.mean([t["outcome"] == "sack" for t in tr]),
               "complete_per_attempt": np.mean([t["outcome"] == "complete" for t in tr if t["outcome"] in ("complete", "incomplete", "interception")]),
               "yards_per_dropback": np.mean([t["yards"] for t in tr])}
        act = g.filter(pl.col("posteam") == off_team)
        a_att = act.filter(pl.col("attempt"), ~pl.col("sack"), ~pl.col("scramble"))
        actual = {"dropbacks": act.height, "pressure": float((act["was_pressure"].fill_null(False) | act["sack"]).mean()), "sack": float(act["sack"].mean()),
                  "complete_per_attempt": float(a_att["complete"].mean()), "yards_per_dropback": float(act["yards_gained"].mean())}
        out[off_team] = {"lineup_offense": off, "lineup_defense": dfn, "simulated": {k: round(float(v), 3) for k, v in sim.items()}, "actual": {k: round(v, 3) for k, v in actual.items()},
                         "sample_trace": next(t for t in tr if t["outcome"] == "complete")}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4000, int(sys.argv[3]) if len(sys.argv) > 3 else 1)
