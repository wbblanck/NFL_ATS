"""v3 history (docs/v3_history_preregistration.md): the as-registered player projection scored game by game on
Test A (2022-2024) and Test B (2025), so it can be graded against the stale and closing lines like the other models.

Nothing here refits v3 year by year. It reuses players_v3_eval unchanged (train-only constants, (D, k) tuned on
2013-2021, beta fit on 2013-2021 and frozen) and checks that it reproduces the published run before anything is graded."""
from __future__ import annotations

import json

import numpy as np
import polars as pl

from engine import config
from engine.backtest import patterns as P
from engine.backtest import players_v3_eval as E


def build(cache: str | None = None, log=print) -> tuple[pl.DataFrame, dict]:
    ctx = E.prepare(cache, log=log)
    tu = E.tune(ctx, log=log)
    D, k = tu["D"], tu["k"]
    reg = ctx["reg"]
    d = E.design(E.features(ctx["data"], ctx["sched"], D, k, ctx["const"]), ctx["rates"], ctx["games"])
    beta = E.fit_beta(E._split(d, *E.TRAIN))
    stale = P.dataset().select("game_id", "season", "line", "close", "margin", "p_live")
    rows, scored = [], {}
    for lab, (lo, hi) in (("test_a", E.TEST_A), ("test_b", (E.TEST_B, E.TEST_B))):
        s = E._split(reg, lo, hi)
        pm3, pm1 = E.game_pmfs(E._split(d, lo, hi), s, beta), E.game_pmfs(E._split(d, lo, hi), s, None)
        g = s.filter(pl.col("result").is_not_null(), pl.col("spread_line").is_not_null(), pl.col("game_id").is_in(list(pm3)))
        scored[lab] = g.height
        for r in stale.filter(pl.col("game_id").is_in(g["game_id"].to_list())).iter_rows(named=True):
            gid, ln = r["game_id"], r["line"]
            rows.append({**r, "p_v3": E._cover(pm3[gid], ln), "p_v1": E._cover(pm1[gid], ln)})
    df = pl.DataFrame(rows).sort("season", "game_id")
    # reproduction check against the published run
    pub = json.loads((config.ROOT / "data" / "backtests" / "players_v3.json").read_text())
    half = df.filter(pl.col("season") == 2025).filter((pl.col("line").abs() % 1 == 0.5))
    y = (half["margin"].to_numpy() > -half["line"].to_numpy())
    w3 = int(((half["p_v3"].to_numpy() > 0.5) == y).sum()); w1 = int(((half["p_v1"].to_numpy() > 0.5) == y).sum())
    ref = pub["test"]["test_b_cbs_open"]["half_point_opens"]
    checks = {"scored_test_a": scored["test_a"], "published_test_a": pub["test"]["test_a"]["n_games"],
              "scored_test_b": scored["test_b"], "published_test_b": pub["test"]["test_b"]["n_games"],
              "half_point_2025_n": half.height, "published_n": ref["v3"]["N"],
              "v3_w": w3, "published_v3_w": ref["v3"]["W"], "v1_w": w1, "published_v1_w": ref["v1"]["W"], "D": D, "k": k}
    checks["reproduces"] = (checks["scored_test_a"] == checks["published_test_a"] and checks["scored_test_b"] == checks["published_test_b"]
                            and checks["v3_w"] == checks["published_v3_w"] and checks["v1_w"] == checks["published_v1_w"])
    return df, checks


def main(cache: str | None = None) -> int:
    df, checks = build(cache)
    print(json.dumps(checks, indent=1))
    out = config.ROOT / "data" / "backtests" / "v3_history.csv"
    df.write_csv(out)
    (config.ROOT / "data" / "backtests" / "v3_history_checks.json").write_text(json.dumps(checks, indent=1))
    print(out, df.height, "games; reproduces:", checks["reproduces"])
    return 0 if checks["reproduces"] else 1
