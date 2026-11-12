"""Score the refit harness output against V0 (docs/simulator_refit_v1_preregistration.md). Research only.

Usage: python scripts/sim_refit_score.py [candidate ...]   (default: v0r v1)
Reads data/gamesim/refit/<version>_<season>.parquet, writes data/gamesim/refit/score_v1.json.
Sign: spread negative = home favored; home covers when margin > -spread.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

K = Path(__file__).resolve().parents[1] / "data" / "gamesim" / "refit"
V = np.arange(-60, 61)
ALPHA, SIMS, BOOT, BSEED = 0.1, 1000, 10000, 7
KEYS = [1, 2, 3, 4, 6, 7, 8, 10, 14]
SEASONS = {"v0r": [2022, 2023, 2024, 2025], "v1": [2021, 2022, 2023, 2024, 2025]}


def load(version, seasons):
    return pl.concat([pl.read_parquet(K / f"{version}_{s}.parquet") for s in seasons]).sort("game_id")


def per_game(df: pl.DataFrame) -> dict:
    n = df.height
    margin = df["margin"].to_numpy().astype(float)
    total = df["total"].to_numpy().astype(float)
    spread = df["close_spread"].to_numpy().astype(float)
    dist = np.stack([df[f"m_{v}"].to_numpy() for v in V], axis=1)
    idx = np.clip(margin.astype(int), -60, 60) + 60
    sm = (dist * SIMS + ALPHA) / (SIMS + 121 * ALPHA)
    thr = -spread
    gt = (dist * (V[None, :] > thr[:, None])).sum(1)
    eq = (dist * (V[None, :] == thr[:, None])).sum(1)
    p_cov = gt / np.clip(1 - eq, 1e-9, None)
    push = margin == thr
    y_cov = (margin > thr).astype(float)
    pw = df["sim_pwin"].to_numpy()
    tie = margin == 0
    y_win = (margin > 0).astype(float)
    return {"abs_err": np.abs(df["sim_fair"].to_numpy() - margin), "ll": -np.log(sm[np.arange(n), idx]),
            "tot_err": np.abs(df["sim_total"].to_numpy() - total), "p_cov": p_cov, "push": push, "y_cov": y_cov,
            "pw": pw, "tie": tie, "y_win": y_win, "fair": df["sim_fair"].to_numpy(), "spread": spread, "dist": dist,
            "margin": margin}


def market_pwin(df):
    def imp(ml):
        ml = ml.astype(float)
        return np.where(ml < 0, -ml / (-ml + 100), 100 / (ml + 100))
    h, a = imp(df["home_moneyline"].to_numpy()), imp(df["away_moneyline"].to_numpy())
    return h / (h + a)


def boot(diff, rng):
    n = len(diff)
    means = np.array([diff[rng.integers(0, n, n)].mean() for _ in range(BOOT)])
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)), float((means >= 0).mean())


def secondary(df, g):
    keep = ~g["push"]
    nt = ~g["tie"]
    side = np.where(g["fair"] > -g["spread"], 1.0, np.where(g["fair"] < -g["spread"], 0.0, np.nan))[keep]
    yk = g["y_cov"][keep]
    ok = ~np.isnan(side)
    w = int((side[ok] == yk[ok]).sum())
    mk = market_pwin(df)
    out = {"games": df.height, "margin_mae": float(g["abs_err"].mean()), "margin_logloss": float(g["ll"].mean()),
           "total_mae": float(g["tot_err"].mean()),
           "close_total_mae": float(np.abs(df["total_line"].to_numpy() - df["total"].to_numpy()).mean()),
           "ats_brier": float(((np.clip(g["p_cov"][keep], 1e-6, 1 - 1e-6) - yk) ** 2).mean()),
           "ats_record_vs_close": [w, int(ok.sum()) - w],
           "ml_brier": float(((g["pw"][nt] - g["y_win"][nt]) ** 2).mean()),
           "ml_brier_market_novig": float(((mk[nt] - g["y_win"][nt]) ** 2).mean())}
    absm = np.abs(g["margin"])
    dist = g["dist"]
    out["key_margins"] = {str(k): {"actual": float((absm == k).mean()),
                                   "sim": float((dist[:, V == k].sum(1) + dist[:, V == -k].sum(1)).mean())} for k in KEYS}
    # 3-point split
    s3 = dist[:, V == 3].sum(1) + dist[:, V == -3].sum(1)
    a3 = (absm == 3).astype(float)
    sp = np.abs(g["spread"])
    tl = df["total_line"].to_numpy()
    ot = df["overtime"].fill_null(0).to_numpy() == 1
    splits = {"spread_0_2.5": sp <= 2.5, "spread_3_6.5": (sp > 2.5) & (sp <= 6.5), "spread_7plus": sp > 6.5,
              "total_under_44": tl < 44, "total_44_47.5": (tl >= 44) & (tl < 48), "total_48plus": tl >= 48,
              "overtime": ot, "regulation": ~ot}
    out["three_point_split"] = {k: {"n": int(m.sum()), "actual": float(a3[m].mean()) if m.sum() else None,
                                    "sim": float(s3[m].mean()) if m.sum() else None} for k, m in splits.items()}
    return out


def main(cands):
    rng = np.random.default_rng(BSEED)
    res = {}
    for c in cands:
        seasons = SEASONS[c]
        b, x = load("v0", seasons), load(c, seasons)
        assert b["game_id"].to_list() == x["game_id"].to_list()
        gb, gx = per_game(b), per_game(x)
        r = {"seasons": seasons, "games": b.height}
        d_mae, d_ll = gx["abs_err"] - gb["abs_err"], gx["ll"] - gb["ll"]
        lo, hi, p = boot(d_mae, rng)
        r["mae_diff"] = {"mean": float(d_mae.mean()), "ci95": [lo, hi], "p_one_sided": p}
        lo, hi, p2 = boot(d_ll, rng)
        r["logloss_diff"] = {"mean": float(d_ll.mean()), "ci95": [lo, hi], "p_one_sided": p2}
        seas = b["season"].to_numpy()
        r["mae_diff_by_season"] = {str(s): float(d_mae[seas == s].mean()) for s in seasons}
        r["seasons_better"] = int(sum(v < 0 for v in r["mae_diff_by_season"].values()))
        r["candidate"] = {"pooled": secondary(x, gx), **{str(s): secondary(x.filter(pl.col("season") == s),
                          per_game(x.filter(pl.col("season") == s))) for s in seasons}}
        r["v0"] = {"pooled": secondary(b, gb), **{str(s): secondary(b.filter(pl.col("season") == s),
                   per_game(b.filter(pl.col("season") == s))) for s in seasons}}
        res[c] = r
    # Holm over candidates on the one-sided MAE p
    ps = sorted((res[c]["mae_diff"]["p_one_sided"], c) for c in res)
    m = len(ps)
    stop = False
    for i, (p, c) in enumerate(ps):
        ok = (not stop) and p <= 0.05 / (m - i)
        stop = stop or not ok
        res[c]["holm_pass"] = bool(ok)
    for c, r in res.items():
        cp, vp = r["candidate"]["pooled"], r["v0"]["pooled"]
        sec_ok = (cp["total_mae"] - vp["total_mae"] <= 0.1 and cp["ats_brier"] - vp["ats_brier"] <= 0.005
                  and cp["ml_brier"] - vp["ml_brier"] <= 0.005)
        need = 3 if c == "v0r" else 4
        r["pass"] = bool(r["holm_pass"] and r["mae_diff"]["ci95"][1] < 0 and r["logloss_diff"]["ci95"][1] < 0
                         and r["seasons_better"] >= need and sec_ok)
        r["secondary_ok"] = bool(sec_ok)
    (K / "score_v1.json").write_text(json.dumps(res, indent=1))
    for c, r in res.items():
        print(c, "games", r["games"], "MAE diff", round(r["mae_diff"]["mean"], 4), [round(v, 4) for v in r["mae_diff"]["ci95"]],
              "LL diff", round(r["logloss_diff"]["mean"], 4), [round(v, 4) for v in r["logloss_diff"]["ci95"]],
              "seasons better", r["seasons_better"], "PASS" if r["pass"] else "FAIL")


if __name__ == "__main__":
    main(sys.argv[1:] or ["v0r", "v1"])
