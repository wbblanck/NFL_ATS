"""Sharp-book market estimate check (docs/sharp_line_preregistration.md): the live model's pick with the market at
lock taken as (1) the nflverse consensus close, (2) Pinnacle's close, (3) Pinnacle's close adjusted by its no-vig
price. Stale line: the SBRO open. Seasons 2014-2017 (Pinnacle era of the AusSportsBetting file)."""
from __future__ import annotations

import math

import numpy as np
import polars as pl

from engine.backtest import gap2022 as G
from engine.backtest import total as T
from engine.models.margin_dist import TotalDist
from engine.picks.grading import is_half_point

SEASONS = (2014, 2017)
GRID = np.arange(-30, 30.001, 0.05)


def dataset() -> pl.DataFrame:
    df, sched = T.load()
    reg = sched.filter(pl.col("game_type") == "REG")
    m = G.match(G.load_xlsx(), reg.filter(pl.col("season").is_between(*SEASONS)))
    return df.join(m, on="game_id").filter(
        pl.col("season").is_between(*SEASONS), pl.col("open").is_not_null(), pl.col("b_close").is_not_null(),
        pl.col("hp").is_not_null(), pl.col("margin") != -pl.col("open")).with_columns(
        ((1 / pl.col("hp")) / (1 / pl.col("hp") + 1 / pl.col("ap"))).alias("q_home"),
        pl.col("open").map_elements(is_half_point, return_dtype=pl.Boolean).alias("half"),
        (pl.col("margin") > -pl.col("open")).cast(pl.Float64).alias("y"))


def price_center(td: TotalDist, spread: float, q_home: float, total: float) -> float:
    """Centre c at which P(home covers its own spread | c, no push) equals the no-vig price probability.
    Prices are conditional on no push, so on a whole-number spread the push mass is removed (fixed after the first
    run, which counted pushes as losses and shifted whole-number lines by ~0.5 pt; both runs are reported)."""
    n = np.full_like(GRID, 1.0)
    t = -spread
    cover = td.sf(n * t, GRID, n * total)
    if float(t).is_integer():
        lose = 1 - td.sf(n * (t - 0.5), GRID, n * total)                          # P(margin < t)
        p = cover / np.clip(cover + lose, 1e-9, None)
    else:
        p = cover
    return float(GRID[np.argmin(np.abs(p - q_home))])


def run() -> dict:
    df, _ = T.load()
    d = dataset()
    y, half = d["y"].to_numpy(), d["half"].to_numpy()
    opn, tot, s = d["open"].to_numpy(), d["total"].to_numpy(), d["season"].to_numpy()
    qh = d["q_home"].to_numpy()
    mk = {"baseline": d["close"].to_numpy(), "pinnacle": d["b_close"].to_numpy(), "pinnacle_price": np.empty(d.height)}
    probs = {k: np.empty(d.height) for k in mk}
    for yr in np.unique(s):
        tr = df.filter(pl.col("season") < yr)
        td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
        k = s == yr
        for i in np.where(k)[0]:
            mk["pinnacle_price"][i] = price_center(td, mk["pinnacle"][i], qh[i], tot[i])
        for name, m in mk.items():
            probs[name][k] = td.sf(-opn[k], m[k], tot[k])

    def ll(p, yy):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return float(-np.mean(yy * np.log(p) + (1 - yy) * np.log(1 - p)))

    def cmp(a, b, mask):
        pa, pb, yy = probs[a][mask] > 0.5, probs[b][mask] > 0.5, y[mask]
        diff = pa != pb
        ao, bo, n = int(((pa == yy) & diff).sum()), int(((pb == yy) & diff).sum()), int(diff.sum())
        return {"N": int(mask.sum()), f"{a}_W": int((pa == yy).sum()), f"{b}_W": int((pb == yy).sum()),
                "differ": n, f"{a}_only": ao, f"{b}_only": bo, "z": (ao - bo) / math.sqrt(n) if n else 0.0,
                f"{a}_logloss": ll(probs[a][mask], yy), f"{b}_logloss": ll(probs[b][mask], yy)}
    near = np.abs(mk["baseline"] - opn) <= 0.5
    out = {"n_games": int(d.height), "n_half": int(half.sum()),
           "pinnacle_vs_consensus_close": {"equal": float(np.mean(mk["pinnacle"] == mk["baseline"])),
                                           "mean_abs_diff": float(np.mean(np.abs(mk["pinnacle"] - mk["baseline"])))},
           "price_center_minus_pinnacle": float(np.mean(np.abs(mk["pinnacle_price"] - mk["pinnacle"])))}
    for v in ("pinnacle", "pinnacle_price"):
        out[f"{v}_vs_baseline_half"] = cmp(v, "baseline", half)
        out[f"{v}_vs_baseline_half_near"] = cmp(v, "baseline", half & near)
        out[f"{v}_vs_baseline_all"] = cmp(v, "baseline", np.ones_like(half, bool))
    out["worth_credits"] = any(out[f"{v}_vs_baseline_half"]["z"] >= 1.645
                               and out[f"{v}_vs_baseline_half"][f"{v}_logloss"] < out[f"{v}_vs_baseline_half"]["baseline_logloss"]
                               for v in ("pinnacle", "pinnacle_price"))
    return out
