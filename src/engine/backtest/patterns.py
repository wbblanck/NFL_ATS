"""Overlooked-patterns scan (docs/patterns_preregistration.md): 15 situational inputs, each tested for whether it
predicts covers against the stale line beyond the live model (logit of its cover probability as a fixed offset).
Discovery 2008-2013 fixes the sign; confirmation 2014-2024 decides (one-sided, Holm over 15)."""
from __future__ import annotations

import math
from collections import defaultdict, deque

import numpy as np
import polars as pl

from engine.backtest import adaptive_eval as V
from engine.data import nflverse
from engine.models import adaptive as A

DISC, CONF = (2008, 2013), (2014, 2024)
NAMES = ["home_dog", "dog", "nomove_home", "move_to_dog", "move_to_fav", "early_move", "late_move", "key_cross",
         "division_dog", "primetime_dog", "big_fav_dog", "rest", "bounce", "ats_fade", "wind_dog"]


def dataset() -> pl.DataFrame:
    sched, _ = nflverse.pull("schedules", save=False)
    games = V.games_frame(sched)
    pred = A.ratings(games, {}, 0.5, 0.35, 16.0, 0.0, 0.0)          # pred_margin is unused here
    return V.dataset(games, pred)


def history(sched: pl.DataFrame) -> dict:
    """game_id -> {(team): (lost_by_14_as_fav_last_game, covered_last_3)} from earlier games of the same season."""
    s = nflverse.with_kickoff(sched).filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                                            pl.col("spread_line").is_not_null()).sort("kickoff_utc", "game_id")
    last = {}
    covers: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=3))
    out = {}
    for g in s.iter_rows(named=True):
        yr = g["season"]
        h, a = g["home_team"], g["away_team"]
        out[g["game_id"]] = {t: (last.get((yr, t), False), len(covers[(yr, t)]) == 3 and all(covers[(yr, t)]))
                             for t in (h, a)}
        res, sp = g["result"], g["spread_line"]                  # spread_line > 0: home favored by that much
        for t, sign in ((h, 1), (a, -1)):
            margin, fav_by = sign * res, sign * sp
            last[(yr, t)] = fav_by > 0 and margin <= -14
            if margin != fav_by:
                covers[(yr, t)].append(margin > fav_by)
    return out


def features(d: pl.DataFrame, sched: pl.DataFrame) -> np.ndarray:
    info = {r["game_id"]: r for r in sched.select("game_id", "home_team", "away_team", "div_game", "weekday",
                                                  "gametime", "home_rest", "away_rest", "roof", "wind").iter_rows(named=True)}
    hist = history(sched)
    line, close, wk = d["line"].to_numpy(), d["close"].to_numpy(), d["week"].to_numpy()
    drift = close - line
    dirn = np.where(drift < 0, 1.0, np.where(drift > 0, -1.0, 0.0))
    dog = np.where(line > 0, 1.0, -1.0)
    cross = np.array([any((min(abs(a), abs(b)) < k < max(abs(a), abs(b))) or (np.sign(a) != np.sign(b) and k < 1)
                          for k in (3, 7)) for a, b in zip(line, close)])
    X = {n: np.zeros(d.height) for n in NAMES}
    X["home_dog"] = (line > 0).astype(float)
    X["dog"] = dog
    X["nomove_home"] = (drift == 0).astype(float)
    X["move_to_dog"] = np.where(dirn == dog, dirn, 0.0)
    X["move_to_fav"] = np.where((dirn != 0) & (dirn == -dog), dirn, 0.0)
    X["early_move"] = np.where(wk <= 4, dirn, 0.0)
    X["late_move"] = np.where(wk >= 15, dirn, 0.0)
    X["key_cross"] = np.where(cross, dirn, 0.0)
    for i, gid in enumerate(d["game_id"].to_list()):
        r = info[gid]
        X["division_dog"][i] = dog[i] * (r["div_game"] == 1)
        hr = int((r["gametime"] or "13:00").split(":")[0])
        prime = r["weekday"] in ("Thursday", "Monday") or hr >= 19
        X["primetime_dog"][i] = dog[i] * prime
        X["big_fav_dog"][i] = dog[i] * (abs(line[i]) >= 10)
        if r["home_rest"] is not None and r["away_rest"] is not None:
            X["rest"][i] = np.sign(r["home_rest"] - r["away_rest"])
        hh = hist.get(gid, {})
        hb, hc = hh.get(r["home_team"], (False, False))
        ab, ac = hh.get(r["away_team"], (False, False))
        X["bounce"][i] = float(hb) - float(ab)
        X["ats_fade"][i] = float(ac) - float(hc)
        outdoor = (r["roof"] or "") in ("outdoors", "open")
        X["wind_dog"][i] = dog[i] * (outdoor and (r["wind"] or 0) >= 15)
    return np.column_stack([X[n] for n in NAMES])


