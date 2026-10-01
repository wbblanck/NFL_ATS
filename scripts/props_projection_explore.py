"""Projection model vs prop lines, exploration on 2024 (fit) and 2025 (check) ONLY.
Bet unit: the DraftKings quote for each player-game-market (screened as in props_confirm). Writes docs/props_projection_explore.txt."""
from __future__ import annotations

import io

import numpy as np
import polars as pl

from engine import config
from engine.backtest import props as P, props_confirm as C
from engine.models import player_proj as M


def bets(season: int, proj: pl.DataFrame) -> pl.DataFrame:
    """DraftKings quote only (the one book present all season both years); screened as in props_confirm.
    `nl` = number of distinct lines among all real books for the same prop (books disagree if >= 2)."""
    g = P.graded(P.join(P.load_lines(season), P.load_stats(season), P.load_snaps(season)))
    s = C.screened(g).filter(pl.col("result") != "push")
    nl = s.group_by(C.KEY).agg(pl.col("line").n_unique().alias("nl"),
                               pl.col("line").max().alias("hi"), pl.col("line").min().alias("lo"))
    dk = s.filter(pl.col("book") == "DK NJ").unique(subset=C.KEY).join(nl, on=C.KEY)
    return dk.join(proj.select("player_id", "season", "week", "market", "proj", "n_prior"),
                   on=["player_id", "season", "week", "market"], how="inner") \
        .with_columns(((pl.col("line") - pl.col("proj")) / pl.col("line").abs().clip(lower_bound=1)).alias("gap_u"),
                      ((pl.col("proj") - pl.col("line")) / pl.col("line").abs().clip(lower_bound=1)).alias("gap_o"),
                      pl.col("result").alias("result_lo"))


def main() -> None:
    buf = io.StringIO()
    pr = lambda *a: print(*a, file=buf)  # noqa: E731
    st = M.stats([2023, 2024, 2025]); imp = M.implied_points([2023, 2024, 2025])
    L = M.long(M.features(st, imp))
    params = M.fit(L.filter(pl.col("season") == 2024))
    pr("fitted on 2024 (a = team factor exponent, b = opponent):", {m: (p["a"], p["b"]) for m, p in params.items()})
    proj = M.project(L, params)
    for S in (2024, 2025):
        b = bets(S, proj)
        x = b.filter(pl.col("market") != "anytime_td")
        mae_line = float(np.mean(np.abs(proj.join(x.select("player_id", "week", "market", "line"), on=["player_id", "week", "market"]).filter(pl.col("season") == S).select(pl.col("actual") - pl.col("line")).to_numpy())))
        mae_proj = float(np.mean(np.abs(proj.join(x.select("player_id", "week", "market"), on=["player_id", "week", "market"]).filter(pl.col("season") == S).select(pl.col("actual") - pl.col("proj")).to_numpy())))
        pr(f"\n== {S} ({'fit' if S == 2024 else 'check'}): {x.height} props with a projection; MAE line {mae_line:.2f} vs projection {mae_proj:.2f}")
        for side, gap, oc, res in (("UNDER (line above projection)", "gap_u", "under_odds", "under"),
                                   ("OVER (projection above line)", "gap_o", "over_odds", "over")):
            pr(f"  {side}")
            for k in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30):
                y = x.filter(pl.col(gap) >= k)
                if y.height == 0:
                    continue
                rcol = "result" if res == "under" else "result_lo"
                won = (y[rcol] == res).cast(pl.Float64).to_numpy()
                pr(f"    gap >= {k:.2f}: n {y.height:5d}  win {won.mean():.3f}  ROI {P.profit(y[oc].to_numpy(), won).mean():+.3f}")
        for k in (0.10, 0.20):
            y = x.filter(pl.col("gap_u") >= k, pl.col("nl") >= 2, pl.col("line") == pl.col("hi"))
            won = (y["result"] == "under").cast(pl.Float64).to_numpy()
            if y.height:
                pr(f"  UNDER gap >= {k:.2f} AND books disagree AND DK has the high line: n {y.height}  win {won.mean():.3f}  ROI {P.profit(y['under_odds'].to_numpy(), won).mean():+.3f}")
        pr("  UNDER gap >= 0.15 by market:", sorted(
            (mk, y.height, round(float((y["result"] == "under").mean()), 3),
             round(float(P.profit(y["under_odds"].to_numpy(), (y["result"] == "under").cast(pl.Float64).to_numpy()).mean()), 3))
            for (mk,), y in x.filter(pl.col("gap_u") >= 0.15).group_by(["market"])))
    out = config.ROOT / "docs" / "props_projection_explore.txt"
    out.write_text(buf.getvalue())
    print(buf.getvalue())


if __name__ == "__main__":
    main()
