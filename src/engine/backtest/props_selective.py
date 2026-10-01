"""Selective prop rules (docs/selective_props_confirm.md): chosen on 2025, confirmed on 2026.

All start from the under at the highest line where >= 2 books disagree (props_confirm.screened, best under
price at that line, pushes dropped), with the line gap capped at 30% of the lower line (floored at 1).
"""
from __future__ import annotations

import numpy as np
import polars as pl

from engine.backtest import props as P
from engine.backtest import props_confirm as C

RULES = {
    "R1_three_plus_books": pl.col("nb") >= 3,
    "R2_under_priced_below_-120": pl.col("under_odds") < -120,
    "R3_high_line_at_BetRivers_or_BetMGM": pl.col("book").is_in(["BetRivers NJ", "BetMGM NJ"]),
}


def bets(g: pl.DataFrame) -> pl.DataFrame:
    s = C.screened(g)
    grp = s.group_by(C.KEY).agg(pl.col("book").n_unique().alias("nb"), pl.col("line").n_unique().alias("nl"),
                                ((pl.col("line").max() - pl.col("line").min())
                                 / pl.col("line").min().abs().clip(lower_bound=1)).alias("rel"))
    x = s.join(grp.filter((pl.col("nb") >= 2) & (pl.col("nl") >= 2) & (pl.col("rel") <= 0.30)), on=C.KEY)
    x = x.filter(pl.col("line") == pl.col("line").max().over(C.KEY))
    return x.sort("under_odds", descending=True).unique(subset=C.KEY, keep="first").filter(pl.col("result") != "push")


def evaluate(x: pl.DataFrame, level: float = 0.025 / 3, n_boot: int = 4000, seed: int = 7) -> dict:
    """ROI per unit, week-clustered interval at the Bonferroni level (one-sided 2.5% / 3 rules)."""
    if x.height == 0:
        return {"n": 0, "pass": False}
    won = (x["result"] == "under").cast(pl.Float64).to_numpy()
    pnl = P.profit(x["under_odds"].to_numpy(), won)
    wk = (x["season"] * 100 + x["week"]).to_numpy()
    ids = np.unique(wk)
    grp = [np.where(wk == w)[0] for w in ids]
    rng = np.random.default_rng(seed)
    bs = [pnl[np.concatenate([grp[j] for j in rng.integers(0, len(ids), len(ids))])].mean() for _ in range(n_boot)]
    lo, hi = np.quantile(bs, [level, 1 - level])
    return {"n": x.height, "weeks": len(ids), "under_rate": float(won.mean()), "roi": float(pnl.mean()),
            "roi_ci": [float(lo), float(hi)], "pass": bool(x.height >= 30 and len(ids) >= 10 and lo > 0)}


def run(season: int) -> dict:
    g = P.graded(P.join(P.load_lines(season), P.load_stats(season), P.load_snaps(season)))
    b = bets(g)
    return {name: evaluate(b.filter(cond)) for name, cond in RULES.items()}
