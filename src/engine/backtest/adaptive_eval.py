"""Evaluation of the adaptive model (docs/adaptive_preregistration.md)."""
from __future__ import annotations

import itertools
import math

import numpy as np
import polars as pl

from engine.backtest import gap2022 as G
from engine.backtest import total as T
from engine.features.efficiency_v6 import with_order_time
from engine.models import adaptive as A
from engine.models.margin_dist import TotalDist
from engine.picks.grading import is_half_point



def metrics(cache: str | None = None) -> pl.DataFrame:
    """Per team-game efficiency (the v6 play-by-play metrics), built once and cached as parquet."""
    from engine import config
    from engine.backtest.projection_v6_eval import load_metrics
    return load_metrics(cache or str(config.ROOT / "data" / "cache"))[0]

TUNE1 = (2007, 2015)
VAL2, CONF = (2016, 2019), (2020, 2024)
GRID1 = {"q": (0.5, 1.0, 2.0, 4.0), "s": (0.2, 0.35, 0.5), "p0": (4.0, 16.0), "rho": (0.0, 0.5, 1.0, 2.0)}
GRID2 = {"H": (2.0, 4.0, 8.0, math.inf), "lam": (0.1, 1.0, 10.0)}


def games_frame(sched: pl.DataFrame) -> pl.DataFrame:
    from engine.data import nflverse
    s = with_order_time(nflverse.with_kickoff(sched)).filter(pl.col("season") >= 1999, pl.col("result").is_not_null())
    return s.sort("kickoff_utc", "game_id").select("game_id", "season", "week", "game_type", "home_team",
                                                   "away_team", "result", "location", "spread_line", "total_line")


def fit_k(games: pl.DataFrame, eff: dict) -> float:
    g = games.filter(pl.col("season").is_between(*TUNE1), pl.col("game_type") == "REG")
    x, y = [], []
    for r in g.iter_rows(named=True):
        eh, ea = eff.get((r["game_id"], A._f(r["home_team"]))), eff.get((r["game_id"], A._f(r["away_team"])))
        if eh is not None and ea is not None:
            x.append(eh - ea); y.append(r["result"])
    X = np.column_stack([np.ones(len(x)), x])
    return float(np.linalg.lstsq(X, np.array(y, float), rcond=None)[0][1])


def tune_layer1(games, eff, k):
    reg = games.filter(pl.col("game_type") == "REG", pl.col("season").is_between(*TUNE1))
    ids = set(reg["game_id"].to_list())
    y = dict(zip(reg["game_id"].to_list(), reg["result"].to_list()))
    rows = []
    for q, s, p0, rho in itertools.product(*GRID1.values()):
        pr = A.ratings(games.filter(pl.col("season") <= TUNE1[1]), eff, q, s, p0, rho, k)
        pr = pr.filter(pl.col("game_id").is_in(list(ids)))
        e = np.array([y[g] for g in pr["game_id"].to_list()]) - pr["pred_margin"].to_numpy()
        rows.append({"q": q, "s": s, "p0": p0, "rho": rho, "mse": float(np.mean(e ** 2)), "n": len(e)})
    t = pl.DataFrame(rows).sort("mse")
    return t, t.row(0, named=True)


def dataset(games: pl.DataFrame, pred: pl.DataFrame) -> pl.DataFrame:
    """REG games 2008-2025 with proxy line, market close/total, live cover probability and Layer 1 margin."""
    from engine.backtest.holdout2025 import cbs_opens_2025
    df, sched = T.load()
    reg = sched.filter(pl.col("game_type") == "REG")
    book = G.match(G.load_xlsx(), reg.filter(pl.col("season").is_between(2014, 2024))).select("game_id", "b_open")
    cbs = cbs_opens_2025(sched)
    d = df.join(reg.select("game_id", "week"), on="game_id").join(book, on="game_id", how="left") \
        .join(cbs, on="game_id", how="left").join(pred.select("game_id", "pred_margin"), on="game_id")
    d = d.with_columns(pl.when(pl.col("season") <= 2013).then(pl.col("open"))
                       .when(pl.col("season") <= 2024).then(pl.col("b_open"))
                       .otherwise(pl.col("cbs_open")).alias("line"))
    d = d.filter(pl.col("season").is_between(2008, 2025), pl.col("line").is_not_null(),
                 pl.col("margin") != -pl.col("line"))
    p = np.empty(d.height)
    s = d["season"].to_numpy()
    for yr in np.unique(s):
        tr = df.filter(pl.col("season") < yr)
        td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
        k = s == yr
        p[k] = td.sf(-d["line"].to_numpy()[k], d["close"].to_numpy()[k], d["total"].to_numpy()[k])
    return d.with_columns(pl.Series("p_live", p), (pl.col("close") - pl.col("line")).alias("drift"),
                          (pl.col("margin") > -pl.col("line")).cast(pl.Float64).alias("y"),
                          pl.col("line").map_elements(is_half_point, return_dtype=pl.Boolean).alias("half")) \
        .sort("season", "week", "game_id")


def walk(d: pl.DataFrame, H: float, lam: float, lo: int, hi: int) -> tuple[np.ndarray, list]:
    """Weekly re-fit; returns p_adaptive for every game (nan outside lo..hi) and the fitted weights by week."""
    X = A.features(d["p_live"].to_numpy(), d["pred_margin"].to_numpy(), d["line"].to_numpy(), d["drift"].to_numpy())
    y = d["y"].to_numpy()
    s, w = d["season"].to_numpy(), d["week"].to_numpy()
    t = s * 100 + w
    out = np.full(d.height, np.nan)
    coefs = []
    for key in np.unique(t[(s >= lo) & (s <= hi)]):
        tr = t < key
        age = (key // 100) - s[tr] + (1 - w[tr] / 18.0) * 0          # age in seasons (whole seasons)
        wt = np.ones(tr.sum()) if math.isinf(H) else 0.5 ** (age / H)
        b = A.fit_logit(X[tr], y[tr], wt, lam)
        te = t == key
        out[te] = 1 / (1 + np.exp(-(X[te] @ b)))
        coefs.append({"season": int(key // 100), "week": int(key % 100), "b": [float(v) for v in b]})
    return out, coefs


def logloss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def compare(pa: np.ndarray, pb: np.ndarray, y: np.ndarray) -> dict:
    a, b = pa > 0.5, pb > 0.5
    diff = a != b
    ao, bo = int(((a == y) & diff).sum()), int(((b == y) & diff).sum())
    n = int(diff.sum())
    return {"N": int(len(y)), "adaptive_W": int((a == y).sum()), "live_W": int((b == y).sum()), "differ": n,
            "adaptive_only": ao, "live_only": bo, "z": (ao - bo) / math.sqrt(n) if n else 0.0,
            "logloss_adaptive": logloss(pa, y), "logloss_live": logloss(pb, y)}
