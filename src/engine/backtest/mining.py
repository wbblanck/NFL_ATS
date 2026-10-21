"""Open pattern search (docs/mining_preregistration.md).

Every rule "in situation C take side S" is scored on the search set (2008-2019) by how much S beat the live model's
own cover probability; the same search is run on histories simulated from the model (luck check); the top 25 are
tested on the holdout (2020-2025)."""
from __future__ import annotations

import itertools
import math
from collections import defaultdict

import numpy as np
import polars as pl

from engine.backtest import patterns as PT
from engine.data import nflverse

SEARCH, HOLD = (2008, 2019), (2020, 2025)
MIN_N, TOP = 60, 25
TZ = {"ARI": -3, "ATL": 0, "BAL": 0, "BUF": 0, "CAR": 0, "CHI": -1, "CIN": 0, "CLE": 0, "DAL": -1, "DEN": -2,
      "DET": 0, "GB": -1, "HOU": -1, "IND": 0, "JAX": 0, "KC": -1, "LA": -3, "LAC": -3, "LV": -3, "MIA": 0,
      "MIN": -1, "NE": 0, "NO": -1, "NYG": 0, "NYJ": 0, "PHI": 0, "PIT": 0, "SEA": -3, "SF": -3, "TB": 0,
      "TEN": -1, "WAS": 0, "OAK": -3, "SD": -3, "STL": -1}
SIDES = ["home", "away", "favorite", "underdog", "move side", "against move"]


def team_form(sched: pl.DataFrame) -> dict:
    """(game_id, team) -> pre-game form flags from earlier regular-season games of the same season."""
    s = nflverse.with_kickoff(sched).filter(pl.col("game_type") == "REG", pl.col("result").is_not_null()) \
        .sort("kickoff_utc", "game_id")
    hist: dict[tuple, list] = defaultdict(list)          # (season, team) -> [(margin, covered or None)]
    out = {}
    for g in s.iter_rows(named=True):
        yr = g["season"]
        for t, sign in ((g["home_team"], 1), (g["away_team"], -1)):
            h = hist[(yr, t)]
            last = h[-1] if h else None
            cov = [c for _, c in h if c is not None]
            wins = [m > 0 for m, _ in h]
            out[(g["game_id"], t)] = {
                "last_bigwin": bool(last and last[0] >= 14), "last_bigloss": bool(last and last[0] <= -14),
                "last_cover": bool(last and last[1] is True), "last_nocover": bool(last and last[1] is False),
                "cover3": len(cov) >= 3 and all(cov[-3:]), "nocover3": len(cov) >= 3 and not any(cov[-3:]),
                "win3": len(wins) >= 3 and all(wins[-3:]), "lose3": len(wins) >= 3 and not any(wins[-3:]),
                "good": len(wins) >= 4 and np.mean(wins) >= 2 / 3, "bad": len(wins) >= 4 and np.mean(wins) <= 1 / 3}
        for t, sign in ((g["home_team"], 1), (g["away_team"], -1)):
            m = sign * g["result"]
            fav_by = None if g["spread_line"] is None else sign * g["spread_line"]
            hist[(yr, t)].append((m, None if fav_by is None or m == fav_by else m > fav_by))
    return out


