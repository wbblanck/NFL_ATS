"""Brute-force setting search (docs/search_preregistration.md)."""
from __future__ import annotations

import itertools
import math

import numpy as np
import polars as pl

from engine.models import projection as P
from engine.models.margin_dist import MarginDist, TotalDist

KINDS = ("shifted_total", "shifted", "normal_total", "keynum")
WINDOWS = (None, 10, 5)
WS = (0.0, 0.1, 0.2, 0.3, 0.5)
HS, LAMS = (4, 8, 16), (2.5, 5.0, 10.0)
DS = (0.5, 1.0, 1.5, math.inf)
S1, S2, S3, T25 = (2008, 2015), (2016, 2019), (2020, 2024), 2025


def v1_cover_all(d: pl.DataFrame, sched: pl.DataFrame, H: float, lam: float) -> np.ndarray:
    """P(home covers the stale line) from proj-poisson-v1 (refit before each week), any line."""
    import nflreadpy as nfl

    from engine.backtest import projection_eval as PE
    games = P.team_games(nfl.load_team_stats(seasons=list(range(1999, 2026))), sched)
    tgt = d.join(sched.select("game_id", "home_team", "away_team"), on="game_id").select(
        "game_id", "season", "week", "home_team", "away_team")
    pr = PE.project_games(games, tgt, H, lam)
    mg = np.arange(-P.MAXP, P.MAXP + 1)
    out = []
    for x, ln in zip(pr, d["line"].to_list()):
        if x is None:
            out.append(0.5)
            continue
        pm = x.margin_pmf
        push = pm[mg == -ln].sum() if float(ln).is_integer() else 0.0
        out.append(float(pm[mg > -ln].sum() / max(1 - push, 1e-9)))
    return np.array(out)


def market_probs(df: pl.DataFrame, d: pl.DataFrame, kind: str, window: int | None) -> np.ndarray:
    p = np.empty(d.height)
    s = d["season"].to_numpy()
    line, close, tot = d["line"].to_numpy(), d["close"].to_numpy(), d["total"].to_numpy()
    for yr in np.unique(s):
        tr = df.filter(pl.col("season") < yr)
        if window:
            tr = tr.filter(pl.col("season") >= yr - window)
        k = s == yr
        if kind.endswith("_total"):
            td = TotalDist(kind).fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
            p[k] = td.sf(-line[k], close[k], tot[k])
        else:
            md = MarginDist(kind).fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
            p[k] = md.sf(-line[k], close[k])
    return np.clip(p, 1e-4, 1 - 1e-4)


def settings():
    out = []
    for kind, win in itertools.product(KINDS, WINDOWS):
        out.append((kind, win, 0.0, None, None, math.inf))
        for w, H, lam, dd in itertools.product(WS[1:], HS, LAMS, DS):
            out.append((kind, win, w, H, lam, dd))
    return out


def blend(pm: np.ndarray, pv: np.ndarray | None, w: float, dd: float, drift: np.ndarray) -> np.ndarray:
    if w == 0 or pv is None:
        return pm
    use = np.abs(drift) < dd
    return np.where(use, (1 - w) * pm + w * pv, pm)


def ll(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def three_stage(P_all: dict, y: np.ndarray, s: np.ndarray, half: np.ndarray, live_key, keys: list) -> dict:
    """P_all: setting -> probs. Search 2008-15, validate 2016-19, test 2020-24 half and 2025 half."""
    m1, m2 = (s >= S1[0]) & (s <= S1[1]), (s >= S2[0]) & (s <= S2[1])
    m3, m25 = (s >= S3[0]) & (s <= S3[1]) & half, (s == T25) & half
    a = sorted(keys, key=lambda k: ll(P_all[k][m1], y[m1]))[:20]
    best = min(a, key=lambda k: ll(P_all[k][m2], y[m2]))
    def cmp(k, m):
        pa, pb, yy = P_all[k][m] > 0.5, P_all[live_key][m] > 0.5, y[m]
        diff = pa != pb
        ao, bo, n = int(((pa == yy) & diff).sum()), int(((pb == yy) & diff).sum()), int(diff.sum())
        return {"N": int(m.sum()), "setting_W": int((pa == yy).sum()), "live_W": int((pb == yy).sum()), "differ": n,
                "setting_only": ao, "live_only": bo, "z": (ao - bo) / math.sqrt(n) if n else 0.0,
                "ll_setting": ll(P_all[k][m], y[m]), "ll_live": ll(P_all[live_key][m], y[m])}
    return {"best": best, "search_ll": ll(P_all[best][m1], y[m1]), "live_search_ll": ll(P_all[live_key][m1], y[m1]),
            "valid_ll": ll(P_all[best][m2], y[m2]), "live_valid_ll": ll(P_all[live_key][m2], y[m2]),
            "test": cmp(best, m3), "cbs2025": cmp(best, m25)}
