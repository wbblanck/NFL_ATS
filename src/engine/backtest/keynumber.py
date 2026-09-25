"""Key-number fix evaluation (docs/keynumber_preregistration.md)."""
from __future__ import annotations

import datetime as dt
import glob
import math
import re

import numpy as np
import polars as pl

from engine import config
from engine.backtest import calibration as C
from engine.backtest.phase4 import load
from engine.data import cbs_lines, nflverse
from engine.models.margin_dist import MarginDist
from engine.picks.grading import is_half_point

KINDS = ("shifted", "keynum")


def _ats(p, y):
    w = int(((p > 0.5) == (y == 1)).sum()); n = len(y); r = w / n
    return {"W": w, "L": n - w, "N": n, "win_rate": r, "se": math.sqrt(r * (1 - r) / n)}


def primary() -> dict:
    df, _ = load()
    rows = []
    for s in range(2007, 2022):
        tr = df.filter(pl.col("season") < s)
        te = df.filter(pl.col("season") == s, pl.col("open").is_not_null(), pl.col("margin") != -pl.col("open"))
        y = (te["margin"].to_numpy() > -te["open"].to_numpy()).astype(float)
        for k in KINDS:
            md = MarginDist(kind=k).fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
            p = md.sf(-te["open"].to_numpy(), te["close"].to_numpy())
            rows += [{"season": s, "kind": k, "p": pi, "y": yi, "open": o, "close": c}
                     for pi, yi, o, c in zip(p, y, te["open"].to_numpy(), te["close"].to_numpy())]
    return _summarize(pl.DataFrame(rows))


def _summarize(R: pl.DataFrame) -> dict:
    out = {}
    key_adj = pl.col("open").abs().is_in([2.5, 3.5, 6.5, 7.5])
    for k in KINDS:
        x = R.filter(pl.col("kind") == k)
        p, y = x["p"].to_numpy(), x["y"].to_numpy()
        xa = x.filter(key_adj)
        out[k] = {"log_loss": C.log_loss(p, y), "brier": C.brier(p, y), **_ats(p, y),
                  "key_adjacent": _ats(xa["p"].to_numpy(), xa["y"].to_numpy()) if xa.height else None}
    a, b = R.filter(pl.col("kind") == "shifted")["p"].to_numpy(), R.filter(pl.col("kind") == "keynum")["p"].to_numpy()
    out["picks_changed"] = int(((a > 0.5) != (b > 0.5)).sum())
    return out


def confirmation(season: int) -> dict | None:
    files = sorted(glob.glob(str(config.ROOT / f"docs/evidence/probe/*/cbs_odds_{season}_w*.html")))
    if not files:
        return None
    sched, _ = nflverse.regular_season_schedule(save=False)
    latest = {}
    for f in files:
        latest[int(re.search(r"_w(\d+)\.html", f).group(1))] = f
    reg = sched.filter(pl.col("season") == season)
    opens = []
    for w, f in sorted(latest.items()):
        for r in cbs_lines.match_games(cbs_lines.parse_odds_page(open(f).read()), reg):
            if r.get("game_id") and r.get("spread") is not None:
                opens.append({"game_id": r["game_id"], "open": float(r["spread"])})
    if not opens:
        return {"season": season, "games_with_open": 0}
    op = pl.DataFrame(opens).unique("game_id", keep="first")
    g = reg.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null()) \
        .select("game_id", pl.col("result").alias("margin"), (-pl.col("spread_line")).alias("close")).join(op, on="game_id")
    g = g.filter(pl.col("open").map_elements(is_half_point, return_dtype=pl.Boolean))  # primary: half-point opens
    hist = sched.filter(pl.col("season") < season, pl.col("result").is_not_null(), pl.col("spread_line").is_not_null())
    y = (g["margin"].to_numpy() > -g["open"].to_numpy()).astype(float)
    res = {"season": season, "games_half_point_open": g.height}
    for k in KINDS:
        md = MarginDist(kind=k).fit(-hist["spread_line"].to_numpy(), hist["result"].to_numpy())
        p = md.sf(-g["open"].to_numpy(), g["close"].to_numpy())
        res[k] = {"log_loss": C.log_loss(p, y), **_ats(p, y)}
    return res
