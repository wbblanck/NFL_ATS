"""Re-grade the tracked models on the rebuilt 2018-2022 pool lines vs the SBRO open. Research only.

Models (as defined live, walk-forward where they learn from history):
- official: MarginDist("shifted") fit on earlier seasons' close/margin; P(cover line | close) > 0.5.
- keynum: same with MarginDist("keynum") (the live shadow model).
- v1: proj-poisson-v1, refit each week (H=8, lambda=5, as live); P(margin > -line) > 0.5.
- hybrid: official pick if |close - line| >= 1, else v1 pick (hybrid-v1-lowmove).
v3 is not re-graded: it was fit on 2013-2021, so 2018-2021 would be in-sample.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from engine.backtest import walk_forward as W  # noqa: E402
from engine.backtest.projection_eval import data as proj_data, project_games  # noqa: E402
from engine.models import projection as P  # noqa: E402
from engine.models.margin_dist import MarginDist  # noqa: E402
from engine.picks import final, hybrid  # noqa: E402

D = ROOT / "data" / "raw" / "espn_history"
MG = np.arange(-P.MAXP, P.MAXP + 1)


def outcome(margin, line, side):
    if margin == -line:
        return "P"
    return "W" if (margin > -line) == (side == "home") else "L"


def main() -> None:
    base = W.load()
    rb = pl.read_csv(D / "rebuilt_pool_lines_2018_2022.csv").select("game_id", "rebuilt_pool")
    df = base.join(rb, on="game_id", how="left").filter(pl.col("season").is_between(2018, 2022))
    hist = W.load()
    sched, games = proj_data()
    tgt = sched.filter(pl.col("game_id").is_in(df["game_id"].to_list())).select(
        "game_id", "season", "week", "home_team", "away_team")
    pr = dict(zip(tgt["game_id"].to_list(), project_games(games, tgt, final.PROJ_H, final.PROJ_LAM)))
    rows = []
    for s in range(2018, 2023):
        tr = hist.filter(pl.col("season") < s)
        md = {k: MarginDist(k).fit(tr["close"].to_numpy(), tr["margin"].to_numpy()) for k in ("shifted", "keynum")}
        for r in df.filter(pl.col("season") == s).to_dicts():
            for src, line in (("sbro", r["open"]), ("rebuilt", r["rebuilt_pool"])):
                if line is None:
                    continue
                picks = {}
                for k, name in (("shifted", "official"), ("keynum", "keynum")):
                    p = float(md[k].sf(np.array([-line]), np.array([r["close"]]))[0])
                    picks[name] = "home" if p > 0.5 else "away"
                x = pr.get(r["game_id"])
                if x is not None:
                    picks["v1"] = "home" if float(x.margin_pmf[MG > -line].sum()) > 0.5 else "away"
                    picks["hybrid"] = picks["official"] if abs(r["close"] - line) >= hybrid.MIN_MOVE else picks["v1"]
                for m, side in picks.items():
                    rows.append({"game_id": r["game_id"], "season": s, "src": src, "model": m,
                                 "o": outcome(r["margin"], line, side)})
    R = pl.DataFrame(rows)
    R.write_csv(D / "models_on_rebuilt_lines_games.csv")
    both = (R.group_by("game_id", "model").agg(pl.col("src").n_unique().alias("n"))
            .filter(pl.col("n") == 2).select("game_id", "model"))
    def rec(x):
        w, l, p = (x.filter(pl.col("o") == k).height for k in "WLP")
        return f"{w}-{l}-{p} ({w / (w + l):.1%})"
    print("Same games 2018-2021 (both lines available):")
    for m in ("official", "keynum", "v1", "hybrid"):
        q = R.join(both, on=["game_id", "model"]).filter(pl.col("model") == m)
        print(f"  {m:9s} SBRO open {rec(q.filter(pl.col('src') == 'sbro'))}   "
              f"rebuilt {rec(q.filter(pl.col('src') == 'rebuilt'))}")
    print("Rebuilt lines, 2022 / all 2018-2022:")
    for m in ("official", "keynum", "v1", "hybrid"):
        q = R.filter(pl.col("model") == m, pl.col("src") == "rebuilt")
        print(f"  {m:9s} 2022 {rec(q.filter(pl.col('season') == 2022))}   all {rec(q)}")


if __name__ == "__main__":
    main()
