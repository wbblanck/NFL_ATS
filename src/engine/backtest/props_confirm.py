"""Confirmation test for NFL player props (docs/props_confirm_preregistration.md).

Hypotheses from the 2024 exploration (docs/props_explore_2024.txt), tested once on held-out seasons:

- H1 (decides) Where at least two books post different lines for the same player-game-market, bet the under
  at the highest line (best under price among the books at that line).
- H2 (reported only) Same games: the under at the lowest line.

Screen (fixed before any held-out data): real books only (Action Network Consensus/Open dropped); over/under
markets except passing TDs and interceptions (0.5 / 1.5 / 2.5 lines there are different propositions); both
prices present; de-vigged P(over) in [0.35, 0.65] and hold < 10% (drops quotes that look in-game or stale);
lines differ by at most 15% of the lower line (floored at 1); pushes dropped; one bet per player-game-market.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from engine.backtest import props as P

KEY = ["player_id", "week", "market"]
EXCLUDE = ["pass_td", "pass_int"]


def screened(g: pl.DataFrame) -> pl.DataFrame:
    return g.filter(pl.col("p_over").is_between(0.35, 0.65), pl.col("hold") < 0.10,
                    ~pl.col("market").is_in(EXCLUDE), pl.col("player_id").is_not_null())


def disagreement_bets(g: pl.DataFrame) -> dict[str, pl.DataFrame]:
    s = screened(g)
    grp = s.group_by(KEY).agg(pl.col("book").n_unique().alias("nb"), pl.col("line").n_unique().alias("nl"),
                              ((pl.col("line").max() - pl.col("line").min())
                               / pl.col("line").min().abs().clip(lower_bound=1)).alias("rel"))
    keep = grp.filter((pl.col("nb") >= 2) & (pl.col("nl") >= 2) & (pl.col("rel") <= 0.15)).select(KEY)
    d = s.join(keep, on=KEY)
    out = {}
    for name, ext in (("H1_under_at_highest_line", pl.col("line").max()), ("H2_under_at_lowest_line", pl.col("line").min())):
        x = d.filter(pl.col("line") == ext.over(KEY))
        x = x.sort("under_odds", descending=True).unique(subset=KEY, keep="first")   # best under price
        out[name] = x.filter(pl.col("result") != "push").sort(KEY)
    return out


def baseline(g: pl.DataFrame) -> pl.DataFrame:
    """Every screened DraftKings under (one per player-game-market): what any under earned that week."""
    return screened(g).filter(pl.col("book") == "DK NJ", pl.col("result") != "push").unique(subset=KEY)


def _pnl(x: pl.DataFrame) -> np.ndarray:
    return P.profit(x["under_odds"].to_numpy(), (x["result"] == "under").cast(pl.Float64).to_numpy())


def evaluate(x: pl.DataFrame, base: pl.DataFrame, n_boot: int = 4000, seed: int = 7) -> dict:
    """ROI per unit on the under at the recorded price. Week-clustered bootstrap (whole weeks resampled, the
    same draw for the bets and the same-weeks baseline). PASS needs n >= 30 bets in >= 10 weeks and both 95%
    lower ends > 0: (a) the ROI and (b) ROI minus the same weeks' baseline ROI."""
    n = x.height
    if n == 0:
        return {"n": 0, "pass": False}
    pnl = _pnl(x)
    wk = (x["season"] * 100 + x["week"]).to_numpy()
    base = base.filter((pl.col("season") * 100 + pl.col("week")).is_in(np.unique(wk).tolist()))
    bpnl = _pnl(base)
    bwk = (base["season"] * 100 + base["week"]).to_numpy()
    ids = np.unique(wk)
    gx = [np.where(wk == w)[0] for w in ids]
    gb = [np.where(bwk == w)[0] for w in ids]
    rng = np.random.default_rng(seed)
    roi_b, diff_b = np.empty(n_boot), np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.integers(0, len(ids), len(ids))
        a = pnl[np.concatenate([gx[j] for j in pick])].mean()
        c = bpnl[np.concatenate([gb[j] for j in pick])].mean()
        roi_b[b], diff_b[b] = a, a - c
    q = lambda v: [float(np.quantile(v, 0.025)), float(np.quantile(v, 0.975))]  # noqa: E731
    roi_ci, diff_ci = q(roi_b), q(diff_b)
    return {"n": n, "weeks": len(ids), "win_rate": float((x["result"] == "under").mean()), "roi": float(pnl.mean()),
            "roi_ci95": roi_ci, "baseline_n": base.height, "baseline_roi": float(bpnl.mean()),
            "roi_minus_baseline": float(pnl.mean() - bpnl.mean()), "roi_minus_baseline_ci95": diff_ci,
            "books_at_bet": dict(x["book"].value_counts().iter_rows()),
            "pass": bool(n >= 30 and len(ids) >= 10 and roi_ci[0] > 0 and diff_ci[0] > 0)}


def run(seasons: list[int]) -> dict:
    out = {}
    for s in seasons:
        d = P.join(P.load_lines(s), P.load_stats(s), P.load_snaps(s))
        g = P.graded(d)
        bets, base = disagreement_bets(g), baseline(g)
        out[str(s)] = {k: evaluate(v, base) for k, v in bets.items()}
    return out