def situations(d: pl.DataFrame, sched: pl.DataFrame) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """(situational masks grouped by feature for pairing, identity masks)."""
    info = {r["game_id"]: r for r in sched.iter_rows(named=True)}
    form = team_form(sched)
    n = d.height
    line, close, total, wk = (d[c].to_numpy() for c in ("line", "close", "total", "week"))
    drift = close - line
    sea = d["season"].to_numpy()
    q1, q2 = np.quantile(total[(sea >= SEARCH[0]) & (sea <= SEARCH[1])], [1 / 3, 2 / 3])
    F: dict[str, dict[str, np.ndarray]] = defaultdict(dict)
    a = np.abs(line)
    F["week"] = {f"weeks {lo}-{hi}": (wk >= lo) & (wk <= hi) for lo, hi in ((1, 4), (5, 8), (9, 12), (13, 16), (17, 18))}
    F["spread"] = {"spread <=2.5": a <= 2.5, "spread 3": a == 3, "spread 3.5-6.5": (a >= 3.5) & (a <= 6.5),
                   "spread 7": a == 7, "spread 7.5-9.5": (a >= 7.5) & (a <= 9.5), "spread >=10": a >= 10}
    F["homefav"] = {"home favored": line < 0, "home underdog": line > 0}
    F["total"] = {"low total": total <= q1, "mid total": (total > q1) & (total <= q2), "high total": total > q2}
    toward_fav = np.sign(drift) == np.sign(line)                # line < 0 (home fav) and drift < 0: toward home=fav
    mv = np.abs(drift)
    F["move"] = {"no move": mv == 0, "move 0.5": mv == 0.5, "move 1": mv == 1, "move 1.5-2.5": (mv >= 1.5) & (mv <= 2.5),
                 "move 3+": mv >= 3}
    F["movedir"] = {"moved toward favorite": (mv > 0) & toward_fav, "moved toward underdog": (mv > 0) & ~toward_fav}
    F["keycross"] = {"move crosses 3 or 7": np.array([any(min(abs(x), abs(y)) < k < max(abs(x), abs(y)) for k in (3, 7))
                                                      for x, y in zip(line, close)])}
    cols = defaultdict(lambda: np.zeros(n, bool))
    for i, gid in enumerate(d["game_id"].to_list()):
        r = info[gid]
        h, aw = r["home_team"], r["away_team"]
        hr = int((r["gametime"] or "13:00").split(":")[0])
        cols["Thursday"][i] = r["weekday"] == "Thursday"
        cols["Monday"][i] = r["weekday"] == "Monday"
        cols["Sunday night"][i] = r["weekday"] == "Sunday" and hr >= 19
        cols["Sunday afternoon late"][i] = r["weekday"] == "Sunday" and 16 <= hr < 19
        cols["neutral site"][i] = r["location"] == "Neutral"
        cols["division game"][i] = r["div_game"] == 1
        cols["dome or closed"][i] = (r["roof"] or "") in ("dome", "closed")
        cols["grass"][i] = "grass" in (r["surface"] or "")
        cols["cold (<40F)"][i] = r["temp"] is not None and r["temp"] < 40
        cols["windy (15+ mph)"][i] = (r["wind"] or 0) >= 15
        hrst, arst = r["home_rest"], r["away_rest"]
        if hrst is not None and arst is not None:
            cols["home 2+ more rest days"][i] = hrst - arst >= 2
            cols["away 2+ more rest days"][i] = arst - hrst >= 2
            cols["home off bye"][i] = hrst >= 13
            cols["away off bye"][i] = arst >= 13
        if r["location"] != "Neutral" and h in TZ and aw in TZ:
            z = abs(TZ[h] - TZ[aw])
            cols["away travels 0 zones"][i] = z == 0
            cols["away travels 1 zone"][i] = z == 1
            cols["away travels 2-3 zones"][i] = z >= 2
        for side, t in (("home", h), ("away", aw)):
            for k, v in form.get((gid, t), {}).items():
                cols[f"{side} {k}"][i] = v
    groups = {"day": ["Thursday", "Monday", "Sunday night", "Sunday afternoon late"], "site": ["neutral site"],
              "div": ["division game"], "roof": ["dome or closed"], "surface": ["grass"], "cold": ["cold (<40F)"],
              "wind": ["windy (15+ mph)"], "rest": ["home 2+ more rest days", "away 2+ more rest days"],
              "bye": ["home off bye", "away off bye"],
              "travel": ["away travels 0 zones", "away travels 1 zone", "away travels 2-3 zones"]}
    for side in ("home", "away"):
        for k in ("last_bigwin", "last_bigloss", "last_cover", "last_nocover", "cover3", "nocover3", "win3", "lose3",
                  "good", "bad"):
            groups[f"{side}_{k.split('_')[0] if k.startswith('last') else k}"] = \
                groups.get(f"{side}_{k.split('_')[0] if k.startswith('last') else k}", []) + [f"{side} {k}"]
    for g, names in groups.items():
        for nm in names:
            F[g][nm] = cols[nm]
    ident = {}
    for col, lab in (("home_team", "home team"), ("away_team", "away team"), ("home_coach", "home coach"),
                     ("away_coach", "away coach"), ("referee", "referee")):
        vals = [info[g][col] for g in d["game_id"].to_list()]
        for v in set(vals):
            if v:
                ident[f"{lab} {v}"] = np.array([x == v for x in vals])
    return F, ident


def rules(F: dict, ident: dict) -> tuple[list[str], np.ndarray]:
    names, masks = [], []
    flat = [(g, nm, m) for g, d_ in F.items() for nm, m in d_.items()]
    for g, nm, m in flat:
        names.append(nm); masks.append(m)
    for (g1, n1, m1), (g2, n2, m2) in itertools.combinations(flat, 2):
        if g1 != g2:
            names.append(f"{n1} & {n2}"); masks.append(m1 & m2)
    for nm, m in ident.items():
        names.append(nm); masks.append(m)
    return names, np.array(masks)


