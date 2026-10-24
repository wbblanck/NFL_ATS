"""Key-number pick in no-move and straddle games (docs/keynum_combo_preregistration.md). Writes aggregate numbers
only to data/backtests/keynum_combo.json: per-game AusSportsBetting lines are personal-use and stay off git."""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from engine import config
from engine.backtest import edge2 as E
from engine.backtest.variants2026 import _straddle, binom_sf
from engine.data import nflverse
from engine.models.margin_dist import MarginDist, TotalDist
from engine.picks import final

SETS = {"asb_2022_2024": (2022, 2024), "asb_2014_2021": (2014, 2021)}


def rule_masks(L: np.ndarray, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nomove = np.abs(m - L) < 1
    strad = np.array([_straddle(a, b) for a, b in zip(L, m)], bool)
    return nomove, strad


def compare(off, kn, y, mask, cm=None) -> dict:
    d = mask & (kn != off)
    w = int((kn == y)[d].sum())
    out = {"games": int(mask.sum()), "official": [int((off == y)[mask].sum()), int(mask.sum())],
           "kn": [int((kn == y)[mask].sum()), int(mask.sum())],
           "differ": int(d.sum()), "kn_wins": w, "official_wins": int(d.sum()) - w, "p": binom_sf(w, int(d.sum()))}
    if cm is not None:
        out["cover_margin_diff"] = float(np.mean(np.where(kn, cm, -cm)[mask] - np.where(off, cm, -cm)[mask]))
    return out


def evaluate(off, key, L, m, y, mask, cm=None) -> dict:
    nomove, strad = rule_masks(L, m)
    use = nomove | strad
    kn = np.where(use, key, off)
    res = compare(off, kn, y, mask, cm)
    res["no_move_only"] = compare(off, np.where(nomove, key, off), y, mask)
    res["straddle_only"] = compare(off, np.where(strad & ~nomove, key, off), y, mask)
    res["keynum_everywhere"] = compare(off, key, y, mask)
    return res, kn


def asb() -> dict:
    d, df = E.dataset()
    D = E.dists(df, range(2014, 2025))
    L, m, M, s = (d[c].to_numpy() for c in ("b_open", "b_close", "margin", "season"))
    off = E.p_cover(d, D, m) > 0.5
    key = np.empty(d.height, bool)
    for yr in range(2014, 2025):
        tr = df.filter(pl.col("season") < yr)
        kd = MarginDist(kind=final.SHADOW).fit(tr["close"].to_numpy(), tr["margin"].to_numpy())
        k = s == yr
        key[k] = kd.sf(-L[k], m[k]) > 0.5
    y = d["home_cov"].to_numpy()
    cm = M + L
    out = {}
    for name, (lo, hi) in SETS.items():
        mask = (s >= lo) & (s <= hi)
        res, kn = evaluate(off, key, L, m, y, mask, cm)
        diff = lambda idx: float(np.mean(np.where(kn, cm, -cm)[idx] - np.where(off, cm, -cm)[idx]))
        res["cover_margin_ci95"] = E.cluster_boot(d, diff, mask)
        out[name] = res
    return out


def cbs2025() -> dict:
    """2025 CBS-open games (players2025_games.csv), distributions fitted on seasons before 2025."""
    g = pl.read_csv(config.ROOT / "data/backtests/players2025_games.csv").filter(pl.col("half"))
    sched, _ = nflverse.pull("schedules", save=False)
    reg = sched.filter(pl.col("game_type") == "REG", pl.col("result").is_not_null(),
                       pl.col("spread_line").is_not_null(), pl.col("total_line").is_not_null())
    g = g.join(reg.select("game_id", pl.col("total_line").alias("T")), on="game_id")
    tr = reg.filter(pl.col("season") < 2025)
    c, M0, T0 = -tr["spread_line"].to_numpy(), tr["result"].to_numpy(), tr["total_line"].to_numpy()
    L, m, M, T = (g[x].to_numpy().astype(float) for x in ("open", "close", "margin", "T"))
    off = TotalDist("shifted_total").fit(c, M0, T0).sf(-L, m, T) > 0.5
    key = MarginDist(kind=final.SHADOW).fit(c, M0).sf(-L, m) > 0.5
    return evaluate(off, key, L, m, M > -L, np.ones(L.size, bool), M + L)[0]


def season2026() -> dict:
    g = json.loads((config.ROOT / "data/backtests/variants2026.json").read_text())["games"]
    L, m, M = (np.array([r[k] for r in g], float) for k in ("L", "m", "margin"))
    off = np.array([r["picks"]["official"] for r in g], bool)
    key = np.array([r["picks"]["keynum"] for r in g], bool)
    return evaluate(off, key, L, m, M > -L, np.ones(L.size, bool), M + L)[0]


def run() -> dict:
    res = {"asb": asb(), "cbs2025": cbs2025(), "2026": season2026()}
    prim = res["asb"]["asb_2022_2024"]
    res["primary_pass"] = prim["p"] <= 0.05
    (config.ROOT / "data/backtests/keynum_combo.json").write_text(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    r = run()
    p = r["asb"]["asb_2022_2024"]
    print({"primary_pass": r["primary_pass"], "differ": p["differ"], "kn_wins": p["kn_wins"], "p": p["p"]})
