"""Exploration of NFL player props on the 2024 season ONLY (docs/props_preregistration.md).

Everything here is descriptive; any pattern is a hypothesis until confirmed once on held-out seasons.
Bets are graded at the posted price of each real book (Action Network's Consensus/Open dropped); each
(player, game, market) is counted once per book.

Writes docs/props_explore_2024.txt.
"""
from __future__ import annotations

import io
import sys

import numpy as np
import polars as pl

from engine import config
from engine.backtest import props as P

OUT = config.ROOT / "docs" / "props_explore_2024.txt"


def roi(odds: np.ndarray, won: np.ndarray) -> tuple[int, float]:
    return len(odds), float(P.profit(odds, won).mean()) if len(odds) else float("nan")


def side_won(res: np.ndarray, side: str) -> np.ndarray:
    return np.where(res == "push", np.nan, (res == side).astype(float))


def prior_means(stats: pl.DataFrame, prev: pl.DataFrame) -> pl.DataFrame:
    """Per player-week: mean of each market's stat over this player's earlier 2024 games (strictly before the
    week); weeks with no earlier 2024 game use the player's 2023 regular-season mean."""
    long = stats.unpivot(index=["player_id", "week"], on=list(P.STAT), variable_name="market", value_name="v")
    out = []
    for (pid, mk), g in long.sort("week").group_by(["player_id", "market"], maintain_order=True):
        w, v = g["week"].to_numpy(), g["v"].to_numpy().astype(float)
        cs = np.cumsum(v) - v
        n = np.arange(len(v))
        with np.errstate(invalid="ignore", divide="ignore"):
            m = np.where(n > 0, cs / np.maximum(n, 1), np.nan)
        out.append(pl.DataFrame({"player_id": [pid] * len(w), "market": [mk] * len(w), "week": w,
                                 "prior_mean": m, "prior_n": n}))
    pm = pl.concat(out)
    pv = prev.unpivot(index=["player_id", "week"], on=list(P.STAT), variable_name="market", value_name="v") \
        .group_by("player_id", "market").agg(pl.col("v").mean().alias("prev_mean"), pl.len().alias("prev_n"))
    return pm.join(pv, on=["player_id", "market"], how="left").with_columns(
        pl.when(pl.col("prior_n") > 0).then(pl.col("prior_mean")).otherwise(pl.col("prev_mean")).alias("asof_mean"))


