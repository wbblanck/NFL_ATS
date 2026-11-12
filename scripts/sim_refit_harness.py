"""Chronological harness for the simulator refit (docs/simulator_refit_v1_preregistration.md). Research only.

For each test season t (2021-2025, regular season weeks 2-18) runs one version of the simulator with seed 101 and
1000 runs per game, and writes data/gamesim/refit/<version>_<t>.parquet (git-ignored): fair margin, fair total,
win probability, the home-margin distribution m_-60..m_60 and total distribution t_0..t_100, plus the actual result
and nflverse closing lines (spread in this repo's sign, total, moneylines).

Versions:
  v0   frozen V0: league tables and league rates fit on 2016-2020, teams.factors (no opponent adjustment)
  v0r  league tables and league rates refit on 2016..t-1 (expanding); all tuned constants frozen
  v1   v0 + opponent-adjusted team factors (teams_adj.factors_adj)
Usage: python scripts/sim_refit_harness.py <cache dir> <version> [season ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim import engine as E, league as L, personnel as P, run as R, teams as TM, teams_adj as TA

ROOT = Path(__file__).resolve().parents[1]
K = ROOT / "data" / "gamesim"
OUT = K / "refit"
SIMS, SEED = 1000, 101
TESTS = [2021, 2022, 2023, 2024, 2025]
FIT0 = list(range(2016, 2021))


def tables(pbp: pl.DataFrame, seasons: list[int]) -> dict:
    p = pbp.filter(pl.col("season").is_in(seasons))
    T = L.fit(p)
    T.update(L.two_point_decision(p))
    T.update(L.clock(p))
    return T


def main(cache, version, seasons):
    d = Path(cache)
    OUT.mkdir(parents=True, exist_ok=True)
    k = json.loads((K / "gamesim_constants.json").read_text())
    T0 = json.loads((K / "gamesim_league.json").read_text())
    sched = pl.read_parquet(d / "schedules.parquet")
    pbp = pl.concat([pl.read_parquet(d / f"pbp_{s}.parquet") for s in range(2015, 2026)], how="diagonal_relaxed")
    kicks, xps = R.kick_pools(pbp)
    pk = k["personnel"]
    qg = P.qb_games(pbp)
    qbd = P.qb_delta(sched, qg, P.QBRater(qg, pk["replacement"]))
    inj = P.injury_loss(pl.read_parquet(d / "injuries.parquet"), pl.read_parquet(d / "snaps.parquet"),
                        pl.read_parquet(d / "players.parquet"), sched)
    for t in seasons:
        if version == "v0r":
            T = tables(pbp, list(range(2016, t)))
            lg = TM.league_rates(TM.game_stats(pbp.filter(pl.col("season").is_in(list(range(2016, t)))), T))
        else:
            T, lg = T0, k["league"]
        gs = TM.game_stats(pbp.filter(pl.col("season") <= t), T)
        fac = (TA.factors_adj if version == "v1" else TM.factors)(gs, lg, k["h"], k["k"], k["r"])
        games = sched.filter(pl.col("season") == t, pl.col("game_type") == "REG", pl.col("week") >= 2,
                             pl.col("result").is_not_null()).select(
            "season", "week", "game_id", "home_team", "away_team", "result", "total", "spread_line", "total_line",
            "home_moneyline", "away_moneyline", "overtime", (pl.col("location") == "Neutral").alias("neutral"))
        inp = P.inputs(qbd, inj, sched).filter(pl.col("game_id").is_in(games["game_id"].implode()))
        out, margins, totals = R.simulate_games(games, fac, E.Tables(T), kicks, xps, k["hfa"], sims=SIMS, seed=SEED,
                                                shift=P.shifts(inp, pk["coefs"]), return_totals=True)
        order = {g: i for i, g in enumerate(out["game_id"].to_list())}
        idx = np.array([order[g] for g in games["game_id"].to_list()])
        m = np.clip(np.rint(margins[idx]).astype(int), -60, 60)
        tt = np.clip(np.rint(totals[idx]).astype(int), 0, 100)
        cols = {f"m_{v}": (m == v).mean(1) for v in range(-60, 61)}
        cols.update({f"t_{v}": (tt == v).mean(1) for v in range(0, 101)})
        res = games.join(out.select("game_id", pl.col("fair").alias("sim_fair"), "sim_total"), on="game_id") \
            .with_columns((-pl.col("spread_line")).alias("close_spread"), pl.lit(version).alias("version")) \
            .rename({"result": "margin"}).drop("spread_line") \
            .with_columns(pl.Series("sim_pwin", (margins[idx] > 0).mean(1) + 0.5 * (margins[idx] == 0).mean(1)),
                          **{c: pl.Series(v) for c, v in cols.items()})
        res.write_parquet(OUT / f"{version}_{t}.parquet")
        mae = float((res["sim_fair"] - res["margin"]).abs().mean())
        print(f"{version} {t}: {res.height} games, margin MAE {mae:.3f}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [int(s) for s in sys.argv[3:]] or TESTS)
