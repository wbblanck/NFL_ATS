"""Turnover and late-score luck (docs/turnover_luck_preregistration.md): 6 inputs built from earlier games of the
same season, each "away minus home" (positive favors home), tested beyond the live model exactly as in
engine.backtest.patterns (discovery 2008-2013 fixes the sign, confirmation 2014-2024 decides, Holm over 6)."""
from __future__ import annotations

import math
from collections import defaultdict, deque

import numpy as np
import polars as pl

from engine.backtest import patterns as P
from engine.data import nflverse

NAMES = ["to_last", "to_last4", "to_season", "fumble_luck", "close_record", "late_cover_flip"]
SEASONS = list(range(2008, 2026))


def team_games() -> pl.DataFrame:
    """Per team-game: giveaways, takeaways, own and opponent fumbles and how many each side recovered."""
    import nflreadpy as nfl
    t = nfl.load_team_stats(seasons=SEASONS).filter(pl.col("season_type") == "REG")
    z = lambda c: pl.col(c).fill_null(0)
    t = t.select("season", "week", "team", "opponent_team", "game_id",
                 (z("passing_interceptions") + z("sack_fumbles_lost") + z("rushing_fumbles_lost")
                  + z("receiving_fumbles_lost")).alias("give"),
                 (z("sack_fumbles") + z("rushing_fumbles") + z("receiving_fumbles")).alias("fum"),
                 (z("sack_fumbles_lost") + z("rushing_fumbles_lost") + z("receiving_fumbles_lost")).alias("fum_lost"))
    o = t.select("game_id", pl.col("team").alias("opponent_team"), pl.col("give").alias("take"),
                 pl.col("fum").alias("opp_fum"), pl.col("fum_lost").alias("opp_fum_lost"))
    return t.join(o, on=["game_id", "opponent_team"], how="left")


def late_states(sched: pl.DataFrame) -> dict:
    """game_id -> home margin with 5:00 left in regulation (last score at or before 300 s remaining)."""
    import nflreadpy as nfl
    out = {}
    for yr in SEASONS:
        p = nfl.load_pbp(seasons=[yr]).select("game_id", "game_seconds_remaining", "total_home_score",
                                              "total_away_score")
        p = p.filter(pl.col("game_seconds_remaining") >= 300).sort("game_id", "game_seconds_remaining",
                                                                   descending=[False, True])
        last = p.group_by("game_id").agg(pl.col("total_home_score").last(), pl.col("total_away_score").last())
        for r in last.iter_rows(named=True):
            if r["total_home_score"] is not None:
                out[r["game_id"]] = r["total_home_score"] - r["total_away_score"]
    return out


def history(sched: pl.DataFrame, tg: pl.DataFrame, late: dict) -> dict:
    """game_id -> {team: (to_last, to_last4, to_season_per_game, fumble_luck, close_record, late_flip)}, built
    from games before this one in the same season."""
    s = nflverse.with_kickoff(sched).filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                                            pl.col("season").is_in(SEASONS)).sort("kickoff_utc", "game_id")
    tgi = {(r["game_id"], r["team"]): r for r in tg.iter_rows(named=True)}
    last4: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=4))
    tot, n, fl, cr, flip = defaultdict(float), defaultdict(int), defaultdict(float), defaultdict(int), {}
    out = {}
    for g in s.iter_rows(named=True):
        yr, gid, h, a = g["season"], g["game_id"], g["home_team"], g["away_team"]
        out[gid] = {}
        for t in (h, a):
            k = (yr, t)
            q = last4[k]
            out[gid][t] = (q[-1] if q else 0.0, float(sum(q)), tot[k] / n[k] if n[k] else 0.0, fl[k], float(cr[k]),
                           float(flip.get(k, 0)))
        res, sp, m5 = g["result"], g["spread_line"], late.get(gid)
        for t, sign in ((h, 1), (a, -1)):
            k = (yr, t)
            r = tgi.get((gid, t))
            if r is not None and r["take"] is not None:
                net = float(r["take"] - r["give"])
                last4[k].append(net)
                tot[k] += net
                n[k] += 1
                fumbles = (r["fum"] or 0) + (r["opp_fum"] or 0)
                recovered = ((r["fum"] or 0) - (r["fum_lost"] or 0)) + (r["opp_fum_lost"] or 0)
                fl[k] += recovered - fumbles / 2
            margin = sign * res
            if abs(margin) <= 7 and margin != 0:
                cr[k] += 1 if margin > 0 else -1
            flip[k] = 0
            if sp is not None and m5 is not None:
                cov_end = margin - sign * sp                                        # cover margin vs closing line
                cov_5 = sign * m5 - sign * sp
                if cov_5 > 0 and cov_end < 0:
                    flip[k] = 1                                                    # lost the cover late
                elif cov_5 < 0 and cov_end > 0:
                    flip[k] = -1
    return out


def features(d: pl.DataFrame, sched: pl.DataFrame, hist: dict) -> np.ndarray:
    info = {r["game_id"]: (r["home_team"], r["away_team"]) for r in sched.select("game_id", "home_team",
                                                                                   "away_team").iter_rows(named=True)}
    X = np.zeros((d.height, len(NAMES)))
    for i, gid in enumerate(d["game_id"].to_list()):
        h, a = info[gid]
        hh = hist.get(gid, {})
        if h in hh and a in hh:
            X[i] = np.array(hh[a]) - np.array(hh[h])          # away minus home: positive fades a lucky away team
    return X


def run() -> dict:
    sched, _ = nflverse.pull("schedules", save=False)
    d = P.dataset()
    tg = team_games()
    late = late_states(sched)
    F = features(d, sched, history(sched, tg, late))
    y, p, s = d["y"].to_numpy(), np.clip(d["p_live"].to_numpy(), 1e-4, 1 - 1e-4), d["season"].to_numpy()
    off = np.log(p / (1 - p))
    disc, conf, c25 = (s >= P.DISC[0]) & (s <= P.DISC[1]), (s >= P.CONF[0]) & (s <= P.CONF[1]), s == 2025
    rows = []
    for j, nm in enumerate(NAMES):
        f = F[:, j]
        bd, sd = P.fit_offset(f[disc], y[disc], off[disc])
        sign = 1.0 if bd >= 0 else -1.0
        bc, sc = P.fit_offset(f[conf], y[conf], off[conf])
        z = sign * bc / sc if sc and math.isfinite(sc) else 0.0
        rows.append({"input": nm, "disc_b": bd, "disc_z": bd / sd if math.isfinite(sd) else 0.0, "sign": sign,
                     "conf_b": bc, "conf_z_in_sign": z, "conf_p": 0.5 * math.erfc(z / math.sqrt(2)),
                     "nonzero_share": float((f != 0).mean()),
                     "disc_effect": P.effect(f[disc], y[disc], p[disc], sign),
                     "conf_effect": P.effect(f[conf], y[conf], p[conf], sign),
                     "cbs2025_effect": P.effect(f[c25], y[c25], p[c25], sign)})
    order = sorted(range(len(rows)), key=lambda i: rows[i]["conf_p"])
    alive = True
    for rank, i in enumerate(order):
        thr = 0.05 / (len(rows) - rank)
        ok = alive and rows[i]["conf_p"] <= thr
        alive = ok
        rows[i]["holm_threshold"], rows[i]["pass"] = thr, ok
    checks = {"late_states": len(late), "team_games": int(tg.height),
              "flip_share": float((F[:, 5] != 0).mean())}
    return {"n_games": int(d.height), "n_disc": int(disc.sum()), "n_conf": int(conf.sum()), "checks": checks,
            "inputs": rows}