def main() -> None:
    buf = io.StringIO()
    pr = lambda *a: print(*a, file=buf)  # noqa: E731
    lines = P.load_lines(2024)
    stats = P.load_stats(2024)
    d = P.join(lines, stats, P.load_snaps(2024))
    pr("rows (real books):", d.height, "| books:", dict(d["book"].value_counts().sort("count", descending=True).iter_rows()))
    pr("match:", dict(d["match"].value_counts().iter_rows()), "| with actual:", d.filter(pl.col("actual").is_not_null()).height)
    um = d.filter(pl.col("match") != "full").select("player", "team", "week", "match").unique().head(15)
    pr("unmatched / last-name examples:", um.rows())

    g = P.graded(d)
    pr("\n== Over/under markets, every real book (one row per player-game-market-book) ==")
    pr("market          n   hold   over%  under%  push%  mean p_over  ROI over  ROI under")
    for mk in sorted(g["market"].unique()):
        x = g.filter(pl.col("market") == mk)
        res = x["result"].to_numpy()
        _, ro = roi(x["over_odds"].to_numpy(), side_won(res, "over"))
        _, ru = roi(x["under_odds"].to_numpy(), side_won(res, "under"))
        pr(f"{mk:13s} {x.height:5d}  {x['hold'].median():.3f}  {np.mean(res=='over'):.3f}  {np.mean(res=='under'):.3f}"
           f"  {np.mean(res=='push'):.3f}   {x['p_over'].mean():.3f}     {ro:+.3f}   {ru:+.3f}")

    pr("\n== Calibration of de-vigged P(over), all O/U markets, DK only ==")
    dk = g.filter(pl.col("book") == "DK NJ", pl.col("result") != "push")
    bins = [0, .40, .45, .50, .55, .60, 1]
    for lo, hi in zip(bins[:-1], bins[1:]):
        x = dk.filter(pl.col("p_over").is_between(lo, hi, closed="left"))
        if x.height:
            pr(f"  p_over [{lo:.2f},{hi:.2f}): n {x.height:5d}  mean p {x['p_over'].mean():.3f}  over rate {np.mean(x['result'].to_numpy()=='over'):.3f}")

    pr("\n== Line vs the player's as-of mean (strictly earlier games; week 1 uses 2023), DK only ==")
    prev = P.load_stats(2023)
    pm = prior_means(stats, prev)
    e = dk.join(pm, on=["player_id", "market", "week"], how="left").filter(pl.col("asof_mean").is_not_null())
    e = e.with_columns(((pl.col("asof_mean") - pl.col("line")) / pl.col("line").abs().clip(lower_bound=0.5)).alias("gap"))
    for mk in sorted(e["market"].unique()):
        x = e.filter(pl.col("market") == mk)
        if x.height < 200:
            continue
        q = np.quantile(x["gap"].to_numpy(), [0, .2, .4, .6, .8, 1])
        row = []
        for lo, hi in zip(q[:-1], q[1:]):
            y = x.filter(pl.col("gap").is_between(lo, hi, closed="left" if hi < q[-1] else "both"))
            row.append(f"{np.mean(y['result'].to_numpy()=='over'):.3f}")
        pr(f"  {mk:13s} n {x.height:5d}  over rate by gap quintile (mean - line, low->high): {' '.join(row)}")

    pr("\n== Anytime TD (yes price only), all real books ==")
    td = d.filter(pl.col("market") == "anytime_td", pl.col("yes_odds").is_not_null(), pl.col("actual").is_not_null())
    td = td.with_columns((1 / td["yes_odds"].map_elements(P.american_to_decimal, return_dtype=pl.Float64)).alias("p_imp"),
                         (pl.col("actual") > 0).cast(pl.Float64).alias("scored"))
    for lo, hi in [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, .5), (.5, 1)]:
        x = td.filter(pl.col("p_imp").is_between(lo, hi, closed="left"))
        if x.height:
            _, r = roi(x["yes_odds"].to_numpy(), x["scored"].to_numpy())
            pr(f"  implied [{lo:.1f},{hi:.1f}): n {x.height:5d}  implied {x['p_imp'].mean():.3f}  scored {x['scored'].mean():.3f}  ROI yes {r:+.3f}")

    pr("\n== Books disagreeing on the line (same player-game-market), O/U ==")
    k = ["player_id", "week", "market"]
    multi = g.group_by(k).agg(pl.col("line").n_unique().alias("nl"), pl.col("book").n_unique().alias("nb"))
    pr("  player-game-markets with >= 2 books:", multi.filter(pl.col("nb") >= 2).height,
       "| with different lines:", multi.filter((pl.col("nb") >= 2) & (pl.col("nl") >= 2)).height)

    pr("\n== Follow-ups (added after the tables above; still 2024 only) ==")
    gg = g.filter(pl.col("result") != "push")
    res = gg["result"].to_numpy()
    _, ru = roi(gg["under_odds"].to_numpy(), side_won(res, "under"))
    pr(f"  always under, all O/U markets, all books: n {gg.height}  under {np.mean(res=='under'):.3f}  ROI {ru:+.3f}")
    for name, mks in {"yardage": ["pass_yds", "rush_yds", "rec_yds", "rush_rec_yds", "pass_rush_yds"],
                      "counts": ["pass_att", "pass_cmp", "rush_att", "rec"], "tds_ints": ["pass_td", "pass_int"]}.items():
        x = gg.filter(pl.col("market").is_in(mks))
        r = x["result"].to_numpy()
        _, rr = roi(x["under_odds"].to_numpy(), side_won(r, "under"))
        pr(f"  always under, {name:9s}: n {x.height:5d}  under {np.mean(r=='under'):.3f}  ROI {rr:+.3f}")
    for lab, cond in {"under is plus money or even": pl.col("under_odds") >= -100,
                      "under is minus money": pl.col("under_odds") < -100}.items():
        x = gg.filter(cond)
        r = x["result"].to_numpy()
        _, rr = roi(x["under_odds"].to_numpy(), side_won(r, "under"))
        pr(f"  always under, {lab:28s}: n {x.height:5d}  under {np.mean(r=='under'):.3f}  ROI {rr:+.3f}")
    pr("  under rate by line tercile within market (low -> high line):")
    for mk in ["rec", "rec_yds", "rush_yds", "rush_att", "pass_yds", "rush_rec_yds"]:
        x = gg.filter(pl.col("market") == mk)
        q = np.quantile(x["line"].to_numpy(), [0, 1 / 3, 2 / 3, 1])
        row = []
        for lo, hi in zip(q[:-1], q[1:]):
            y = x.filter(pl.col("line").is_between(lo, hi, closed="left" if hi < q[-1] else "both"))
            r = y["result"].to_numpy()
            _, rr = roi(y["under_odds"].to_numpy(), side_won(r, "under"))
            row.append(f"[{lo:g}-{hi:g}] {np.mean(r=='under'):.3f} ({rr:+.3f})")
        pr(f"    {mk:13s} " + "  ".join(row))
    pr("  line shopping where books disagree (same player-game-market, >= 2 books, different lines):")
    k = ["player_id", "week", "market"]
    dis = gg.join(multi.filter((pl.col("nb") >= 2) & (pl.col("nl") >= 2)).select(k), on=k)
    lo_ = dis.filter(pl.col("line") == pl.col("line").min().over(k))
    hi_ = dis.filter(pl.col("line") == pl.col("line").max().over(k))
    for lab, x, side, oc in (("over at the lowest line", lo_, "over", "over_odds"),
                             ("under at the highest line", hi_, "under", "under_odds")):
        x = x.unique(subset=k, keep="first")
        r = x["result"].to_numpy()
        _, rr = roi(x[oc].to_numpy(), side_won(r, side))
        pr(f"    {lab:26s}: n {x.height:4d}  win {np.mean(r==side):.3f}  ROI {rr:+.3f}")
    OUT.write_text(buf.getvalue())
    sys.stdout.write(buf.getvalue())


if __name__ == "__main__":
    main()
