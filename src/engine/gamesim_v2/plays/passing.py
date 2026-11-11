"""One correlated dropback (gamesim v2, sprint 1 milestone).

Sequence, each step conditional on the ones before it (spec 9.1; steps without data are marked):
  1 calls: pass rushers sampled from the league distribution (no formation or defensive-call model yet)
  2 protection vs rush -> pressure (matchups.protection)
  3 pressure -> time to throw (resampled from history given the pressure state)
  4 pressure + rushers -> sack, scramble or throw (empirical rates; no QB-decision model)
  5 target chosen by prior target share; air yards resampled given pressure
  6 receiver, QB, coverage, pressure, depth -> completion (matchups.coverage)
  7 interception on incompletions, calibrated separately by pressure and depth
  8 yards resampled given outcome and depth
Not modelled yet (no data or no model): separation, YAC mechanics, tackling, fumbles, penalties, clock, game state.
Each mechanism draws from its own stream (probability.random_streams)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from ..matchups import coverage as C, protection as P


@dataclass
class Empirics:
    """Resampling pools and rates built from dropbacks before the cutoff."""
    nr: np.ndarray
    ttt: dict            # pressure flag -> array
    sack_given: dict     # (pressure, nr bucket) -> rate
    scramble_given: dict
    air: dict            # pressure flag -> array of air yards among attempts
    int_rate: dict       # (pressure, air bucket) -> rate among incompletions
    yards_complete: dict   # air bucket -> array
    yards_sack: np.ndarray
    yards_scramble: np.ndarray


def _ab(y):
    return int(np.digitize(y, [0, 5, 10, 15, 20]))


def build_empirics(d: pl.DataFrame) -> Empirics:
    """d: dropbacks with participation, all dated before the cutoff."""
    d = d.filter(pl.col("has_part"))
    pr = (d["was_pressure"].fill_null(False) | d["sack"]).to_numpy()
    nr = np.clip(d["number_of_pass_rushers"].fill_null(4).to_numpy(), 2, 7)
    sack, scr = d["sack"].to_numpy(), d["scramble"].to_numpy()
    att = d["attempt"].to_numpy() & ~sack & ~scr
    ay = d["air_yards"].to_numpy().astype(float)
    ttt = d["time_to_throw"].to_numpy().astype(float)
    yg = d["yards_gained"].to_numpy().astype(float)
    comp, itc = d["complete"].to_numpy(), d["interception"].to_numpy()
    e = Empirics(nr=nr, ttt={}, sack_given={}, scramble_given={}, air={}, int_rate={}, yards_complete={},
                 yards_sack=yg[sack], yards_scramble=yg[scr])
    for f in (False, True):
        m = pr == f
        e.ttt[f] = ttt[m & ~np.isnan(ttt)]
        e.air[f] = ay[m & att & ~np.isnan(ay)]
        for n in range(2, 8):
            mm = m & (nr == n)
            e.sack_given[(f, n)] = sack[mm].mean() if mm.sum() else sack[m].mean()
            e.scramble_given[(f, n)] = (scr[mm & ~sack].mean()) if mm.sum() else scr[m].mean()
        for b in range(6):
            mb = m & att & ~np.isnan(ay) & (np.digitize(ay, [0, 5, 10, 15, 20]) == b) & ~comp
            e.int_rate[(f, b)] = itc[mb].mean() if mb.sum() else 0.03
    for b in range(6):
        mb = att & comp & ~np.isnan(ay) & (np.digitize(ay, [0, 5, 10, 15, 20]) == b)
        e.yards_complete[b] = yg[mb] if mb.sum() else np.array([7.0])
    return e


def target_shares(d: pl.DataFrame, team: str, before: str, games: int = 8) -> dict:
    """Share of the team's targets by receiver over its previous `games` games (point in time: games dated before `before`)."""
    x = d.filter((pl.col("posteam") == team) & (pl.col("game_date") < before) & pl.col("target").is_not_null())
    gids = x.select("game_id", "game_date").unique().sort("game_date").tail(games)["game_id"]
    t = x.filter(pl.col("game_id").is_in(gids.implode())).group_by("target").len()
    n = t["len"].sum()
    return {u: c / n for u, c in zip(t["target"], t["len"])} if n else {}


def simulate_pass_play(rs: dict, tables: dict, effects: dict, emp: Empirics, play: dict, off: dict, dfn: dict,
                       shares: dict, latent: dict | None = None) -> dict:
    """rs: random streams. tables: {'pressure': AbilityTable, 'completion': AbilityTable}. effects: realized player effects
    (one draw per game from AbilityTable.draw). off/dfn: lineups. play: one-row context (down, ydstogo, shotgun, no_huddle)."""
    latent = latent or {}
    nr = int(rs["strategy"].choice(emp.nr))
    ctx = {**play, "number_of_pass_rushers": [nr]}
    prot = P.simulate_protection(rs["matchup"], tables["pressure"], effects, ctx, {**off, "QB": off["QB"][0], "DL": dfn["DL"], "LB": dfn["LB"]},
                                 latent.get("pressure", 0.0))
    pres = prot["pressure"]
    tr = {"rushers": nr, "pressure": pres, "p_pressure": prot["p_pressure"], "protection_parts": prot["logit_parts"]}
    tr["time_to_throw"] = float(rs["outcome"].choice(emp.ttt[pres]))
    nb = min(max(nr, 2), 7)
    u = rs["outcome"].random()
    p_sack, p_scr = emp.sack_given[(pres, nb)], emp.scramble_given[(pres, nb)]
    tr["decision"] = "sack" if u < p_sack else "scramble" if u < p_sack + p_scr else "throw"
    if tr["decision"] == "sack":
        tr.update(outcome="sack", yards=float(rs["outcome"].choice(emp.yards_sack)), target=None)
        return tr
    if tr["decision"] == "scramble":
        tr.update(outcome="scramble", yards=float(rs["outcome"].choice(emp.yards_scramble)), target=None)
        return tr
    recv = list(shares)
    target = None
    if recv:
        w = np.array([shares[r] for r in recv])
        target = recv[int(rs["strategy"].choice(len(recv), p=w / w.sum()))]
    air = float(rs["outcome"].choice(emp.air[pres]))
    cctx = {**play, "air_yards": [air], "was_pressure": [pres]}
    cat = C.simulate_catch(rs["matchup"], tables["completion"], effects, cctx, target, off["QB"][0], dfn, latent.get("completion", 0.0))
    b = _ab(air)
    tr.update(target=target, air_yards=air, p_complete=cat["p_complete"], coverage_parts=cat["logit_parts"])
    if cat["complete"]:
        tr.update(outcome="complete", yards=float(rs["outcome"].choice(emp.yards_complete[b])))
    elif rs["outcome"].random() < emp.int_rate[(pres, b)]:
        tr.update(outcome="interception", yards=0.0)
    else:
        tr.update(outcome="incomplete", yards=0.0)
    return tr
