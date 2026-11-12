"""Reproduce the ported game simulator's frozen 2022-2025 output inside NFL_ATS (docs/HANDOFF_game_simulator.md).

Runs G3 (team factors + QB and injury layer) with the constants frozen in nfl-betting-model, seed 101, 1000 runs per
game, on 2022-2025 regular season weeks 2-18, and checks the margin MAE against the registered 9.983. Also runs the
Elo baseline. Writes data/gamesim/g3_2022_2025.parquet: one row per game with the simulator's fair home margin,
Elo's fair home margin, the actual margin, nflverse's closing spread in this repo's sign (negative = home favored),
and the simulator's home-margin distribution (columns m_-60 .. m_60, share of runs; tails folded into the ends).

Usage: python scripts/gamesim_reproduce.py <cache dir>   (the cache is filled from nflverse on first use)"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim import elo as EL, engine as E, personnel as P, run as R, teams as TM

ROOT = Path(__file__).resolve().parents[1]
K = ROOT / "data" / "gamesim"
CONFIRM = [2022, 2023, 2024, 2025]
SEASONS = list(range(2015, 2026))
G3_MAE = 9.983
SIMS, SEED = 1000, 101


def cache(d: Path):
    import nflreadpy as nfl

    d.mkdir(parents=True, exist_ok=True)
    for s in SEASONS:
        f = d / f"pbp_{s}.parquet"
        if not f.exists():
            nfl.load_pbp(seasons=[s]).write_parquet(f)
    if not (d / "schedules.parquet").exists():
        nfl.load_schedules(seasons=list(range(1999, 2027))).write_parquet(d / "schedules.parquet")
        nfl.load_injuries(seasons=SEASONS).write_parquet(d / "injuries.parquet")
        nfl.load_snap_counts(seasons=SEASONS).write_parquet(d / "snaps.parquet")
        nfl.load_players().write_parquet(d / "players.parquet")


def main(d):
    d = Path(d)
    cache(d)
    k = json.loads((K / "gamesim_constants.json").read_text())
    T = json.loads((K / "gamesim_league.json").read_text())
    ek = json.loads((K / "elo_constants.json").read_text())
    sched = pl.read_parquet(d / "schedules.parquet")
    pbp = pl.concat([pl.read_parquet(d / f"pbp_{s}.parquet") for s in SEASONS], how="diagonal_relaxed")
    games = sched.filter(pl.col("season").is_in(CONFIRM), pl.col("game_type") == "REG", pl.col("week") >= 2,
                         pl.col("result").is_not_null()).select(
        "season", "week", "game_id", "home_team", "away_team", "result", "spread_line",
        (pl.col("location") == "Neutral").alias("neutral"))
    kicks, xps = R.kick_pools(pbp)
    gs = TM.game_stats(pbp, T)
    fac = TM.factors(gs, k["league"], k["h"], k["k"], k["r"])
    qg = P.qb_games(pbp)
    pk = k["personnel"]
    qbd = P.qb_delta(sched, qg, P.QBRater(qg, pk["replacement"]))
    inj = P.injury_loss(pl.read_parquet(d / "injuries.parquet"), pl.read_parquet(d / "snaps.parquet"),
                        pl.read_parquet(d / "players.parquet"), sched)
    inp = P.inputs(qbd, inj, sched).filter(pl.col("game_id").is_in(games["game_id"].implode()))
    out, margins = R.simulate_games(games, fac, E.Tables(T), kicks, xps, k["hfa"], sims=SIMS, seed=SEED,
                                    shift=P.shifts(inp, pk["coefs"]))
    x = games.join(out.select("game_id", pl.col("fair").alias("sim_fair")), on="game_id")
    mae = float((x["sim_fair"] - x["result"]).abs().mean())
    print(f"G3 margin MAE {mae:.4f} on {x.height} games (registered {G3_MAE})")
    if abs(mae - G3_MAE) >= 0.0005:
        raise SystemExit("does not reproduce the registered result; nothing written")
    # Elo baseline
    eg = EL.prep(sched.filter(pl.col("season") <= 2025))
    er = EL.run(eg, ek["k"], ek["h"], ek["c"]).join(EL.scoring_level(eg), on="game_id")
    mh, ma = EL.means(er["d"], er["level"], ek["b"])
    er = er.select("game_id", pl.Series("elo_fair", mh - ma))
    # margin distributions, aligned to `out` row order
    order = {g: i for i, g in enumerate(out["game_id"].to_list())}
    idx = np.array([order[g] for g in x["game_id"].to_list()])
    m = np.clip(np.rint(margins[idx]).astype(int), -60, 60)
    dist = np.stack([(m == v).mean(1) for v in range(-60, 61)], axis=1)
    cols = {f"m_{v}": dist[:, i] for i, v in enumerate(range(-60, 61))}
    # attach the distributions while rows are still in x's order (a later join may reorder rows; fixed 2026-11-12,
    # before this the m_* columns were attached after the Elo join and did not line up with their games)
    x = x.with_columns(**{c: pl.Series(v) for c, v in cols.items()})
    res = x.join(er, on="game_id", how="left").with_columns((-pl.col("spread_line")).alias("close_spread")) \
        .rename({"result": "margin"}).drop("spread_line")
    res.write_parquet(K / "g3_2022_2025.parquet")
    print(f"Elo margin MAE {float((res['elo_fair'] - res['margin']).abs().mean()):.4f}; "
          f"close MAE {float((res['close_spread'] + res['margin']).abs().mean()):.4f}; wrote {res.height} rows")


if __name__ == "__main__":
    main(sys.argv[1])