def fit_offset(f: np.ndarray, y: np.ndarray, off: np.ndarray) -> tuple[float, float]:
    """Coefficient and SE of f in logit P = off + b f (Newton)."""
    b = 0.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-(off + b * f)))
        g, h = float(np.sum(f * (y - p))), float(np.sum(f * f * p * (1 - p)))
        if h <= 0:
            return 0.0, math.inf
        step = g / h
        b += step
        if abs(step) < 1e-10:
            break
    p = 1 / (1 + np.exp(-(off + b * f)))
    return b, 1 / math.sqrt(float(np.sum(f * f * p * (1 - p))))


def effect(f: np.ndarray, y: np.ndarray, p: np.ndarray, sign: float) -> dict:
    """Cover rate of the side the pattern favors (in its discovery sign) vs the rate the live model predicted."""
    k = f != 0
    side_home = (sign * f[k]) > 0
    won = np.where(side_home, y[k] == 1, y[k] == 0)
    pred = np.where(side_home, p[k], 1 - p[k])
    return {"games": int(k.sum()), "won": int(won.sum()), "rate": float(won.mean()) if k.any() else None,
            "model_expected": float(pred.mean()) if k.any() else None}


def run() -> dict:
    sched, _ = nflverse.pull("schedules", save=False)
    d = dataset()
    F = features(d, sched)
    y, p, s = d["y"].to_numpy(), np.clip(d["p_live"].to_numpy(), 1e-4, 1 - 1e-4), d["season"].to_numpy()
    off = np.log(p / (1 - p))
    disc, conf, c25 = (s >= DISC[0]) & (s <= DISC[1]), (s >= CONF[0]) & (s <= CONF[1]), s == 2025
    rows = []
    for j, n in enumerate(NAMES):
        f = F[:, j]
        bd, sd = fit_offset(f[disc], y[disc], off[disc])
        sign = 1.0 if bd >= 0 else -1.0
        bc, sc = fit_offset(f[conf], y[conf], off[conf])
        z = sign * bc / sc if sc and math.isfinite(sc) else 0.0
        pval = 0.5 * math.erfc(z / math.sqrt(2))
        rows.append({"pattern": n, "disc_b": bd, "disc_z": bd / sd if math.isfinite(sd) else 0.0, "sign": sign,
                     "conf_b": bc, "conf_z_in_sign": z, "conf_p": pval,
                     "disc_effect": effect(f[disc], y[disc], p[disc], sign),
                     "conf_effect": effect(f[conf], y[conf], p[conf], sign),
                     "cbs2025_effect": effect(f[c25], y[c25], p[c25], sign)})
    order = sorted(range(len(rows)), key=lambda i: rows[i]["conf_p"])
    alive = True
    for rank, i in enumerate(order):
        thr = 0.05 / (len(rows) - rank)
        ok = alive and rows[i]["conf_p"] <= thr
        alive = ok
        rows[i]["holm_threshold"], rows[i]["pass"] = thr, ok
    return {"n_games": int(d.height), "n_disc": int(disc.sum()), "n_conf": int(conf.sum()), "patterns": rows}
