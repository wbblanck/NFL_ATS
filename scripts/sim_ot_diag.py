"""Overtime and endgame diagnostic for the simulator V0 (descriptive, development data 2022-2025). Research only.

Question: is the simulator's 3-point shortfall (11.5% vs 15.2%) caused by overtime (how often it reaches overtime,
how its overtime games end) or by regulation scoring? Uses the simulator's own end-of-regulation score.
Usage: python scripts/sim_ot_diag.py <cache dir>  -> data/gamesim/refit/ot_diag.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

from engine.gamesim import engine as E, personnel as P, run as R, teams as TM

ROOT = Path(__file__).resolve().parents[1]
K = ROOT / "data" / "gamesim"
SIMS, SEED = 1000, 101
SEASONS = [2022, 2023, 2024, 2025]
KEYS = [1, 2, 3, 4, 6, 7, 8, 10, 14]


def main(cache):
    d = Path(cache)
    k = json.loads((K / "gamesim_constants.json").read_text())
    T = json.loads((K / "gamesim_league.json").read_text())
    sched = pl.read_parquet(d / "schedules.parquet")
    pbp = pl.concat([pl.read_parquet(d / f"pbp_{s}.parquet") for s in range(2015, 2026)], how="diagonal_relaxed")
    kicks, xps = R.kick_pools(pbp)
    pk = k["personnel"]
    qg = P.qb_games(pbp)
    qbd = P.qb_delta(sched, qg, P.QBRater(qg, pk["replacement"]))
    inj = P.injury_loss(pl.read_parquet(d / "injuries.parquet"), pl.read_parquet(d / "snaps.parquet"),
                        pl.read_parquet(d / "players.parquet"), sched)
    gs = TM.game_stats(pbp, T)
    fac = TM.factors(gs, k["league"], k["h"], k["k"], k["r"])
    games = sched.filter(pl.col("season").is_in(SEASONS), pl.col("game_type") == "REG", pl.col("week") >= 2,
                         pl.col("result").is_not_null()).select(
        "season", "week", "game_id", "home_team", "away_team", "result", "overtime",
        (pl.col("location") == "Neutral").alias("neutral"))
    inp = P.inputs(qbd, inj, sched).filter(pl.col("game_id").is_in(games["game_id"].implode()))
    out, margins, totals, reg = R.simulate_games(games, fac, E.Tables(T), kicks, xps, k["hfa"], sims=SIMS, seed=SEED,
                                                 shift=P.shifts(inp, pk["coefs"]), return_totals=True,
                                                 return_regscore=True)
    order = {g: i for i, g in enumerate(out["game_id"].to_list())}
    idx = np.array([order[g] for g in games["game_id"].to_list()])
    m = np.rint(margins[idx]).astype(int)
    rm = (reg[idx, :, 0] - reg[idx, :, 1]).astype(int)
    sim_ot = rm == 0
    act = games["result"].to_numpy().astype(int)
    act_ot = games["overtime"].fill_null(0).to_numpy() == 1
    res = {"games": games.height, "fair_mae_check": float(np.abs(margins[idx].mean(1) - act).mean())}
    res["overtime_rate"] = {"actual": float(act_ot.mean()), "sim": float(sim_ot.mean())}
    res["ot_games_ending_by_3"] = {"actual": float((np.abs(act[act_ot]) == 3).mean()),
                                   "sim": float((np.abs(m[sim_ot]) == 3).mean())}
    res["ot_ties"] = {"actual": float((act[act_ot] == 0).mean()), "sim": float((m[sim_ot] == 0).mean())}
    res["ot_ending_by_6_or_more"] = {"actual": float((np.abs(act[act_ot]) >= 6).mean()),
                                     "sim": float((np.abs(m[sim_ot]) >= 6).mean())}
    keys = {}
    for kk in KEYS:
        keys[str(kk)] = {
            "all_actual": float((np.abs(act) == kk).mean()), "all_sim": float((np.abs(m) == kk).mean()),
            "reg_decided_actual": float(((np.abs(act) == kk) & ~act_ot).mean()),
            "reg_decided_sim": float(((np.abs(m) == kk) & ~sim_ot).mean()),
            "ot_actual": float(((np.abs(act) == kk) & act_ot).mean()),
            "ot_sim": float(((np.abs(m) == kk) & sim_ot).mean())}
    res["key_margins_share_of_all_games"] = keys
    # end-of-regulation margin distribution near zero (sim) vs actual games' final margin when decided in regulation
    res["sim_reg_margin_abs_le_3"] = float((np.abs(rm) <= 3).mean())
    (K / "refit").mkdir(parents=True, exist_ok=True)
    (K / "refit" / "ot_diag.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k_: v for k_, v in res.items() if k_ != "key_margins_share_of_all_games"}, indent=1))
    for kk, v in keys.items():
        print(kk, {a: round(b, 3) for a, b in v.items()})


if __name__ == "__main__":
    main(sys.argv[1])