def side_arrays(d: pl.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    """Per side: (valid, pick_home)."""
    line, drift = d["line"].to_numpy(), (d["close"] - d["line"]).to_numpy()
    allv = np.ones(d.height, bool)
    return [(allv, allv), (allv, ~allv), (line != 0, line < 0), (line != 0, line > 0),
            (drift != 0, drift < 0), (drift != 0, drift > 0)]


def score(M: np.ndarray, y: np.ndarray, p: np.ndarray, sides, sel: np.ndarray) -> dict:
    """n, wins, expected, z for every (rule, side) restricted to games in `sel`."""
    Ms = (M & sel).astype(np.float32)
    out = {}
    for si, (valid, ph) in enumerate(sides):
        v = valid & sel
        won = np.where(ph, y == 1, y == 0) & v
        pred = np.where(ph, p, 1 - p) * v
        var = pred * (1 - pred)
        n, W, E, Var = Ms @ v.astype(np.float32), Ms @ won.astype(np.float32), Ms @ pred.astype(np.float32), \
            Ms @ var.astype(np.float32)
        z = np.where(Var > 0, (W - E) / np.sqrt(np.maximum(Var, 1e-9)), 0.0)
        out[si] = (n, W, E, z)
    return out


def best(sc: dict, k: int = TOP, min_n: int = MIN_N):
    rows = []
    for si, (n, W, E, z) in sc.items():
        ok = np.where(n >= min_n)[0]
        for r in ok:
            rows.append((float(z[r]), int(r), si, int(n[r]), int(W[r]), float(E[r])))
    rows.sort(reverse=True)
    return rows[:k], rows


def run(n_null: int = 50, seed: int = 3) -> dict:
    sched, _ = nflverse.pull("schedules", save=False)
    d = PT.dataset()
    F, ident = situations(d, sched)
    names, M = rules(F, ident)
    sides = side_arrays(d)
    y, p, s = d["y"].to_numpy(), np.clip(d["p_live"].to_numpy(), 1e-4, 1 - 1e-4), d["season"].to_numpy()
    search, hold = (s >= SEARCH[0]) & (s <= SEARCH[1]), (s >= HOLD[0]) & (s <= HOLD[1])
    top, allrows = best(score(M, y, p, sides, search))
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(n_null):
        ysim = (rng.random(len(p)) < p).astype(float)
        t, a_ = best(score(M, ysim, p, sides, search))
        zs = np.array([r[0] for r in a_])
        null.append({"max_z": float(zs.max()), "top25_min_z": float(t[-1][0]), "n_z_over_3": int((zs > 3).sum()),
                     "n_z_over_2": int((zs > 2).sum())})
    real_z = np.array([r[0] for r in allrows])
    hs = score(M, y, p, sides, hold)
    c25 = score(M, y, p, sides, s == 2025)
    tested = []
    for z, r, si, n, W, E in top:
        hn, hW, hE, hz = (x[r] for x in hs[si])
        cn, cW, cE, _ = (x[r] for x in c25[si])
        pval = 0.5 * math.erfc(float(hz) / math.sqrt(2))
        tested.append({"rule": names[r], "side": SIDES[si], "search": {"n": n, "won": W, "expected": round(E, 1), "z": z},
                       "holdout": {"n": int(hn), "won": int(hW), "expected": round(float(hE), 1), "z": float(hz), "p": pval},
                       "cbs2025": {"n": int(cn), "won": int(cW), "expected": round(float(cE), 1)}})
    order = sorted(range(len(tested)), key=lambda i: tested[i]["holdout"]["p"])
    alive = True
    for rank, i in enumerate(order):
        thr = 0.05 / (len(tested) - rank)
        ok = alive and tested[i]["holdout"]["p"] <= thr
        alive = ok
        tested[i]["holm_threshold"], tested[i]["pass"] = thr, ok
    return {"n_rules": len(names), "n_rule_side_scored": len(allrows), "search_games": int(search.sum()),
            "holdout_games": int(hold.sum()),
            "real": {"max_z": float(real_z.max()), "top25_min_z": top[-1][0], "n_z_over_3": int((real_z > 3).sum()),
                     "n_z_over_2": int((real_z > 2).sum())},
            "null": null, "top25": tested}
