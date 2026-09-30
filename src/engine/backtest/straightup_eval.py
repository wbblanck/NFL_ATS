"""Close-game straight-up test (docs/straightup_preregistration.md): market favorite vs v1 (2010-2025) and v3
(2022-2024) on games with a closing spread of 2.5 or less."""
from __future__ import annotations

import math
import pickle

import numpy as np
import polars as pl

from engine.backtest import total as T
from engine.models import projection as P
from engine.models.margin_dist import TotalDist

SEASONS = (2010, 2025)


def market_probs(df: pl.DataFrame, d: pl.DataFrame) -> np.ndarray:
    """P(home wins) from the live margin distribution (fit on earlier seasons) at the closing spread and total."""
    out = np.empty(d.height)
    s = d["season"].to_numpy()
    for yr in np.unique(s):
        tr = df.filter(pl.col("season") < yr)
        td = TotalDist("shifted_total").fit(tr["close"].to_numpy(), tr["margin"].to_numpy(), tr["total"].to_numpy())
        k = s == yr
        out[k] = td.sf(np.zeros(k.sum()), d["close"].to_numpy()[k], d["total"].to_numpy()[k])
    return out


def v1_margins(d: pl.DataFrame, sched: pl.DataFrame) -> np.ndarray:
    import nflreadpy as nfl
    from engine.backtest import projection_eval as PE
    from engine.picks import final
    games = P.team_games(nfl.load_team_stats(seasons=list(range(1999, 2026))), sched)
    tgt = d.join(sched.select("game_id", "week", "home_team", "away_team"), on="game_id").select(
        "game_id", "season", "week", "home_team", "away_team")
    pr = PE.project_games(games, tgt, final.PROJ_H, final.PROJ_LAM)
    return np.array([np.nan if x is None else (lambda hs: hs[0] - hs[1])(x.mean_scores()) for x in pr])


def compare(pick_a: np.ndarray, pick_b: np.ndarray, home_won: np.ndarray, pa: np.ndarray | None = None,
            pb: np.ndarray | None = None) -> dict:
    diff = pick_a != pick_b
    ao, bo, n = int(((pick_a == home_won) & diff).sum()), int(((pick_b == home_won) & diff).sum()), int(diff.sum())
    out = {"N": int(len(home_won)), "a_W": int((pick_a == home_won).sum()), "b_W": int((pick_b == home_won).sum()),
           "differ": n, "a_only": ao, "b_only": bo, "z": (ao - bo) / math.sqrt(n) if n else 0.0}
    return out


def run(v3_pickle: str | None = None) -> dict:
    df, sched = T.load()
    d = df.filter(pl.col("season").is_between(*SEASONS), pl.col("margin") != 0)
    pm = market_probs(df, d)
    home_won = d["margin"].to_numpy() > 0
    mkt = pm > 0.5
    close = np.abs(d["close"].to_numpy()) <= 2.5
    v1m = v1_margins(d, sched)
    ok = ~np.isnan(v1m)
    v1 = v1m > 0
    out = {"market_all": {"W": int((mkt == home_won).sum()), "N": int(len(home_won)),
                          "expected_W": float(np.where(mkt, pm, 1 - pm).sum())},
           "close_games": int(close.sum()),
           "v1_vs_market_close": compare(v1[close & ok], mkt[close & ok], home_won[close & ok]),
           "v1_vs_market_all": compare(v1[ok], mkt[ok], home_won[ok])}
    for lo, hi in ((2010, 2017), (2018, 2025)):
        k = close & ok & (d["season"].to_numpy() >= lo) & (d["season"].to_numpy() <= hi)
        out[f"v1_vs_market_close_{lo}_{hi}"] = compare(v1[k], mkt[k], home_won[k])
    if v3_pickle:
        pmfs = pickle.load(open(v3_pickle, "rb"))
        mg = np.arange(-P.MAXP, P.MAXP + 1)
        v3m = np.array([float(pmfs[g] @ mg) if g in pmfs else np.nan for g in d["game_id"].to_list()])
        k3 = ~np.isnan(v3m)
        out["v3_vs_market_close_2022_2024"] = compare((v3m > 0)[k3 & close], mkt[k3 & close], home_won[k3 & close])
        out["v3_vs_market_all_2022_2024"] = compare((v3m > 0)[k3], mkt[k3], home_won[k3])
    z = out["v1_vs_market_close"]["z"]
    out["PASS"] = bool(z >= 1.645)
    return out
